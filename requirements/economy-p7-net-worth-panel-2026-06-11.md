# Brief — P7 / #86: "Why is my net worth X?" panel (2026-06-11)

**Issue:** #86 (P7 in `requirements/economics-review-2026-06-10.md`).
**Suggested owner:** Claude (reporting/UI surface — server payload + static
frontend + CLI display; no engine-mechanic changes). Independent of the
P1/P2/P3 economy rebalance, so it can land in parallel without rework.
**Base off:** current `origin/pre-release`.

---

## Why

Net worth is the win condition, but its components are scattered across the
treasury, inventory, capital, the loan ledger, and the equity/shareholder-loan
layer. Players "can't optimise what they can't see." This is pure decomposition
and display of values the engine already computes — **no scoring changes**.

## The scoring drivers (already computed — just expose them)

The win-condition score is `Player.total_wealth(...)`
(`island_traders/models/player.py:576`), which sums:

| Component | Source | Sign |
|---|---|---|
| Island treasury (cash) | `player.dollops` | + |
| Resource inventory (marked to market) | `player.inventory.total_value(prices)` | + |
| Capital book value (depreciated) | `player.capital_book_value(catalogue, tick)` | + |
| Bank debt outstanding | `loan_ledger.outstanding_debt(pid)` | − |
| Loans receivable (bank loans owed *to* you) | `loan_ledger.loans_receivable(pid)` | + |
| Shareholder loans owed back to investors | `sum(player.shareholder_loans.values())` | − |

Separately, the **investor** balance sheet is `Player.net_worth(...)`
(`player.py:198`): `personal_cash + Σ(holdings × share_price) + loan_receivable`.
The review lists personal cash + equity value as drivers too, so the panel
should show these as a second section (investor wealth) distinct from the
island-liquidation total — they are *not* both in `total_wealth`. Be explicit in
the UI about which number is the win-condition score (the island total) vs. the
investor net worth.

## Scope

**In:**
1. A reusable breakdown helper — e.g. `Player.wealth_breakdown(prices,
   loan_ledger, capital_catalogue, current_tick) -> dict` returning each
   component above as a labelled value plus the resolved total. Implement
   `total_wealth` in terms of it (or have it call the same sub-pieces) so the
   panel and the score can never disagree.
2. Surface it in the server player payload (the per-player `to_dict` /
   game-state broadcast in `island_traders/server/app.py`) so the frontend can
   render it. Add a matching field to the OpenAPI/UX payload tests if present
   (`tests/test_server/test_ux_payload.py`).
3. Frontend panel in the static client (`island_traders/server/static/`):
   a collapsible "Net worth breakdown" showing each component with its sign,
   the island total (win-condition score), and the investor net-worth section.
4. CLI parity: extend the existing wealth/inventory display in
   `island_traders/cli/display.py` with the same breakdown (it already prints
   Dollops + inventory; add capital, loans ±, shareholder loans, total).

**Out:**
- No change to how any component is *calculated* (no rebalance). If a number
  looks wrong, file separately — this brief only surfaces existing values.
- No historical charting of net worth over time (that's a possible follow-up;
  `player.wealth_history` already exists if wanted later).
- No new equity mechanics.

## Acceptance

- `wealth_breakdown(...)` components sum to exactly `total_wealth(...)` for the
  same args (add a test asserting equality across a few constructed players,
  including ones with debt, loans receivable, and shareholder loans).
- Server payload exposes the breakdown; UX-payload test updated.
- Static panel renders the components, the island total, and the investor
  net-worth section, clearly labelled as to which is the score.
- CLI shows the same decomposition.
- Full suite green; APP_VERSION bump + RELEASE_NOTES.

## Integration seam

Touches `player.py` (additive helper), `server/app.py` payload, static
frontend, `cli/display.py`. No overlap with the P1/P2 market/payroll work
(`market.py`, `game.py` payroll, `ai.py`) — safe to develop in parallel; if
P1/P2 lands first, rebase (the breakdown helper is additive).
