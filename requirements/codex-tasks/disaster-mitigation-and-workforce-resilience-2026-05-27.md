# Codex Task — Disaster mitigation + workforce resilience (2026-05-27)

**Owner:** Codex
**Origin:** 2026-05-27 Comet playtest feedback ("Flood as a game mechanic") + 2026-05-27 Manny Fracture / Manufacturer playtest report ("Mining had 0 active workers for virtually the entire 5-year game"). Both point at the same underlying gap: the engine has no soft-landing for catastrophic workforce loss, and no insurance product that actually *reduces* the loss rate.

## Goal

Three engine changes to make catastrophic single-event and slow-bleed workforce loss survivable:

1. **Soften Flood-class events.** A `natural_disaster: true` event with `outage: true` + `yield_modifier: 0.0` + cascading `0.5` modifier to every other island is too brutal. One bad roll late game leaves no recovery time. Add per-event-class severity tiers so disasters can be "tough but recoverable" rather than "binary wipeout."
2. **Make Life Insurance actually reduce fatality rate** (not just pay a death benefit). The current Life policy is a payout-only mechanism — the worker still dies, the player just gets cash. Players need a way to *prevent* the death, like Medical Insurance does for injuries.
3. **Per-event-per-player workforce-loss cap.** A single natural-disaster firing + concurrent workplace-risk rolls can wipe most of a starting workforce in one tick. Cap losses from any single event at, say, 30 % of active skilled workers so the player retains some core team to rebuild from.

## Branching

- **Base:** `pre-release` at `0.1.0-dev.2026-05-27.4` head or later.
- **Branch name:** `codex/disaster-mitigation-and-workforce-resilience-2026-05-27`
- **Target for merge:** `pre-release`. **Do not merge yourself.** Push the branch and stop. Claude will review.

## Spec

### Fix 1: Disaster severity tiers

Today `config/event_charts.yaml` Flood entry has:
```yaml
- name: "Flood"
  weight: 0.05
  yield_modifier: 0.0      # full production halt
  outage: true             # AI/turn-skip flag
  damage_seasons: 1        # next season at 0.5 too
  natural_disaster: true   # cascades 0.5 to all other islands
  price_shock_resource: "Food"
  price_shock_multiplier: 1.8
```

So a single Flood gives the originating player two halt-equivalent seasons AND every other island a 0.5 season. That's harsh enough late-game to be unrecoverable.

Proposal: introduce a new YAML field `severity` taking values `light` (≤25 % yield drag), `medium` (~50 %), `heavy` (≤75 %), `catastrophic` (current 0.0 + outage behaviour). Then:

- Re-tier `Flood` from `catastrophic` to `heavy` by default: `yield_modifier: 0.25`, `outage: false`, `damage_seasons: 1` (next season 0.5).
- Keep `catastrophic` available as a YAML option for future use, but no event uses it today.
- The natural-disaster cascade on OTHER islands stays at 0.5 — that's not the painful part.

This is intentionally a calibration change, not a mechanic redesign. After landing, run the 4-seed sweep and confirm no role drifts outside the [12-18 %] band.

### Fix 2: Life Insurance reduces fatality rate

Today (`workforce_events.py:113-141`):
```python
base_fatal = role_risks["fatality_rate"]
fatality_candidates = [...]
deceased = [w for w, p in fatality_candidates if rng.random() < p]
# Life insurance only triggers the death-benefit payout AFTER the death.
```

Change: when the player holds Life insurance, multiply the per-worker fatality probability by `(1.0 - LIFE_INSURANCE_FATALITY_REDUCTION)` before rolling, mirroring how Medical insurance halves injuries. Reasonable default: 50 % reduction (so Mining fatality at 0.08 → 0.04 with a Life policy in force). Add a new constant:

```python
LIFE_INSURANCE_FATALITY_REDUCTION: float = 0.50
```

The death-benefit payment path stays as-is — it fires on the survivors of the rate-reduced roll.

### Fix 3: Per-event-per-player workforce-loss cap

Add a hard cap in `apply_workplace_risks` so a single bad roll can't wipe too many of a player's active workers at once. Suggested cap:

```python
MAX_WORKFORCE_LOSS_PER_TICK_FRACTION: float = 0.30
```

After collecting `deceased` list:
```python
max_deaths = max(1, math.floor(len(active_at_start) * MAX_WORKFORCE_LOSS_PER_TICK_FRACTION))
if len(deceased) > max_deaths:
    # Keep the most-experienced workers; drop the rest from this tick's
    # fatality list (they survive this season, may still die later).
    deceased.sort(key=lambda w: w.age_seasons, reverse=True)  # oldest first
    deceased = deceased[:max_deaths]
    # Log the cap firing for visibility.
    report.cap_applied = True
    report.cap_threshold = max_deaths
```

`max(1, ...)` keeps the cap meaningful for small workforces (a 5-worker island can lose at most 1 per tick at 30 %).

### Logging + visibility

When workers leave a roster, the in-game log should say WHY so the player can decide which insurance to buy:

```
[WORKFORCE] Mining lost 2 worker(s) to workplace fatalities this season.
  - Sam (Miner, age 18 seasons): Life insurance paid 50 Dp death benefit.
  - Pat (Pit Worker, age 7 seasons): no Life insurance.
[WORKFORCE] Cap applied: would have lost 4, kept 2 (30% / tick cap).
```

This was implicit before (just "2 worker fatality/fatalities" in `WorkforceEventReport.summary()`). Make it explicit so the next playtest report can be specific about the cause.

### Files to touch (suggested)

- `island_traders/constants.py` — new constants `LIFE_INSURANCE_FATALITY_REDUCTION`, `MAX_WORKFORCE_LOSS_PER_TICK_FRACTION`.
- `config/event_charts.yaml` — re-tier Flood (and audit other halt-class events).
- `island_traders/engine/workforce_events.py` — apply Life-insurance reduction + per-tick cap.
- `island_traders/engine/events.py` — optional `severity` field on EventResult for downstream display.
- `island_traders/server/app.py` — surface per-tick cap firing on the game log.
- Tests: new `tests/test_engine/test_disaster_mitigation.py` covering all three fixes + a regression sim.

### UI follow-up (Claude separate)

- Workforce panel shows "Recent losses: 2 workers (1 injury, 1 retirement, 0 fatalities)" so the player can see attrition cause at a glance.
- Insurance recommendations contextualised by the player's role's risk rate ("Mining: Life insurance halves fatality risk").

## Tests

- `tests/test_engine/test_disaster_mitigation.py` (new):
  - Flood at the new `heavy` severity does NOT zero production — yield_modifier 0.25 applies, damage cycle still triggers, but the player retains 25 % output.
  - Life insurance halves per-worker fatality probability.
  - Per-tick cap: with 10 active workers and a fatality_rate that would normally kill 5, only 3 die (`floor(10 × 0.3)`).
  - Log lines mention each lost worker by name + cause + insurance status.
- Regression on existing tests:
  - `WORKPLACE_RISK` math tests stay green (fatality math is unchanged for uninsured players).
  - Calibration sweep (1000g seed 42 + 4-seed sweep) shows all roles still in [12-18 %] band. Softer Flood will help Farmer / Manufacturer / Doctor (the high-risk roles); recalibrate if anything drifts more than ±2 pp.

## Acceptance criteria

- Three fixes land independently and each has a dedicated regression test.
- A simulation playtest: 5-year run with Manny-Fracture-style Mining setup (no Educator training, just attrition) — Mining still has > 0 active workers at game end.
- Full test suite green at the new baseline count (475 + new).
- Calibration sweep within band.
- `RELEASE_NOTES.md` Unreleased section gets a new `### codex/disaster-mitigation-and-workforce-resilience-2026-05-27` block.

## Out of scope

- A new "Disaster insurance" product (separate from Life/Medical) — could come later if the per-tick cap + Life-insurance reduction isn't enough.
- Catastrophic-tier events (kept as a YAML option but no event uses it today).
- Replacement-worker mechanics (hire from other islands etc.) — covered by GitHub issue #50 separately.
- Graceful-degradation-on-missing-expertise (covered by GitHub issue #47 + the new `graceful-degradation-2026-05-27.md` brief).
