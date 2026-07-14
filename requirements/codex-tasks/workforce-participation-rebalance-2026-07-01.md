# Brief — Rebalance economy after WORKFORCE_PARTICIPATION_RATE change (2026-07-01)

**Suggested owner:** Codex (engine: economic balance tuning via simulation).
**Base off:** `origin/pre-release` at `0d14b33` (APP_VERSION `0.1.5-dev.2026-06-22.17`
— confirm current tip before starting; a same-day Claude commit adds the
`WORKFORCE_PARTICIPATION_RATE` constant this brief is about, so the actual
base will be one commit past `0d14b33`).
**Tracking issue:** none filed yet — file one titled "Rebalance role win rates
after workforce participation rate change" if not already open, and close it
in the PR.
**Pairs with:** none — engine-only balance tuning, no frontend changes expected.

> **Process:** See `requirements/codex-tasks/_README.md` — that file is the
> standing working agreement and overrides anything here on process.

---

## Context

A 2026-07-01 playtest note asked: "Workers should no longer include the whole
population of the island, perhaps start with 50% of the population." Previously
the starting workforce for every role was seeded at 100% of `STARTING_POPULATION`
(50 workers in a 50-person population) — already inconsistent with the
existing `MAX_WORKFORCE_FRACTION_OF_POPULATION = 0.60` recruiting cap, which
assumed a smaller starting workforce than what was actually seeded.

**What changed (already applied, do not revert):**
- New constant `WORKFORCE_PARTICIPATION_RATE: float = 0.50` in `constants.py`
  (near `MAX_WORKFORCE_FRACTION_OF_POPULATION`, ~line 661).
- `Game.setup()`'s `workforce_scale` (previously hardcoded `1.0`) now reads
  `WORKFORCE_PARTICIPATION_RATE` (`engine/game.py`, ~line 243). This uniformly
  scales both `STARTING_WORKFORCE` totals and each named profession's seed
  count in `STARTING_WORKERS_BY_PROFESSION`, so the calibrated
  manager/technician/worker *ratios* within each role are preserved — only
  the absolute headcount shrinks.
- Full pytest suite (854 tests) passes unchanged with this in place — no
  hardcoded workforce-count assumptions broke.

**What's broken: win-rate balance.** Simulation runs (`python -m
island_traders.simulation.runner --games 300 --seed 42`) show a **clear,
monotonic relationship** between `workforce_scale` and Banker's win-rate
advantage — the lower the workforce, the more Banker dominates and the more
production-dependent roles (Doctor, Manufacturer, Miner) get starved:

| workforce_scale | Farmer | Miner | Transporter | Educator | Banker | Manufacturer | Doctor |
|---|---|---|---|---|---|---|---|
| 1.00 (old baseline) | 20.7% | 11.3% | 13.7% | 16.7% | 17.3% | 9.7% | 10.7% |
| 0.75 | 19.3% | 9.3% | 10.3% | 17.0% | 21.7% | 11.3% | 11.0% |
| 0.50 (current)      | 17.0% | 8.0% | 12.0% | 16.0% | 30.0% | 10.7% | 6.3% |

(1/7 ≈ 14.3%; the existing calibration target is ±6pp, i.e. 8.3%–20.3%.)

Even the old 1.0 baseline was borderline (Farmer +6.4pp over target), but
0.50 is badly out of band: Banker at 30% (+15.7pp) and Doctor at 6.3%
(−8pp). This needs real rebalancing, not a different constant value — halving
workforce makes Banker's income (not workforce/production-bound the same way
as other roles) relatively far more attractive while starving roles that
depend on production throughput.

---

## What to investigate and tune

1. **Why Banker scales up as workforce shrinks.** Banker's income sources
   (loan interest, insurance premiums, underwriting) likely don't scale down
   with workforce the way Farmer/Miner/Manufacturer/Doctor production does.
   Check `island_traders/models/player.py` and whatever computes Banker's
   per-season income — does it reference `workforce.count`,
   `production_capacity`, or is it purely capital/dollops-driven? If purely
   capital-driven, Banker effectively gets the same income regardless of
   workforce scale while every production role's output shrinks — that's the
   likely root mechanism.

2. **Why Doctor and Miner get squeezed hardest.** Check `SEASONAL_WORKFORCE`
   requirements in `constants.py` (workforce needed per season per role to
   meet demand) — these were calibrated assuming ~50 starting workers. At 25
   workers (0.50 scale), do Doctor/Miner fall below the threshold needed to
   satisfy seasonal demand at all, effectively capping their output much more
   severely than roles with lower seasonal requirements? A `grep -n
   "SEASONAL_WORKFORCE" island_traders/constants.py` and cross-reference
   against the new (halved) starting workforce per role is the first thing to
   check.

3. **Candidate fixes to test (in order of likely first attempt):**
   - Scale `SEASONAL_WORKFORCE` requirements down by the same
     `WORKFORCE_PARTICIPATION_RATE` factor so the ratio of
     available-workforce-to-required-workforce stays constant across the
     scale change (this is probably the most direct fix and should restore
     most of the balance without touching Banker at all).
   - If Banker is still over-performing after the above, look at whether
     Banker's income should scale with something workforce-adjacent (e.g. cap
     total loan/insurance book size by island population or workforce) rather
     than being effectively workforce-independent.
   - Do NOT touch `STARTING_WORKERS_BY_PROFESSION`'s relative ratios (the
     Educator Professor/Lecturer/TechnicalDirector/Instructor mix in
     particular has a documented anti-deadlock rationale, see the comment
     block above that constant in `constants.py`) — tune via
     `SEASONAL_WORKFORCE` or `WORKFORCE_PARTICIPATION_RATE` itself, not the
     per-profession breakdown.

4. **Re-run the simulation after each candidate fix**:
   ```
   .venv/bin/python -m island_traders.simulation.runner --games 1000 --seed 42
   ```
   Target: every role within ±6pp of 1/7 (~14.3%), i.e. 8.3%–20.3%. Report
   the before/after win-rate table (same shape as above) in the PR
   description and in `RELEASE_NOTES.md`.

5. If ±6pp isn't achievable purely by scaling `SEASONAL_WORKFORCE`, it's fine
   to also tune `WORKFORCE_PARTICIPATION_RATE` itself away from exactly 0.50
   (e.g. 0.60 or 0.65) as a secondary lever — the playtest ask was "perhaps
   50%," not an exact requirement — but exhaust the `SEASONAL_WORKFORCE`
   angle first since that's the more targeted fix and keeps workforce closer
   to the requested halving.

---

## Tests to write

Add to an existing or new `tests/test_engine/test_workforce_participation.py`:

1. `Game.setup()` seeds `workforce.count` at (approximately, given rounding)
   `WORKFORCE_PARTICIPATION_RATE × STARTING_WORKFORCE[role]` for each role.
2. Named profession seed counts in `STARTING_WORKERS_BY_PROFESSION` are scaled
   by the same factor (spot-check Educator: Professor/Lecturer counts should
   reflect the new `workforce_scale`, not the raw constant values).
3. Whatever `SEASONAL_WORKFORCE` change is made: assert the new values are
   the old values scaled by the chosen factor (documents the relationship
   going forward so it doesn't silently drift out of sync on a future
   `WORKFORCE_PARTICIPATION_RATE` change).

Full suite must still pass: `pytest`.

---

## What Claude does next (do not implement)

Nothing — this is a pure engine/balance fix with no frontend surface. Once
merged, Claude will confirm the new simulation numbers look reasonable and
update the running test game if one is active.
