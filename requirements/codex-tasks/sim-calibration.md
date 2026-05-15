# Codex Task — Simulation Calibration

**Goal:** Tune `config/event_charts.yaml` until AI-only games produce
roughly equal win rates across all 7 islands (target ≈ 1/7 ≈ 14% per role).

## Background

The simulation runner runs N AI-only games and writes per-role win
statistics to a CSV.  The event charts haven't been recalibrated since
several major changes landed on `pre-release`:

- 2-season starting inventory for every island
- ForgeHaven product lines (Manufacturer now produces 5 distinct
  capital-equipment outputs)
- Metal as a Mining-island intermediate (Manufacturer consumes Metal,
  not raw Ore)
- Loans / Insurance / Capital purchases mid-game
- Post-auction Island Guarantee (§19.1)
- Workforce baseline ≥1 Manager + 2 Technicians, with the new transport
  professions (Logistics Manager / Flight Crew / Seaman / Warehouse
  Manager) and Educator / Banker / Doctor technician backfills

Cumulatively these likely shift the balance — re-calibration is overdue.

## Branch

- **Base:** `pre-release` (latest at HEAD on `origin`)
- **Branch name:** `codex/sim-calibration` (please use the `codex/` prefix
  so it's visually distinct from Claude's `claude/` branches)
- **Target for merge:** `pre-release`

## Files in scope

- `config/event_charts.yaml` — **primary tuning surface**
- `island_traders/simulation/runner.py` — fine to extend for richer
  stats (e.g. a `--summary` flag, multi-seed support)
- `tests/test_simulation/` — add tests if you want a regression guard
- `RELEASE_NOTES.md` — add a `### codex/sim-calibration` section
  describing before/after, before merging

## Files OUT of scope (Claude is actively editing these)

- `island_traders/server/` (entire directory)
- `island_traders/engine/turn.py`
- `island_traders/models/loan.py`, `models/insurance.py`, `models/profession.py`
- `island_traders/constants.py` (unless you find an outright bug)
- `RULES.md`, `README.md`

If you discover something that requires touching files in the OUT-of-scope
list, please leave a note in `RELEASE_NOTES.md` and coordinate before
merging — don't force the change through.

## Suggested workflow

1. **Baseline run** to capture current state:
   ```bash
   .venv/bin/island-traders-sim --games 1000 --seed 42
   ```
   Inspect the CSV in `simulation_results/`.  Note current win rates per role.

2. **Diagnose** which roles are over / underperforming.  Common causes:
   - Yield modifiers too generous or harsh in a role's event chart
   - Disaster / outage frequency mis-tuned for a role
   - A role's starting inventory + 2-season runway exposing it more than
     others

3. **Adjust** weights in `config/event_charts.yaml`.  The file format is
   per-role event lists with `weight` (probability) and `yield_modifier`
   (multiplier on output).  Some entries include `outage`, `damage_seasons`,
   `natural_disaster`, `price_shock_resource`/`price_shock_multiplier`.

4. **Iterate** with the same seed first (`--seed 42`) to compare apples
   to apples.  Once a single seed looks balanced, verify on 2-3 other
   seeds (`--seed 1`, `--seed 7`, `--seed 99`) to confirm it's not a
   seed-specific artifact.

5. **Final calibration run** at higher game count:
   ```bash
   .venv/bin/island-traders-sim --games 5000 --seed 42
   ```

## Acceptance criteria

- ✅ **Win rate per role within ±5pp of 1/7 (≈14%)** on a 5000-game run
  with `--seed 42`.
- ✅ Same balance holds (within ±5pp) on at least 2 other seeds (e.g.
  1 and 99) at 1000+ games each.
- ✅ No role at <8% or >22% in any of the verification runs.
- ✅ All existing tests pass: `.venv/bin/python -m pytest tests/` (target
  233 passing or better).
- ✅ `RELEASE_NOTES.md` has a new `### codex/sim-calibration` section
  with before / after win-rate tables for at least one seed.

## Optional extras (nice to have)

- `--summary` flag on the simulation runner that prints a tidy win-rate
  table to stdout in addition to the CSV.
- `--seeds 42,1,7,99` form that runs all seeds and aggregates.
- A regression test e.g. `tests/test_simulation/test_win_rates_balanced.py`
  that runs ~500 games and asserts each role is within ±10pp of 1/7.

## What to do if stuck

- If certain roles are structurally over/under-powered and event-chart
  tuning isn't enough, **stop** and write up the diagnosis in
  `RELEASE_NOTES.md` under a "Known follow-ups" subsection.  Coordinate
  with Claude before touching production formulas, `constants.py`,
  starting inventories, or capital catalogue values.

## Hand-off

When the branch is ready:

1. `git add -A && git commit ...`
2. `git push -u origin codex/sim-calibration`
3. Either open a PR to `pre-release` or merge locally and push
   `pre-release` directly (the established workflow this session has been
   local merges + push).
4. The branch should be conflict-free with Claude's work — the only
   shared file is `RELEASE_NOTES.md`, and adding a new section header
   never conflicts as long as it goes at the top of the `## Unreleased`
   block.

## Reference

- Event chart format: see `island_traders/engine/events.py`
  (`EventChartLoader`).
- Simulation runner: `island_traders/simulation/runner.py`.
- Calibration target rationale: `requirements/release-process.md`,
  and the "Tuning the event charts" section in `README.md`.
