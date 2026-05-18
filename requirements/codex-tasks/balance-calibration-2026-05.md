# Codex Task — Balance Calibration (release blocker, 2026-05-18)

**Goal:** Bring AI-only win rates back toward ~1/7 (≈14% per role) so a
point release of `pre-release` → `master` can ship. This is the single
**hard blocker** for the next release.

## Why this is urgent

Measured on `pre-release` @ `36c74a4` (this is *current*, not the old
stale note), AI-only, 3 years/game, multi-seed (42/1/7/99, 200
games/seed):

| Role        | Mean Win% | Avg Wealth (seed 42, 300g) |
|-------------|-----------|----------------------------|
| Farmer      | **42.5%** | 409.8 Dp |
| Banker      | **54.6%** | 310.3 Dp |
| Miner       | 0.4%      | 71.7 Dp |
| Transporter | **0.0%**  | 40.5 Dp |
| Educator    | 1.0%      | 225.0 Dp |
| Manufacturer| 1.5%      | 143.5 Dp |
| Doctor      | **0.0%**  | 88.5 Dp |

Banker + Farmer take ~97% of all wins. **Transporter and Doctor win
literally zero games across 800 games on every seed.** Target is ~14%
each. The pattern is stable across seeds, so this is structural, not
RNG.

This drifted because several large mechanical changes landed since the
last calibration without a re-balance pass: the agriculture role split
(Grain/Produce/Meat/Food + Horticulturalist), Education Phases 1–3
(Courses, Instructor, apprenticeship slot-pool + Instructor gate,
profession-dependent course duration, 75% settling ramp, itemised
training fee), the §21 balance-aware sustenance model, the
loan/insurance Banker economics, and the personnel-sidebar bundled
training UX.

## Important: this is probably NOT just event-chart tuning

`config/event_charts.yaml` weights tune yields/disasters. But
Transporter and Doctor sitting at **0% wins with 40–88 Dp avg wealth**
(vs Farmer 410) looks **structural** — those islands are not building
wealth at all, which event-yield multipliers alone won't fix. Likely
suspects to diagnose first:

- **Transporter**: produces Freight + PassengerSeats. Does AI demand for
  Freight/PassengerSeats actually exist post-refactor? The Phase 3
  training flow now uses Educator-supplied air tickets — did that remove
  the Transporter's main revenue? Check `_post_population_food_demand`,
  PassengerSeats demand, and whether AI ever buys Freight.
- **Doctor**: produces HealthServices + Vaccine; consumes Expertise +
  LaboratoryEquipment. After the Expertise rename + Course economics,
  does anyone buy HealthServices/Vaccine in the AI loop? Is the Doctor
  starved of Expertise inputs?
- **Banker**: 55% — the loan-interest-spread / insurance model may be
  over-powered relative to commodity producers.
- **Farmer**: 43% — the Grain/Produce/Meat→Food assembly + §21
  sustenance change may have over-valued food.

Diagnose with per-role wealth trajectories (the runner already writes
`simulation_results/run_roles.csv` and `run_prices.csv`) before
touching weights. Fixing 0%-win roles will likely need production /
pricing / AI-trading adjustments, not only `event_charts.yaml`.

## Branch

- **Base:** latest `origin/pre-release` (≥ `36c74a4`)
- **Branch name:** `codex/balance-calibration-2026-05`
  (the old `codex/sim-calibration` branch is stale/abandoned — 0 commits
  ahead of pre-release, ~5.8k lines behind; do NOT resume it, start
  fresh)
- **Target for merge:** `pre-release`

## In scope

- `config/event_charts.yaml` — yield/disaster/outage weights
- `island_traders/constants.py`, `island_traders/constants_capacity.py`
  — production recipes, base prices, capital capacities, starting
  inventories (coordinate via RELEASE_NOTES if touching these; they are
  the structural levers)
- `island_traders/engine/ai.py` — AI trading/production strategy if a
  role structurally never trades a product it should
- `island_traders/simulation/runner.py` — fine to extend stats
- `tests/` — keep green; add a balance regression guard if practical
- `RELEASE_NOTES.md` — `### codex/balance-calibration-2026-05` section
  with before/after tables

## Out of scope (do not start without coordination)

- `island_traders/engine/turn.py` training/apprenticeship flow (Phase 3,
  freshly merged — `_action_request_training`,
  `_training_capacity_status`, `_consume_training_capacity`, the
  self-training loop). If a balance fix needs this, flag it in
  RELEASE_NOTES first.
- `requirements/` specs and `RULES.md` (a separate doc-reconciliation
  task owns RULES.md staleness — see "Related" below).

## Workflow

1. **Baseline** (reproduce the numbers above):
   ```bash
   .venv/bin/python -m island_traders.simulation.runner \
       --games 1000 --years 3 --seed 42
   .venv/bin/python -m island_traders.simulation.runner \
       --games 200 --years 3 --seeds 42,1,7,99
   ```
2. **Diagnose** the 0%-win roles from `run_roles.csv` /
   `run_prices.csv` — find *why* Transporter/Doctor build no wealth.
3. **Fix structurally first** (production/pricing/AI), then fine-tune
   `event_charts.yaml`. Iterate on `--seed 42`, then verify on
   1/7/99.
4. **Final run:** `--games 5000 --seed 42` plus the multi-seed sweep.

## Acceptance criteria

- ✅ Every role mean win% within **±5pp of 14.3%** on a 1000-game
  `--seed 42` run, AND on the 4-seed sweep (42/1/7/99).
- ✅ **No role at 0%** and none above ~25% on any verification run.
- ✅ Full test suite green: `.venv/bin/python -m pytest tests/`
  (≥ 297 — current `pre-release` baseline).
- ✅ `RELEASE_NOTES.md` has a `### codex/balance-calibration-2026-05`
  section with before/after multi-seed win-rate tables.

## If event-chart tuning genuinely can't fix it

Don't force unrealistic weights. If a role is structurally broken,
**stop and write the diagnosis** in RELEASE_NOTES under "Known
follow-ups" and coordinate before changing core economic formulas — but
note the release is blocked until win rates are acceptable, so a real
structural fix is expected here, not a deferral.

## Related (NOT this task — flag separately)

`RULES.md`'s training chapter is stale vs shipped Phase 1–3 (still
describes single-season training, no apprenticeship slot-pool /
Instructor gate, no profession-dependent duration, no 75% settling,
"Tutor" not "Instructor"). This is a separate doc-reconciliation task;
mentioned here only so it isn't conflated with balance work.

## Reference

- Runner: `island_traders/simulation/runner.py` (`--games/--years/
  --seed/--seeds/--charts`, writes `simulation_results/`).
- Event chart format: `island_traders/engine/events.py`.
- Calibration rationale: `requirements/release-process.md`, README
  "Tuning the event charts".
