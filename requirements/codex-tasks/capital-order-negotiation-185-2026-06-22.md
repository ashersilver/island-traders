# Brief — Dedicated capital-order negotiation: manufacturer review + counter-offer (2026-06-22)

**Suggested owner:** Codex (engine model + server WS handlers + tests).
**Relates to:** #185 (order form / offer + counter-offer), #188 (maintenance pricing),
Capital Orders II (financing loan + 2% referral).
**Base off:** the branch carrying Capital Orders II (#185/#188 + financing) — currently
`claude/integrate-qol-pollution-48-45`. This brief **depends on** the helpers added there
(`TurnManager.issue_capital_finance_loan`, `MANUFACTURER_FINANCE_REFERRAL_RATE`,
`CapitalFinanceError`, the `_handle_capital_order` settlement). Do not start until that base
is confirmed; if it has merged to `pre-release`, base off `pre-release`.

## Rules of engagement (Codex — read every time)

- **Worktrees / no shared trees.** Work in the **primary checkout**
  (`/Users/ashleysilver/Documents/projects/island-traders`). Claude works in a separate
  `claude/*` worktree — never edit it or `git reset/checkout/stash` against it.
- **Branch.** `git fetch`; confirm current; cut a fresh branch off the base named
  `codex/capital-order-negotiation-2026-06-22`. Never commit onto `pre-release`/`master`.
- **PRs only.** Reach `pre-release` via a PR Claude merges. Link `Refs #185`. Update
  `RELEASE_NOTES.md` and bump `APP_VERSION` `.N` in `constants.py`.
- **Git discipline.** No `--no-verify`/`--amend`/force-push. Run the **full** `pytest` suite
  before handoff.
- **Handoff.** "branch X at commit Y — ready to integrate", noting that the **frontend**
  (review panel + counter UI) is Claude's — you provide backend + WS contract + a stub-free
  message spec.

## Why

A capital order currently settles **instantly**: `_handle_capital_order`
(`server/app.py` ~line 3284) charges the buyer / runs financing and pays the Manufacturer in
one shot, with no manufacturer review. The user wants a **dedicated negotiation**: buyer
sends an **offer**, the Manufacturer **reviews** and may **accept / counter / decline**, and
on the buyer accepting a counter the order **settles**. (Chosen over reusing the resource-
deal system, but mirror its notification plumbing.)

## Current state (ground truth)

- Instant settlement + financing: `server/app.py` `_handle_capital_order` (~3284-3420).
  Pricing: `maintenance_contract_cost(item.cost, term, predictive)` (`models/player.py`),
  spares `0.15·cost·kits`, `upfront = cost + contract + spares`. Financing already routes
  through `game.turn_manager.issue_capital_finance_loan(buyer, upfront, loan_term, year,
  season)` and pays a `MANUFACTURER_FINANCE_REFERRAL_RATE` (2%) Bank-funded kickback;
  falls back to cash when no Banker / bank at cap (`CapitalFinanceError`).
- WS dispatch: `server/app.py` ~line 5266 `elif msg_type == "capital_order":`.
- Delivery: `buyer.place_capital_order(item_id, order, current_tick, delivery_seasons)`.
- **Pattern to mirror** (resource deals): `models/deal.py` `DealLedger` / `DealStatus`
  (PENDING/ACCEPTED/REJECTED/EXPIRED/RETURNED, `awaiting_id`); server
  `_handle_deal_propose` (~2699) + the target push and the `deal_response` result push
  (~2895-2925) using `self._thread_safe_send(room_id, lobby_id, {...})` followed by a fresh
  `get_game_state`; `_deal_lobby_id_for_engine_id`. The live `loan_ledger` hangs off the game
  (`game.loan_ledger`) — add `game.capital_negotiations` the same way.
- AI auto-response precedents: `engine/turn.py` `_action_offer_loan` (AI accepts `rate ≤ 0.15`)
  and the deal AI; replicate for an AI manufacturer.
- Tests harness: `tests/test_server/test_capital_order.py` (`_bootstrap(role_names)`, `_WS`,
  `asyncio.run(mgr._handle_capital_order(...))`).

## Model (`island_traders/models/capital_negotiation.py`, new)

- `CapitalNegotiationStatus(Enum)`: `PROPOSED` (awaiting manufacturer), `COUNTERED`
  (awaiting buyer), `ACCEPTED`, `DECLINED`, `EXPIRED`.
- `CapitalOrderNegotiation` dataclass: `negotiation_id`, `buyer_id`, `manufacturer_id`,
  `item_id`, order terms (`maintenance_term_years`, `predictive_maintenance`, `spares_kits`,
  `expedited_eligible`, `financing`), `list_price`, `recommended_total`, `buyer_offer`,
  `counter_total`, `status`, `awaiting_id`. `recommended_total = list + maintenance + spares`
  (guarantee 0).
- `CapitalNegotiationLedger` mirroring `DealLedger`: `create(...)`, `get(id)`,
  `for_player(pid)`, `awaiting(pid)`, with an `_next_id`.

## Server changes (`server/app.py`)

Add `game.capital_negotiations = CapitalNegotiationLedger()` where `loan_ledger` is created.
WS dispatch (near line 5266):

1. **`capital_order`** (repurpose) → validate item / manufacturer presence / manufactured-
   resource availability as today, but **create a `PROPOSED` negotiation** with
   `buyer_offer` (default = recommended_total if omitted). **Do not** charge, consume, or
   loan yet. Push a `capital_negotiation` notice to the manufacturer's lobby id; ack the
   buyer with the negotiation payload.
2. **`capital_negotiation_respond`** → manufacturer only; `action` ∈ `accept|counter|decline`.
   `counter` carries `counter_total` → status `COUNTERED`, `awaiting_id = buyer`. `accept` →
   go straight to settlement (below). `decline` → status `DECLINED`. Push result to buyer.
3. **`capital_negotiation_accept`** → buyer accepts a `COUNTERED` offer → **settle**.

**Settlement (shared by manufacturer-accept and buyer-accept-counter)** — this is the
existing `_handle_capital_order` body, moved here, charging the **agreed total**: consume one
manufactured unit; if `financing` run `issue_capital_finance_loan` (buyer treasury stays
flat, owes the loan) else `buyer.spend_dollops(total)`; pay the Manufacturer the agreed total
**+ 2% referral on financed orders** (Bank-funded, `MANUFACTURER_FINANCE_REFERRAL_RATE`);
keep the no-Banker / bank-at-cap cash fallback; then `buyer.place_capital_order(...)`. Emit a
`capital_negotiation` settled push + `capital_order_ack`-shaped fields
(`financed/loan_id/loan_repayment/referral_fee`) so the existing UI log keeps working.

4. **AI manufacturer auto-respond:** when the manufacturer seat is AI, auto-`accept` if
   `buyer_offer >= recommended_total`, else auto-`counter` at `recommended_total` (so
   negotiations never stall against AI). Mirror the deal/loan AI gating.

All pushes reuse `_thread_safe_send` + a follow-up `get_game_state`, like `deal_response`.

## Constraints & gotchas

- Settle **exactly once**; guard against double-accept (check status before settling).
- The referral stays internal — never include it in buyer-facing payloads.
- Keep `recommended_total`/pricing identical to the client formulas so the modal and server
  agree.
- Frontend (manufacturer review panel + buyer counter UI) is **Claude's** — define the WS
  message shapes precisely in the PR description; do not build UI.

## Tests (`tests/test_server/test_capital_negotiation.py`, new)

- propose → manufacturer counter → buyer accept settles once with financing + 2% referral;
  buyer treasury flat, loan created.
- manufacturer `decline` → no charge, nothing consumed, no loan.
- `buyer_offer >= recommended_total` against an AI manufacturer auto-accepts and settles.
- financed accept with **no Banker** falls back to cash.
- double `capital_negotiation_accept` settles only once.
Keep `tests/test_server/test_capital_order.py` valid (migrate its assertions onto the
negotiation flow if you repurpose the `capital_order` message).

## Definition of done

- New model + ledger + three WS handlers + AI auto-respond; settlement (incl. financing +
  referral) moved out of the old instant path. Full `pytest` green. PR with RELEASE_NOTES +
  APP_VERSION bump and the **WS message contract** documented for the frontend wiring.
