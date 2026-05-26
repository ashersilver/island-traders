# Codex Task — Educator approval queue: drag-reorder pending list (2026-05-26)

**Owner:** Codex (engine) + Claude (UI follow-up)
**Origin:** 2026-05-26 playtest (`0.1.0-dev.2026-05-26`). User report: *"Education needs to be able to prioritize approvals and adjust the list awaiting approval."*

Today the Educator processes pending training requests in the order `TrainingRegistry` happens to return them (insertion order). When the Educator hits a capacity gate (no Course slots, no Expertise, no Lecturer staffing), the request is left in the queue and the loop moves on — but the *next* season the same arbitrary order is re-used. The user has no way to say "approve the Doctor training first, then the Farming Technician — skip the Banker Analyst request, it can wait."

## Goal

Add an explicit **priority** field on `TrainingRequest` that the Educator can set or change, and have the approval/dispatch loops walk the pending queue in priority order. Surface a drag-reorder UI in the dashboard so the Educator can rearrange the queue visually.

This is an *Educator-side* control. Requesters cannot set priority — they can only suggest it via the offered Dollops amount (which the existing flow already supports). Only the Educator can re-order their own pending list.

## Branching

- **Base:** `pre-release` at `ba74a59` (current head) or later. **Coordinate** with `codex/training-flow-diagnostic-2026-05-26` — that brief covers the broader pipeline; this one is purely additive (new priority field + queue sort). They shouldn't conflict, but pick whichever lands first as the base for the other.
- **Branch name:** `codex/educator-approval-queue-2026-05-26`
- **Target for merge:** `pre-release`. **Do not merge yourself.** Push the branch and stop. Claude will review.

## Spec

### `TrainingRequest.priority`

Add to `island_traders/models/training.py`:

```python
@dataclass
class TrainingRequest:
    ...
    priority: int = 0   # lower value = higher priority; ties broken by insertion order (batch_id)
```

`priority` defaults to `0` for backward compatibility. New requests come in at `0`; the Educator's reorder action mutates the value to express "this one first" (negative numbers / smaller integers move up). The engine never reads priority numerically — it only uses it as a sort key (`sorted(..., key=lambda r: (r.priority, r.batch_id))`).

### Queue sort

In every place the engine iterates pending requests for an Educator (look for `pending_for_educator`, `_action_review_training`, the AI Educator response loop, etc.), wrap the iteration with:

```python
pending = sorted(
    self.training.pending_for_educator(educator.player_id),
    key=lambda r: (r.priority, r.batch_id),
)
```

The AI Educator (`_ai_educator_respond`) uses the same sort so AI behaviour is predictable from the visible queue order.

### New mid-game action: `REORDER_TRAINING_QUEUE`

Add a new `TurnAction` (in the existing `engine/turn_action.py` or wherever the action enum lives). When the Educator chooses it, the IO adapter offers a structured payload representing the current pending list and accepts a new ordered list of `batch_id`s as the response. The engine then rewrites `priority` values so the response order is preserved (e.g. `req.priority = -idx` for the first item, etc.).

Action group: `People` (alongside `REVIEW_TRAINING_REQUESTS`).

### Server payload

The server's game-state payload for an Educator player should include a `training_queue_order` array — list of `{batch_id, requester_name, target_profession, priority, dollops_offered, requested_year, requested_season}` in current sort order. Claude's UI will render this as a drag-reorderable list.

For non-Educator players, this field can be omitted (or always empty) — only the Educator sees their own queue order.

### In-queue reject / counter (added 2026-05-26 follow-up)

The Educator must be able to **reject** or **counter** any pending request from the queue view itself, not just from the per-request approval modal. Today these decisions require the Educator to walk into the modal flow for each request individually — the user wants to triage the entire queue from one screen.

Add two more IO payload variants alongside the reorder action (these can be separate `TurnAction` values, or sub-actions of a single `MANAGE_TRAINING_QUEUE` umbrella — your call):

- `REJECT_TRAINING_REQUEST` — takes a `batch_id` + free-text reason. Marks the request `REJECTED` via the existing `training.educator_reject(batch_id)` path. The reason is stored on the request (new field `decline_reason: str = ""`) and surfaced back to the requester (see "Requester notification" below).
- `COUNTER_TRAINING_REQUEST` — takes a `batch_id` + the same fields the existing per-request counter-offer flow already takes (new `dollops_to_educator`, new ticket split, etc., whatever the existing counter-offer payload already carries) + an optional free-text reason. Marks the request `COUNTERED` and updates the offer values. Existing counter-offer notification path to the requester continues to apply.

Both actions must respect the same auth check as the modal flow: only the Educator the request was filed against can act on it.

### Requester notification (added 2026-05-26 follow-up)

When a request is **countered** or **rejected**, the requester needs an in-game signal they can't miss, plus enough information to re-bid intelligently. Today the engine just prints to the log channel, which scrolls away.

Engine changes:

- Add `decline_reason: str = ""` and `decline_year: int = -1`, `decline_season: int = -1` to `TrainingRequest` so the rejection metadata persists for the requester's UI.
- When the Educator rejects (modal flow or new in-queue flow), populate these fields *before* the `educator_reject` state transition fires.
- Server's player-state payload for the requester should include a `training_decisions` array: every counter / rejection of the requester's own requests, with `{batch_id, status, decline_reason, decline_year, decline_season, original_offer, suggested_offer_if_any, target_profession, n_workers}`. Acknowledged-and-dismissed entries can be filtered server-side (see "ack" below) so the array shrinks back to empty after the requester has seen them.
- Add a `ACK_TRAINING_DECISION` action keyed by `batch_id` so the requester can mark the notification as seen; the server then omits that entry from future `training_decisions` payloads.

Engine notifications must fire for both human and AI Educator paths — the AI Educator's existing reject log line is fine to keep, but it must also populate `decline_reason` (something like `"AI fair-rate threshold: needed {required_offer:.0f} Dp, offered {req.dollops_to_educator:.0f} Dp"`) so the requester sees a useful signal.

### Tests

- `tests/test_engine/test_training_priority.py`:
  - Pending requests sort by priority then batch_id.
  - `REORDER_TRAINING_QUEUE` action rewrites priorities so a chosen order is preserved across seasons.
  - The AI Educator processes requests in the same sorted order the human would see.
  - A request's priority survives a season boundary (priority is not reset).
  - A new incoming request lands at `priority=0` and appears in the sorted order accordingly.
- `tests/test_engine/test_training_queue_actions.py`:
  - `REJECT_TRAINING_REQUEST` from the queue marks the request `REJECTED` and stores the decline reason on the request.
  - `COUNTER_TRAINING_REQUEST` from the queue marks the request `COUNTERED` and updates the offer values.
  - Requester's `training_decisions` payload contains the decision the moment it fires.
  - `ACK_TRAINING_DECISION` removes a decision from the requester's payload on subsequent state pulls.
  - Auth: a non-Educator player cannot reject/counter requests filed against an Educator (no-op + logged refusal).
  - AI Educator rejections populate a sensible `decline_reason` string.

## Acceptance criteria

- `TrainingRequest.priority` field added with default `0`.
- All engine iteration over pending requests is priority-sorted.
- New `REORDER_TRAINING_QUEUE` action with a structured IO payload.
- New `REJECT_TRAINING_REQUEST` and `COUNTER_TRAINING_REQUEST` actions usable from the queue view.
- `TrainingRequest` carries `decline_reason`, `decline_year`, `decline_season`.
- Server payload exposes `training_queue_order` for the Educator and `training_decisions` for the requester.
- New `ACK_TRAINING_DECISION` action for the requester.
- AI Educator rejections populate `decline_reason`.
- Calibration sweep unchanged (this should not move the balance — it only changes processing order and surfaces existing reject/counter outcomes).
- Full test suite green at the new baseline count (442 + new tests).
- `RELEASE_NOTES.md` Unreleased section gets a new `### codex/educator-approval-queue-2026-05-26` block.

## UI follow-up (Claude will handle separately)

- New "Training queue" section in the Educator player card showing the current sorted list.
- Drag-and-drop reordering on that list, with each drop POSTing a `REORDER_TRAINING_QUEUE` response.
- Inline "Reject" and "Counter" buttons on each queue row, with a small reason-text input on Reject and the existing counter-offer modal on Counter.
- Visual chip for queue position ("Next" / "2nd in queue" / etc.) shown on each pending request card across all dashboards.
- A small "Priority" header on the existing approval modal showing where in the queue this request sits.
- **Requester-side notification:** a visual flag (badge / pulsing chip) on the requester's dashboard whenever `training_decisions` is non-empty. Clicking the flag opens a popup that lists each decision with the reason, the original offer, and an "Improve bid" button that opens a pre-filled new-request modal so the requester can re-submit with a stronger offer. Dismissing a decision posts `ACK_TRAINING_DECISION` to clear it from the badge.

## Out of scope

- Letting requesters set priority (they can already signal urgency with the Dollops offer).
- Auto-priority based on relationship score or trade history (interesting future feature; not for this brief).
- Cross-Educator queue sharing (multi-Educator teams already split the pending list per Educator; nothing changes there).
