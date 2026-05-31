# Brief — Equity Phase 2b (shareholder loans) + the economy flip (2026-05-29)

**Status:** Ready to build. Depends on the merged Phase-1 foundation
(`equity.py`, `Player.personal_cash/holdings/cap_table/net_worth`) on
`pre-release` (`a426760`).
**Owner:** Claude (lead — integration-heavy, touches the equity stack).
**Optional Codex carve-out:** the shareholder-loan model + valuation/net-worth
math as a leaf (see §7). Same pattern as `equity.py`.
**Origin:** [equity plan §11](./equity-balance-sheet-separation.md) — the
treasury reseed (500) is unplayable without a way for the owner to fund the
opening, so the flip and shareholder loans must ship **together**.

---

## 1. Why bundle them

The plan's flip seeds each island treasury at `ISLAND_STARTING_CASH = 500` and
funds capital purchases from the treasury — but the opening investing phase
routinely spends ~1000+ Dp. Without a funding path the opening is dead. The fix
is the owner **lending personal cash to their own island** (a shareholder loan).
So this brief delivers, as one coherent change:

1. **The flip** — separate personal cash from island treasury at game start;
   the bid leaves personal cash (to former owners); the treasury is its own 500.
2. **Shareholder loans (Phase 2b)** — the owner injects personal cash into the
   treasury to fund the opening (and mid-game), recorded as a liability the
   island owes back. Net-worth-neutral by construction (see §3).
3. **Net-worth scoring** — the leaderboard ranks by investor net worth, not raw
   `dollops`.

Dividends (Phase 2) are **out of scope** here — separate follow-up.

---

## 2. The money model (locked)

At game start, per island/player:

| Quantity | Value |
|---|---|
| Island treasury (`Player.dollops`) | `ISLAND_STARTING_CASH` (500) |
| Investor personal cash (`Player.personal_cash`) | `starting_capital − winning_bid` (web) / `starting_capital` (engine, no auction) |
| Cap table | `CapTable.new_with_majority(str(player_id))` → owner 60, public 40 |
| `holdings` | `{str(player_id): 60}` (owns 60% of own island) |

- The **winning bid leaves the game** (paid to imaginary former owners) — it is
  *not* added to any treasury. (This matches today, where the bid is already a
  sunk deduction from the single pool.)
- **Opening capital (investing phase)** is bought from the **treasury**. When the
  chosen basket costs more than the treasury holds, the shortfall is **auto-lent
  from personal cash** as a shareholder loan (§3). Net opening capital capacity =
  `treasury(500) + personal_cash`.

> **Balance note:** islands now get +500 of their own seed capital on top of the
> investor's leftover, so opening buying power rises vs. today. This is
> intentional (islands are independently capitalised) and **requires a
> calibration pass** — hand `sim-calibration` to Codex after this lands.

---

## 3. Shareholder loans (Phase 2b)

A shareholder loan moves cash **investor → island treasury** and records a
liability the island owes back to that investor. Modelled so it is **net-worth
neutral** (no 60/40 leakage exploit):

```
lend L:   player.personal_cash      -= L
          island.dollops (treasury) += L
          island.shareholder_loans[str(lender_id)] += L     # liability
          (the lender's matching receivable is derived, not stored — see net_worth)

repay R:  island.dollops            -= R     (only if treasury >= R)
          island.shareholder_loans[str(lender_id)] -= R
          player.personal_cash      += R
          (drop the key when it reaches 0)
```

- **Data:** add `shareholder_loans: dict[str, float] = {}` to `Player` (the
  island's books): `lender_player_id (str) -> principal owed`.
- **Interest:** **0%** for Phase 2b (`SHAREHOLDER_LOAN_RATE = 0.0`, tunable).
  Owner-financing; keep it simple. Bank loans (`loan.py`) are unaffected — these
  are a separate, owner-only instrument.
- **Liabilities:** `liquidation_value`'s `liabilities` argument **must include**
  `sum(island.shareholder_loans.values())` (alongside bank-loan principal). This
  is why lending is neutral: treasury +L and liability +L cancel in the island's
  liquidation value; personal_cash −L and the receivable +L cancel for the
  investor.

### Net worth (the one scoring formula)
```
investor_net_worth(p) =
      p.personal_cash
    + Σ_islands  p.holdings[island_id] * share_price(island)
    + Σ_islands  island.shareholder_loans.get(str(p.player_id), 0.0)   # receivables
```
where `share_price(island) = equity.share_price(equity.fair_value(liq, hist))`,
`liq = equity.liquidation_value(treasury, inventory_mtm, capital_book_value,
bank_loans + shareholder_loans)`, and `hist = island.wealth_history`.

`Player.net_worth(...)` (added in Phase 1) takes `share_price_by_island`; extend
its signature (or add an engine-side helper) to also fold in receivables — the
engine has every island, so it can pass a `loan_receivable` total or the islands
list. Keep `Player` free of engine imports.

---

## 4. Where it plugs in (verified code paths)

- **`island_traders/models/player.py`**
  - add `shareholder_loans: dict[str, float]` field.
  - extend `net_worth(...)` to include receivables (or add a sibling helper).
- **`island_traders/models/equity.py`** — already has `liquidation_value`,
  `fair_value`, `share_price`. No change needed unless the Codex carve-out adds
  loan helpers there.
- **`island_traders/engine/game.py`**
  - `setup()` (~line 133): set `dollops = ISLAND_STARTING_CASH`; set
    `personal_cash` (engine has no auction → `= spec.starting_dollops or default`);
    seat `cap_table` + `holdings`.
  - add a `share_price_by_island(prices, tick)` helper using `total_wealth()`
    (= liquidation value incl. `shareholder_loans`) + `wealth_history`.
  - `compute_summary()` (~421) and `_year_end_summary()` (~439): rank by
    `investor_net_worth`, not `total_wealth`.
  - save/load already round-trips `personal_cash/holdings/cap_table` (Phase 1);
    add `shareholder_loans`.
  - **Seam:** `total_wealth()` (player.py ~527) must subtract `shareholder_loans`
    as a liability so liquidation value is correct. Verify it already sums bank
    loans and add shareholder loans alongside.
- **`island_traders/server/app.py`**
  - web game construction (~line 1271): today
    `player_dollops = starting_capital − winning_bids − investing_spend`.
    Replace with: `personal_cash = starting_capital − winning_bid`;
    `treasury = ISLAND_STARTING_CASH`; compute the investing spend `C`, then
    `L = max(0, C − treasury)`; set `treasury = treasury + L − C`,
    `personal_cash -= L`, `shareholder_loans[str(pid)] = L`. Seat cap table.
    Pass these into `PlayerSpec`/post-construction (the spec currently only
    carries `starting_dollops`; either extend `PlayerSpec` with
    `personal_cash`/`treasury`/`shareholder_loan` or set the fields on the
    engine `Player` objects right after `Game.setup()`).
  - game-state payload (~2251): add `personal_cash`, `treasury` (= `dollops`),
    `cap_table` (`to_dict()`), `net_worth`, and `shareholder_loan_owed`.
- **`island_traders/server/static/index.html`**
  - show **two balances** (💰 Personal cash + 🏦 Island treasury) where the
    single Dollops figure is today; a compact **shareholders** readout (you 60% /
    public 40%); **net worth** on the scoreboard. If a shareholder loan is
    outstanding, show "lent N to island".
  - investing phase: surface "Treasury 500; you'll lend N from personal cash to
    cover this basket" so the auto-lend is transparent. (Explicit lend/repay
    actions are a nice-to-have; auto-lend at construction is the must.)

---

## 5. Optional mid-game actions (nice-to-have, not blocking)
- **Lend to island** — `TurnAction.LEND_TO_ISLAND`: move personal cash → own
  treasury (more shareholder-loan principal). Useful when an island is cash-short
  mid-game.
- **Repay shareholder loan** — move treasury → personal cash, reducing principal
  (only when treasury can cover it).

Ship the auto-lend-at-opening first; add these if the playtest wants them.

---

## 6. Tests
- **Model (Codex carve-out or Claude):**
  - lend/repay conserve total value (personal_cash + treasury + receivable −
    liability invariant); over-repay guarded; key dropped at 0.
  - `liquidation_value` drops by outstanding shareholder loans.
  - `investor_net_worth` is unchanged by a lend (neutrality), and a repay.
- **Engine:** `setup()` seats treasury=500, cap table 60/40, holdings; scoring
  ranks by net worth; save/load round-trips `shareholder_loans`.
- **Server:** web construction with a bid + an investing basket > 500 produces
  `personal_cash = capital − bid − L`, `treasury = 0`, `shareholder_loan = C−500`;
  payload carries the new fields.

---

## 7. Execution split (optional Codex carve-out)

To run parallel again, the **shareholder-loan model + valuation/net-worth math**
is a clean leaf, mirroring how `equity.py` was carved:

| Piece | Owner | Files |
|---|---|---|
| `shareholder_loans` field + `lend`/`repay` helpers (pure, value-conserving) + `investor_net_worth` math + unit tests | **Codex (optional)** | `models/player.py` loan helpers OR a small `models/shareholder_loans.py`; `tests/test_models/test_shareholder_loans.py` |
| The flip wiring: `game.py` setup/scoring, `app.py` construction + payload, `index.html` UI | **Claude** | `engine/game.py`, `server/app.py`, `server/static/index.html` |

**Merge order:** Codex's loan/math leaf merges first; Claude's wiring merges
second and consumes it (same as the equity.py hand-off). If Codex does *not*
take the carve-out, Claude builds the whole brief — it's all specified above.

**Branching (Codex carve-out, if taken):** base `pre-release` (`a426760`),
branch `codex/shareholder-loans-model-2026-05-29`, target `pre-release`, push and
stop.

---

## 8. After this lands
- **Calibration:** hand `sim-calibration` to Codex — the +500 island seed and
  net-worth scoring shift balance; re-tune `config/event_charts.yaml` and the
  opening-cash constants (D1: `ISLAND_STARTING_CASH`, `STARTING_CAPITAL`).
- **Phase 2 (dividends), Phase 3 (buy out the float), Phase 4 (cross-island
  buy-ins)** then build on the now-stable cap-table + loan + net-worth seam.
