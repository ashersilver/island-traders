# Codex Task — Event-frequency cap on production-halting disasters (2026-05-27)

**Owner:** Codex
**Origin:** [Triage `0.1.0-dev.2026-05-26.5`](../playtest-feedback/triage-0.1.0-dev.2026-05-26.5.md) §3.4. Two playtesters reported the same disaster-stacking problem:

- **Comet 1 #9** *(Low/Design)* — "In a single year, the game fired: Factory Fire → Infrastructure Damage → Flood → Flood → Hospital Strike in consecutive seasons. **Five consecutive production-halting events in ~5 seasons** effectively eliminated any meaningful play for the Manufacturer for an entire year."
- **Comet 1 IMP-4** — proposed fix: "max of 1 production-halt event per player per year, or a 'disaster insurance' product."
- **AyaySir BUG-08** *(Low/Design)* — "Pandemic, Factory Fire, and Infrastructure Damage events occurred in consecutive seasons while the training pipeline was also blocked, leaving multiple seasons with zero meaningful player actions available."
- **AyaySir IMP-10** — "Cap consecutive halt events."

The current event resolver (`engine/events.py:SeasonEventResolver.resolve_all`) draws from each role's chart independently each season with no cooldown or per-player budget. A combination of bad rolls produces "I literally cannot play" stretches.

## Goal

Add a cooldown mechanism on production-halting events such that no single player can be hit by more than **1 halt event per game year**, with a configurable per-role yearly budget. Soft mitigations (lower yield modifiers, infrastructure damage requiring repair) are unaffected — only events that result in a `0.0` yield modifier or full outage are gated.

## Branching

- **Base:** `pre-release` at `8b6fd37` (current head) or later.
- **Branch name:** `codex/event-frequency-cap-2026-05-27`
- **Target for merge:** `pre-release`. **Do not merge yourself.** Push the branch and stop. Claude will review.

## Spec

### What counts as a "production-halting" event

For the purposes of this cap, a halt event is any `EventResult` where:

- `outage == True`, OR
- `yield_modifier <= 0.1` (10% productivity floor — anything tighter than this is functionally a halt for a season).

Soft damage (e.g. the `Infrastructure Damage` 0.5 modifier in `resolve_all`) does NOT count and is unaffected.

### Yearly halt budget

Add a per-player halt-counter that resets each game year. Default budget = 1 halt event per year per player. Implementation suggestions:

- Track `_halt_events_this_year: dict[int, int]` keyed by `player_id` on `SeasonEventResolver` or on the engine's per-year state.
- In `resolve_all`, after the chart draws but before the result is committed to `results`, check the counter for that player. If a halt event is drawn and the counter is already at the budget, **re-draw** from the chart with halts filtered out (or substitute `EventResult("Normal Operations")` if no non-halt option exists).
- Re-draw at most 3 times to avoid infinite loops; if no non-halt result lands in 3 tries, return `EventResult("Normal Operations")`.
- Reset the counter at the start of each new game year (or wherever the season cycle ticks from Winter → Spring).

### Configurable

New constant in `island_traders/constants.py`:

```python
# Maximum production-halting events any single player can suffer per game year.
# A halt event is one with outage=True OR yield_modifier<=0.1.  Soft damage
# (yield_modifier ~0.5) is uncapped.  See SeasonEventResolver.
HALT_EVENTS_PER_PLAYER_PER_YEAR: int = 1
```

Per-role override possible later via a dict if calibration demands it, but **start with a single int** to keep the change small.

### Natural disaster (game-wide) interaction

`resolve_all` has a separate "natural_disaster" path that applies a half-yield modifier to every player not already outaged. That stays as-is — it's already a soft modifier (0.5), not a halt by the definition above.

### Logging

When a halt is suppressed by the cap, log it explicitly:

```
[EVENT] Suppressed halt event 'Factory Fire' for Mannyfact (1/1 halts already used this year). Drew 'Normal Operations' instead.
```

This makes the cap visible during playtest and lets us tune later.

### Files to touch (suggested)

- `island_traders/constants.py` — new `HALT_EVENTS_PER_PLAYER_PER_YEAR` constant.
- `island_traders/engine/events.py` — `SeasonEventResolver.resolve_all` and (probably) a small state addition to track the per-year counter.
- `island_traders/engine/game.py` — call site for resetting the counter at year boundary.
- Tests: new `tests/test_engine/test_event_frequency_cap.py`.

### UI follow-up (Claude separate)

- Show "Halt events used: 0/1 this year" on the player's dashboard so they know their resilience budget.
- Surface suppressed-halt log lines as a soft "We dodged a Factory Fire because your budget was full" toast (optional flavour).

## Tests

- `tests/test_engine/test_event_frequency_cap.py` (new):
  - Deterministic chart with 100% chance of a halt event: first season fires, second season suppressed with re-draw to "Normal Operations" (chart configured with that as the fallback).
  - Counter resets at year boundary: same chart fires once in Year 1, once in Year 2.
  - Soft damage (yield_modifier=0.5) does NOT count against the budget.
  - Natural-disaster game-wide event is unaffected (already soft).
  - Multi-player: each player has independent budget — player A's halt doesn't consume player B's.

## Acceptance criteria

- `HALT_EVENTS_PER_PLAYER_PER_YEAR = 1` enforced per the spec.
- Halt events log when suppressed.
- Calibration sweep (1000g seed 42 + 4-seed sweep): all roles still in [12 – 18%] band. The cap will RAISE Manufacturer / Educator / Doctor win rates slightly (they currently suffer worst from halt stacking) — retune if anything moves >2pp out of band.
- Full test suite green (463 + new tests).
- `RELEASE_NOTES.md` Unreleased section gets a new `### codex/event-frequency-cap-2026-05-27` block.

## Out of scope

- Disaster insurance product (the alternate mitigation Comet 1 IMP-4 suggested). Interesting future feature; not for this brief.
- Per-role budget variation (one int for now; can be made a dict later if calibration shows specific roles need more/less protection).
- Soft-event cooldowns (Infrastructure Damage stacking on Infrastructure Damage is currently fine because both are 0.5 modifier — annoying but not a halt).
- Cross-player disaster (natural_disaster) tuning — separate balance question.
