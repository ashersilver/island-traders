# Wave 5 — Defect quick fixes (2026-07-13)

Source: Ash's defect list of 2026-07-13, items 3, 6, 7, 9. All four verified
against code on master (post-#212). These are small, independent server/UI
changes suitable for direct implementation (same style as Waves 1 and 4).

---

## 5.1 Rebuild levy: misleading dead-end message (defect item 3) — CONFIRMED BUG

**Observed:** Forge tried to repair equipment and got
"Rebuild levy must be paid before capital repairs resume." with nowhere to pay.

**Root cause:** the disaster rebuild levy (5/10/20% of capital replacement
value, min 20 Dp, split into 2 installments — `constants.py:431-453`) is
collected *automatically* at each season start
(`engine/game.py:801` → `_process_rebuild_levy_payments`, `game.py:942-961`).
There is no manual payment action anywhere (server or UI), and
`player._rebuild_levy_remaining` is never serialised to the client, so the
player cannot see the amount owed or when repairs will unblock. The blocking
message (`game.py:1218`, surfaced via `app.py:4411-4412`) implies an action
that does not exist. `grep -i levy` in `static/index.html` = zero matches.

**Fix (three parts):**
1. **Serialise** `rebuild_levy_remaining` (and installment count) into the
   per-player game_state payload in `app.py` next to the other capital fields.
2. **New action** `pay_rebuild_levy`: lets the player pay any/all of the
   outstanding levy immediately from dollops (clamped to balance). Clearing
   `_rebuild_levy_remaining` to 0 unblocks repairs the same tick. Wire into
   choose_action for players with a positive balance, plus a WS handler.
3. **UI:** show an amber banner/stat when levy > 0 ("Rebuild levy outstanding:
   X Dp — deducted automatically over the next N seasons; pay now to resume
   repairs") with a **Pay levy** button. Reword the repair-blocked reason to
   mention the amount and both routes (wait for auto-installments or pay now).

**Test:** book a levy via a forced disaster, assert repair blocked, pay via the
new action, assert repair quote returns `repairable: true` same season.

---

## 5.2 Production can't use unsold listed stock (defect item 7) — DESIGN GAP

**Observed:** Digger listed all its Oil for sale, then had to buy it back to
produce.

**Findings:** listing escrows stock out of inventory at post time
(`models/market.py:400-435` → `player.give_resources`). A working
cancel/reduce path already refunds unsold stock end-to-end
(`market.py:298-355`, `app.py:3258-3320`, Remove buttons `index.html:7962`).
Production checks raw inventory only (`engine/production.py:520-541`).

**Fix — auto-delist on use** (not "count listings as available", which would
desync the order book and risk double-spend on a same-season cross):
- Give `ProductionEngine` an optional market handle (same pattern as its
  `telemetry` field, set by `Game.setup()`).
- Before the `missing` computation (`production.py:531`): for each input
  resource where inventory < needed and the player has resting asks on that
  resource, call `market.reduce_offer`/`cancel_offer` to pull back **only the
  shortfall** into inventory, then proceed. Emit a log/toast line
  ("recalled N Oil from your market ask to feed production").
- Apply the same recall in the capacity What-If/`max_producible` input check so
  quoted capacity matches what production will actually achieve.

**Agent follow-up (island-traders-agents):** teach the LLM player that its own
asks can be cancelled/reduced to reclaim stock — add to the market briefing
and expose per-resource "listed (unsold)" quantities in the state summary.

**Test:** list all Oil, produce a line needing Oil, assert production succeeds,
ask is reduced by the shortfall, and no buy-back trade occurs.

---

## 5.3 Manufacturer self-orders are free; should cost 20% of list (defect item 9)

**Observed request:** when the Manufacturer orders equipment from itself it
should pay only 20% of the price (no markup, but inputs are consumed).

**Current behaviour:** a self-order of a manufactured item settles immediately
and costs **$0 cash** — `pays = cash_only or manufacturer.player_id !=
buyer.player_id` (`app.py:3896`), so a self-build only consumes the built unit
(inputs), no dollops move. That under-charges vs. the requested 20%.

**Fix:** in the self-order branch (`app.py:3651-3665`) and settlement, charge
the Manufacturer `0.20 * list_price` (plus spares kits at cost if selected)
as a sunk cash cost (burned, no counterparty). Inputs continue to be consumed
as today. Surface the 20% figure in the order form when buyer == manufacturer.

**Test:** self-order a Foundry: assert dollops decrease by 0.20 × cost and the
manufactured resource is debited; third-party order pricing unchanged.

---

## 5.4 "Repaired and returned to service" visibility (defect item 6) — NO CODE BUG, UI POLISH

**Findings:** repaired units are never removed from the owned list —
`capital_inventory` counts all units regardless of status (`player.py:374-380`);
a failed unit only carries a red "⚠ N failed" badge that clears on repair
(`index.html:3383-3442`). Capacity returns the same season
(`player.py:423-436`; completion runs before the new failure roll,
`game.py:805` vs `859`). The Autumn observation was almost certainly the badge
clearing, not an item disappearing.

**Polish:** make the return-to-service visible: a toast + a transient green
"✓ back in service" badge on the unit row for the season after repair
completes (server already knows: emit a client event where `game.py:970-990`
prints "[CAPITAL REPAIRED] … returned to service").

---

## 5.5 Proposer cannot withdraw a pending deal (added 2026-07-14) — CONFIRMED GAP

**Observed:** once a deal is proposed and the other player hasn't responded,
the proposer has no way to change their mind.

**Findings:** no withdraw path exists anywhere — no ledger method, no WS
action, no UI control. The responder guard (`app.py:3000`,
`deal.awaiting_id != actor.player_id`) structurally blocks the proposer from
acting on their own deal, and `DealLedger.expire_for_player` is dead code
(no caller), so pending deals never expire — an unanswered proposal persists
forever. Nothing is escrowed at proposal time (`trading.py:349` only
validates; goods move once, on accept, `trading.py:424-451`), so withdrawal
is a pure state transition with zero refund logic.

**Fix (mirror `cancel_training_request`, `turn.py:2891` — the only shipped
withdraw precedent):**
1. `models/deal.py`: add `WITHDRAWN` terminal status +
   `DealLedger.withdraw(deal_id, proposer_id)` — `_require_active` first
   (race guard), assert `deal.proposer_id == proposer_id`, set status and
   clear `awaiting_id`.
2. `engine/trading.py`: thin `withdraw_deal` wrapper (parallel to
   `reject_deal`, `trading.py:468`).
3. `server/app.py`: `_handle_deal_withdraw` modeled on `_handle_deal_respond`
   (`:2976`) but authorised on `proposer_id`, requiring
   `status ∈ ACTIVE_DEAL_STATUSES`; register `deal_withdraw` in the dispatch
   (`:6520`); push `deal_response {result:"withdrawn"}` to the counterparty
   via the notify block (`:3100-3110`). Re-fetch the deal after any await —
   never trust a pre-await snapshot.
4. `index.html`: "Withdraw" button on `_renderMyDealCard` (`:6200`) when
   status is pending/returned → `{type:'deal_withdraw', deal_id}`; handle the
   withdrawn result in the `deal_response` case (`:5033`).

**Race:** counterparty accepts while withdraw is in flight — both mutate the
same in-memory ledger inside the event loop, so whichever lands second hits
`_require_active` (`deal.py:162`) and gets a clean "deal already settled"
error. Same shape as the training guard.

**Related gap (out of scope here, note for a later wave):** capital-order
negotiations have the identical hole — the buyer cannot withdraw a `PROPOSED`
order awaiting the manufacturer (`capital_negotiation.py` has no
cancel/withdraw; `app.py:3739` gates on awaiting_id). Same pattern applies.

**Test:** propose → withdraw → assert WITHDRAWN, counterparty notified, no
inventory/dollops delta; withdraw-after-accept returns "already settled";
target's respond-after-withdraw likewise.

---

Suggested order: 5.1 → 5.3 → 5.5 → 5.2 → 5.4 (5.2 touches the engine; do it
once 5.1/5.3/5.5's app.py churn has landed to avoid conflicts).
