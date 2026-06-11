# Codex brief — Economy P1 + P2: market-maker spread/depth + payroll (2026-06-10)

**Owner:** Codex. **Integrator:** Claude.
**Issues:** P1 → #82, P2 → #83 (ship as one calibration pass).
**Depends on:** money-supply instrumentation (P5/#73, PR #92, on `pre-release`
at `0.1.0-dev.2026-06-10.6`). Use the runner's new money-supply summary +
`*_money.csv` as the calibration instrument for this pass.

---

## Why these two together

From `requirements/economics-review-2026-06-10.md` §4: P1 tames the faucet, P2
adds a sink; they interact through prices and treasuries, so calibrating them in
one pass avoids chasing a moving target. The review sequences P1+P2 as the
single largest playability lever after measurement.

**Baseline to calibrate against (pre-release `.6`, `--games 1000 --seed 42`):**
- Win%: Farmer 3.0 / Manufacturer 5.2 / Banker 12.2 / Miner 18.3 / Educator 18.7
  / Doctor 19.3 / Transporter 23.3. Target ≈ 14.3% each; Farmer & Manufacturer
  are the structural losers.
- **Money supply is a net SINK** (~−45%/game, ≈10500 → ~5700 Dp, ≈−400/season).
  This inverts review D1's "unanchored faucet" assumption. P1's spread is a *new*
  sink and P2's payroll is *another* sink — so watch the money-supply chart
  closely: stacking two sinks on an already-contracting economy could starve it.
  If circulation collapses, the lever is P1 depth (smaller) and P2 wage (smaller),
  or a compensating faucet is needed — flag for discussion rather than guessing.

---

## P1 — Market-maker spread + finite depth

**Current behaviour** (`island_traders/models/market.py`):
- `current_price()` (L100) returns a single mid price from the formula
  `1 + PRICE_ELASTICITY·(d−s)/(s+d+1)`, clamped `MIN/MAX_PRICE_MULTIPLIER`.
- `execute_sell()` (L137) pays the seller `mid × qty` and mints Dp unconditionally
  (buyer of last resort). `execute_buy()` (L123) charges `mid × qty` and is capped
  only by posted `supply`.

**Change:**
1. **Spread.** The market-maker buys from players at a **bid** and sells to players
   at an **ask** around the formula mid: `bid = mid·(1−SPREAD)`, `ask = mid·(1+SPREAD)`,
   with `MARKET_MAKER_SPREAD` (start 0.12; calibrate 0.10–0.15) in `constants.py`.
   - `execute_sell` pays `bid × qty`; `execute_buy` charges `ask × qty`.
   - The spread `(ask−bid)·qty` is the money sink — it is destroyed, not paid to
     anyone.
2. **Finite depth.** Cap the market-maker's *own* fills per resource per season at
   `MARKET_MAKER_DEPTH` units (start ~40/resource; calibrate). Beyond the cap the
   market-maker refuses (raise/return "no fill") so the player must find a
   counterparty via the order book (`post_offer`/`post_bid`). The existing
   player-to-player auto-match path must remain unaffected — depth limits only the
   formula market-maker, not peer fills.
   - Track per-season fill volume on the Market; reset it in
     `reset_period_signals()` (L509).

**Keep:** disaster `PriceShock`s, the clamps, and the order book. The spread/depth
sit *on top of* the existing formula mid.

## P2 — Payroll

**Current behaviour:** workers are trained, fed, injured, killed — never paid (review
D2). There is no per-season wage.

**Change:** charge each island a per-season wage for every **active** worker,
scaled by band:
- `PAYROLL_PER_BAND = {Worker: 1.0, Technician: 2.0, Manager: 4.0}` Dp/season in
  `constants.py` (calibrate). Use `band_of(profession)` / `WorkerBand`
  (already imported in `engine/turn.py:21`).
- Charge in a new `Game._process_payroll(year, season)` in
  `island_traders/engine/game.py`, modelled on the existing per-season per-player
  loop `_process_capital_maintenance` (L292). Call it from `run()` alongside the
  other `_process_*` calls (around L234–237), **before** `run_season`.
- Pay from island treasury (`player.dollops`). On shortfall: pay what's affordable
  and mark the rest unpaid — **do not** crash. Decide one of {skip-no-effect for
  v1, or a morale/productivity penalty} — v1 = charge-only, no penalty, so the
  calibration reads cleanly. Surface a log line like capital maintenance does.
- Payroll Dp is **destroyed** (a sink), consistent with there being no household
  cash account yet (P3 introduces consumer spending later).

**Out of scope (do NOT do here):** household income / consumer demand (that's P3
/#84), interest-rate linkage (D6), freight friction (P4/#85). Payroll only removes
cash this pass; the earning side comes in P3.

---

## Integration seam

- Both changes are additive constants + one new `_process_payroll` method + edits
  to `execute_buy`/`execute_sell`/`reset_period_signals`. No overlap with the
  `ai.py` strategy work (#29) — safe to run in parallel, but if #29 lands first,
  rebase onto it.
- The AI (`engine/ai.py`) buys/sells via the market; with a spread + depth its
  arbitrage/dump heuristics may need a light touch so bots don't stall (e.g.
  `AI_ARBITRAGE_MIN_MARGIN` may need to exceed the spread). Check AI liveness in
  the sim (no role's trade volume should crater to zero); adjust the AI margin
  constant if needed, but keep AI behaviour changes minimal and noted.

## Acceptance

- Full suite green (add tests: spread makes ask>bid and the gap leaves circulation;
  depth cap refuses the (N+1)th market-maker unit but peer match still fills;
  payroll debits treasury by Σ band wages and logs a shortfall without crashing).
- `--games 1000 --seed 42`: report the new win% spread **and** the money-supply
  summary. Goal: narrow the win% spread (especially lift Farmer/Manufacturer) and
  keep circulation from collapsing — if the two sinks over-contract the economy,
  stop and flag rather than over-tuning.
- APP_VERSION bump + RELEASE_NOTES entry (include before/after win% and
  money-supply numbers).
