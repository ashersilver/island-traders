# Wave 9 — A real capital order book: backorders, amend, cancel, sweeteners (2026-07-22)

Source: Ash, 2026-07-22 — "Manufacturer doesn't just automatically refuse an
order, he should be able to create an order book, and someone who orders a
capital item should be able to change their order for a different item if
production has not started. Eg if an order needs 2 FarmMachinery and the
manufacturer does not have them, it is still possible to cancel the order. At
the moment the manufacturer is able to produce 2 FarmMachinery he is able to
fulfil the order to Agriculture. Also when ordering a piece of equipment the
total should be adjustable so the deal can be sweetened to ensure the order can
be pushed up the queue."

## Audit findings (2026-07-22) — read before writing code

The order book *looks* implemented but is inert:

- **Orders are refused before anything is stored.** `_handle_capital_order`
  (`server/app.py:3770-3777`) hard-returns an error when
  `manufacturer.inventory.get(resource) < capacity_units`. No ledger row, no
  order-book entry — nothing exists to retry or cancel. The same gate repeats
  at settlement (`app.py:4049-4057`) and in the CLI path (`turn.py:1064-1071`).
  Locked in by `tests/test_server/test_capital_order.py:149-167`.
- **Order-book entries are only created at settlement, always locked.**
  `app.py:4148-4153` → `game.enqueue_capital_negotiation(..., locked=True)`
  (`engine/game.py:485-502`). So every entry is `locked=True, status=accepted`,
  and `ManufacturerOrderBook.reorder` refuses any permutation touching locked
  entries (`models/order_book.py:75-87`) — **`manufacturer_reorder_queue` can
  never succeed in a real game.** The passing test bypasses acceptance by
  calling `order_book.add()` directly.
- **`order_book.remove()` has zero callers.** Entries accumulate forever,
  including after delivery.
- **No buyer cancel or amend.** `_handle_capital_negotiation_action` hard-forces
  `action = "accept"` for the buyer (`app.py:3910-3915`); nothing mutates
  `item_id`/terms after `create()`.
- **No retry pass.** Nothing walks `game.capital_negotiations` per season.
- **`buyer_offer` exists on the wire but the frontend never sends it**
  (`submitCapitalOrder`, `index.html:3376-3390`), so every UI order offers
  exactly `recommended_total` — there is no sweetener today, and `queue_position`
  is pure insertion order with no price input.
- **The buyer never sees their own pending orders.** `my_capital_negotiations`
  ships in game_state but is rendered by nothing.
- **`slots_per_season` is effectively 1** — `game.py:474-476` reads
  `Player.production_capacity`, which is a 0-1 multiplier (default 1.0), not a
  throughput. Promise dates are therefore "one order per season, forever".

## Resolved design decisions (defaults — Ash to veto any)

- **D1 — Acceptance means "I'll build it".** A manufacturer reviewing a
  backordered proposal can accept, counter or decline as today. Accepting an
  order it cannot yet fill moves it to the new `QUEUED` status and puts it in
  the order book **unlocked**; it settles automatically when units exist.
- **D2 — Sweetener places, manufacturer disposes.** Paying above
  `recommended_total` places the entry above any unlocked entry with a smaller
  premium at the moment it is offered or raised. The manufacturer may still
  manually reorder afterwards and that always wins — two permanently competing
  sort orders would make the manufacturer's drag gesture look broken.
- **D3 — One drain, in queue order.** Queued orders settle only in a single
  per-season pass walking `queue_position`, consuming units as it goes and
  stopping at the first order it cannot fill. Never check-then-settle per order
  independently (see landmine 2).
- **D4 — Amend/cancel are gated on `status in {PROPOSED, COUNTERED, QUEUED}`
  and `entry.locked is False`.** Once settled, cash has moved, units are
  consumed and a finance loan may exist; there is no unwind path and there
  should not be one.

---

## Task 9.1 — Backorders instead of refusals (requirement a, d) — LARGE

1. Add `QUEUED` to `CapitalNegotiationStatus` and include it in
   `ACTIVE_CAPITAL_STATUSES`.
2. In `_handle_capital_order`, replace the hard return at `app.py:3770-3777`
   with: record the shortfall on the negotiation (`units_required`,
   `units_short_at_order`) and continue to create the ledger row. The buyer's
   ack must say clearly that the order is **backordered**, not accepted.
3. On manufacturer acceptance of an order that cannot be filled now: set
   `QUEUED` and `game.enqueue_capital_negotiation(..., locked=False)` instead
   of settling. Orders that *can* be filled settle immediately exactly as today.
4. **Per-season drain** (new, alongside the seasonal capital work in
   `engine/game.py:820+`): for each manufacturer, walk its order book in
   `queue_position` order; for each unlocked `QUEUED` entry, if the
   manufacturer now holds `capacity_units` of the manufactured resource **and**
   the buyer can still pay, settle it via the existing
   `_settle_capital_negotiation` primitive and mark the entry `locked=True`.
   Stop at the first entry that cannot be filled — do not skip ahead, or a
   cheap small order would perpetually jump a large one.
5. Notify both parties on each automatic fulfilment (push + fresh game_state,
   as the equity-sale settle path now does).
6. **Fix removal**: call `order_book.remove()` when the delivered item leaves
   `capital_in_transit` (`models/player.py:598-617` drives delivery). Without
   this the locked prefix grows forever and pins every queue head — this is a
   prerequisite for reorder and priority working at all.

## Task 9.2 — Buyer amend & cancel (requirements b, c) — MEDIUM

1. **Extract the quote block** from `_handle_capital_order` (`app.py:3779-3782`)
   into a shared helper — amend must recompute `list_price`,
   `recommended_total`, `manufactured_resource` and `capacity_units`.
2. New `capital_order_amend`: buyer changes `item_id` and/or terms
   (maintenance, spares kits, predictive, expedited) while
   `status in {PROPOSED, COUNTERED, QUEUED}` and the entry is unlocked.
   Amending **resets `status` to `PROPOSED`, clears `counter_total`, and flips
   `awaiting_id` back to the manufacturer** — otherwise a buyer could swap a
   cheap item onto an agreed expensive price.
3. New `capital_order_cancel`: buyer withdraws while unlocked. Sets
   `CANCELLED` (new terminal status), clears `awaiting_id`, and calls
   `order_book.remove()`. Guard the race the same way the deal-withdraw path
   does — re-check status after any await; whichever mutation lands second is
   refused with "already settled".
4. Buyer-side branch in `_handle_capital_negotiation_action`: stop hard-forcing
   `action = "accept"` (`app.py:3910-3915`) so amend/cancel can route through.

## Task 9.3 — Sweetener and priority (requirement e) — MEDIUM

1. **Send `buyer_offer` from the UI.** Add an editable total to the order form
   (`index.html`, near `#cap-order-total`), defaulting to `recommended_total`,
   and include it in `submitCapitalOrder`. Show the premium over the
   recommended total live ("+40 Dp — priority").
2. Store `premium = buyer_offer - recommended_total` on the order-book entry.
   On insert, place the entry above any unlocked entry with a smaller premium
   (D2). Locked entries never move.
3. New `capital_order_sweeten` (or reuse amend): the buyer raises
   `buyer_offer` on a `QUEUED`/`PROPOSED` order, which re-places it by the
   same rule and re-runs `refresh_order_promises`. Raising the offer to at
   least `counter_total` on a countered order should auto-accept, matching the
   AI rule at `app.py:3989`.
4. Surface `premium` and the resulting position in both the manufacturer's
   order-book panel and the new buyer panel, so the manufacturer can see who
   paid for priority.

## Task 9.4 — Buyer's pending-orders panel (prerequisite for 9.2/9.3) — SMALL

`my_capital_negotiations` already ships in game_state and is rendered by
nothing. Add a panel listing the buyer's live orders with status
(proposed / countered / **backordered — waiting on N × Resource** / queued at
position P, promised Year Y Season S), and the Amend / Sweeten / Cancel
controls from 9.2 and 9.3.

## Task 9.5 — Fix promise dates (supporting) — SMALL

`game.refresh_order_promises` (`game.py:467-483`) computes
`slots = max(1, round(max(1.0, manufacturer.production_capacity)))` — a 0-1
multiplier, so always 1. Map it to the manufacturer's real durable throughput
(`capacity.manufacturer_durable_allowance`, already in the payload) so queued
promise dates mean something once buyers can see them.

---

## Landmines (from the audit — do not skip)

1. **Removal before priority.** Fix 9.1.6 first; otherwise accumulated locked
   entries pin every queue head and reorder/priority silently do nothing.
2. **Double-spend of manufactured units.** N queued orders can all pass an
   independent stock check against the same units. Only the single ordered
   drain (D3) may consume units; never settle a queued order outside it.
3. **No unwind after settlement.** Gate amend/cancel on unlocked + non-settled
   (D4). Settlement moves cash, consumes units and can issue a finance loan.
4. **Amend invalidates a counter.** Always reset to `PROPOSED` + re-await the
   manufacturer (9.2.2).
5. **Multi-manufacturer selection is `next(...)`** (`app.py:3764-3767`) — the
   first Manufacturer in `game.players`. Queueing makes that arbitrary pick
   much more consequential; let the buyer choose when more than one exists
   (the CLI path already asks, `turn.py:1062`).

## Gates

Full pytest suite plus 3 same-seed all-AI sims: no season-end crash, no
manufactured-unit conservation error (assert total units consumed by
settlements equals units removed from manufacturer inventories), and
Manufacturer mean net worth within ±10% of the pre-wave baseline. New tests
must cover: backorder created rather than refused; drain settles in queue order
and stops at the first unfillable entry; cancel/amend rejected once locked;
amend resets a countered order; sweetener re-places an entry above a smaller
premium but never above a locked one; delivered entries leave the book.
