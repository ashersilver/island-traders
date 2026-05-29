# Codex Task — Training Expertise deadlock + system-wide visibility (2026-05-27)

**Owner:** Codex
**Origin:** [Triage `0.1.0-dev.2026-05-26.5`](../playtest-feedback/triage-0.1.0-dev.2026-05-26.5.md) §3.2. Reported by two playtesters running different roles:

- **AyaySir (Mining)** BUG-04: training requests #6–#9 (4 Mining Technicians + 1 Oil Extraction Worker) stayed at `awaiting_educator` from Year 1 Summer through Year 3 Autumn — **nine consecutive seasons** of deadlock. Reason logged: "Education Island needs 1 Expertise." Expertise never appeared in the market, no mechanism to substitute/unblock/cancel.
- **Codex Player (Banking)** defects: "Training dependencies got stuck around Expertise. Education could not approve requests, including my Banker training, and the UI did not make the system-wide bottleneck very actionable."

This is a **total-system deadlock** — once the Educator runs out of Expertise, every training request from every island freezes indefinitely. PR #37 (`training-flow-diagnostic`) added seasonal AI Educator review + state logging, but the underlying Expertise supply chain was not addressed.

## Goal

Three layers of fix, deepest to shallowest:

1. **Find and fix the Expertise production blocker.** Walk the Educator's own production chain (LabEquipment input → Expertise output) and identify why the AI Educator stops producing Expertise. Common suspects:
   - LabEquipment not being supplied by Manufacturer (PR #46 was supposed to fix this for human-demand cases but the playtest may have triggered the all-AI path)
   - LabEquipment lifespan expired (capital decay)
   - Workforce shortage on Educator (Lecturer / Professor attrition)
   - Educator AI not prioritising its own production action when training requests are pending

2. **Add a substitute path so deadlock can't recur.** When Expertise is the only blocker for a pending training batch, let the **requester** supply Expertise from their own inventory (AyaySir IMP-03). Creates an inter-island market dynamic and gives the requester an escape hatch.

3. **Surface the bottleneck explicitly on the requester's dashboard.** Today the requester sees `awaiting_educator` and a single static blocker reason; they have no way to know whether the blocker is recurring season-to-season or about to clear, what *system-wide* resource shortage is in play, or what they can do about it.

## Branching

- **Base:** `pre-release` at `8b6fd37` (current head) or later.
- **Branch name:** `codex/training-expertise-deadlock-2026-05-27`
- **Target for merge:** `pre-release`. **Do not merge yourself.** Push the branch and stop. Claude will review.

## Spec

### Layer 1: diagnose-and-fix the Expertise pipeline

Add explicit logging on every Educator production gate (input shortage, workforce shortage, capital decay) so the chain of failure is visible in the game log. Then run a 5-year simulation with 1 human Mining player + 6 AI players, all filing training requests every season, and confirm Expertise production never permanently halts.

If the cause is PR #46's human-demand scoping (AI Manufacturer ignores LabEquipment when only AI players need it), the right fix is probably to widen the demand signal to include *indirect* human demand: a human Miner's pending training request creates upstream Expertise demand, which creates upstream LabEquipment demand on the Manufacturer. PR #46 only looked at *direct* product consumption.

### Layer 2: requester-supplied Expertise (AyaySir IMP-03)

When `_training_capacity_status` returns `False` with reason `"needs {N} Expertise for this course"`, the requester gets a new action option on their dashboard:

- "Supply {N} Expertise to Educator {educator_name}"
- Enabled only if `requester.inventory.get(ResourceType.EXPERTISE) >= N`
- On confirm: requester's Expertise moves to Educator's inventory at zero cost (it's a gift to unblock). The `educator_approve` path then re-runs and the request proceeds normally.

Engine-wise:
- New `TurnAction.SUPPLY_TRAINING_EXPERTISE` action with payload `{batch_id, qty}`.
- Authorization: only the request's original `requester_id` can supply.
- State transition: this does NOT count as approval; the Educator still has to approve (or auto-approve next season if AI).

Same pattern could later extend to other Educator inputs (LabEquipment, Courses) but **this brief is Expertise only** to keep scope small.

### Layer 3: requester-side bottleneck visibility

Add a `training_pipeline_health` payload to the server's player-state delivery whenever the player has any pending training requests. Shape:

```python
training_pipeline_health = {
    "pending_count": int,
    "blockers": [
        {
            "batch_id": int,
            "educator_name": str,
            "reason": str,           # the current _training_capacity_status reason
            "seasons_blocked": int,  # how many seasons this batch has been pending
            "can_supply_expertise": bool,  # true if Layer 2 supply action would work
        },
        ...
    ],
}
```

When any batch is blocked ≥3 seasons, the dashboard can show a prominent "Pipeline blocked: N seasons" indicator — that's a UI follow-up but the payload should ship with this engine work.

### Files to touch (suggested)

- `island_traders/engine/turn.py` — `_training_capacity_status` logging, new `SUPPLY_TRAINING_EXPERTISE` action wiring.
- `island_traders/engine/ai.py` — widen demand signal in `_ai_manufacturer_*` to include training-pipeline-driven LabEquipment demand.
- `island_traders/models/training.py` — track `seasons_blocked` counter per request (or compute on demand from request creation time + current tick).
- `island_traders/server/app.py` — add `training_pipeline_health` to player payload.
- `island_traders/cli/prompts.py` — Fake adapter for the new action.

### UI follow-up (Claude separate)

- "Pipeline blocked: X seasons — supply N Expertise yourself" badge on the requester's dashboard.
- "Supply Expertise" button inline on each blocked batch row.
- System-wide hint on the Educator's dashboard: "N pending requests blocked on Expertise (you have M; produce N-M more to clear)".

## Tests

- `tests/test_engine/test_training_expertise_deadlock.py` (new):
  - End-to-end: 5-year simulation, 1 human Miner + 6 AI, training requests every season. Expertise production never permanently halts. No batch stays pending >5 seasons.
  - Supply path: Miner with 2 Expertise on hand supplies it to Educator with 0 Expertise → blocked training batch unblocks next season.
  - Authorization: a non-requester player attempting `SUPPLY_TRAINING_EXPERTISE` against someone else's batch is refused.
  - Payload: `training_pipeline_health` correctly reports `seasons_blocked` and `can_supply_expertise`.
- Regression: existing PR #37 tests still pass.

## Acceptance criteria

- Layer 1 fix lands: simulation confirms Expertise pipeline doesn't permanently halt over 5 years with mixed human/AI play.
- Layer 2 `SUPPLY_TRAINING_EXPERTISE` action works end-to-end with authorization checks.
- Layer 3 `training_pipeline_health` payload populated in player-state delivery.
- Diagnostic logging at every Educator production gate so future deadlocks are visible immediately.
- Full test suite green (463 + new tests).
- Calibration sweep (1000g seed 42 + 4-seed sweep): all roles still in [12 – 18%] band.
- `RELEASE_NOTES.md` Unreleased section gets a new `### codex/training-expertise-deadlock-2026-05-27` block.

## Out of scope

- Allowing requester to supply LabEquipment, Courses, or PassengerSeats (Expertise only for this brief — same pattern extends later).
- Allowing arbitrary third-party players to supply Expertise (only the requester, to keep accountability simple).
- Reworking the AI Manufacturer's demand chooser more broadly (PR #46's scoping decision was deliberate; this brief just extends the demand signal upstream by one hop).
- AyaySir's broader "system-wide bottleneck visibility" might want a higher-level dashboard later but the per-request `training_pipeline_health` payload is the right first cut.
