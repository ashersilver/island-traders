# Codex Task — Requester-side training-request withdrawal (2026-05-27)

**Owner:** Codex
**Origin:** [Triage `0.1.0-dev.2026-05-26.5`](../playtest-feedback/triage-0.1.0-dev.2026-05-26.5.md) §3.6. Reported by AyaySir (Mining):

- **BUG-05** *(Medium)* — "Both 'Reject Training Request' and 'Counter Training Request' are Educator-only actions. The requester cannot withdraw a submitted request. If the Educator is inactive or resource-blocked, the requester is locked out of workforce development indefinitely."
- **IMP-01** — "Add a 'Withdraw Training Request' action for requesters. Requesters must be able to cancel their own pending training requests when the Educator is inactive or resource-blocked."

The `educator-approval-queue-2026-05-26` brief (already merged as PR #41) added Reject + Counter from the Educator side; this is the **symmetric requester-side action** that's still missing. Small brief — could equally have been folded into the queue brief as an amendment, kept separate here to ship faster.

## Goal

Add a `WITHDRAW_TRAINING_REQUEST` action keyed by `batch_id` and callable only by the request's original requester. Cleanly releases workforce reservations and refunds anything that hasn't been irreversibly consumed.

## Branching

- **Base:** `pre-release` at `8b6fd37` (current head) or later.
- **Branch name:** `codex/training-request-withdraw-by-requester-2026-05-27`
- **Target for merge:** `pre-release`. **Do not merge yourself.** Push the branch and stop. Claude will review.

## Spec

### New action

`TurnAction.WITHDRAW_TRAINING_REQUEST` with payload `{batch_id: int}`. Action group: `People` (same group as the existing training actions).

### State transitions

Allowed source states (request can be withdrawn while in):

- `PENDING` (Educator hasn't responded yet)
- `COUNTERED` (Educator counter-offered; requester can withdraw instead of accepting / rejecting)
- `AWAITING_DISPATCH` (Educator approved; dispatch hasn't happened yet because of tickets/seats shortage)

Forbidden source states (request cannot be withdrawn from):

- `DISPATCHED` (workers are physically at the Educator island — too late to withdraw, must wait for training to complete or be rejected by the Educator).
- `COMPLETED` / `REJECTED` / any terminal state.

When withdrawn, the request transitions to a new `WITHDRAWN` status. `WITHDRAWN` is terminal (same as `REJECTED`).

### Refund semantics

When a request transitions to `WITHDRAWN`:

- **Dollops paid to Educator (training fee)**: if approval already fired (status was `AWAITING_DISPATCH`), the fee is NOT refunded — the Educator already committed Course slots and Expertise to the batch. If approval has not yet fired (`PENDING` / `COUNTERED`), no fee was paid; nothing to refund.
- **Dollops paid to Transporter**: same logic — if transport already booked, not refunded.
- **PassengerSeats**: same — only consumed at dispatch, so withdraw-before-dispatch returns nothing because nothing was taken.
- **Worker reservations**: ALWAYS released. The reserved workers return to the requester's eligible-for-training pool immediately.
- **Educator's committed Course slots and Expertise**: if approval already fired, the Educator's Course / Expertise consumption stays consumed (sunk cost — they put together a class that's now empty). The Course slot is **not** returned to inventory.

This is intentional: withdrawing late should be a cost-bearing action, so withdrawal doesn't become a free abort mechanic.

### Authorization

Only the original `requester_id` on the `TrainingRequest` can withdraw it. Anyone else attempting the action gets a clear refusal:

```
[REFUSED] Only the original requester can withdraw training request #N (requested by Player {requester_name}).
```

### Server payload

Add `can_withdraw: bool` per pending-request entry in the requester's `training_pipeline_health` payload (see `training-expertise-deadlock-2026-05-27` brief — if that ships first, just extend the existing payload; if not, add the field on whatever existing requester-side payload carries the pending list).

### Files to touch (suggested)

- `island_traders/models/training.py` — add `TrainingStatus.WITHDRAWN`; new `TrainingRegistry.requester_withdraw(batch_id, requester_id)` method.
- `island_traders/engine/turn.py` — new `_action_withdraw_training_request` handler.
- `island_traders/server/app.py` — wire the new action through the WS contract.
- `island_traders/cli/prompts.py` — Fake adapter symmetry for tests.
- Tests: new `tests/test_engine/test_training_withdraw.py`.

### UI follow-up (Claude separate)

- "Withdraw" button on each of the requester's pending request rows on the dashboard, enabled per `can_withdraw`. Confirm dialog warning about non-refunded fees when applicable.

## Tests

- `tests/test_engine/test_training_withdraw.py` (new):
  - Withdraw from PENDING releases worker reservations, no Dp movement.
  - Withdraw from COUNTERED releases worker reservations, no Dp movement.
  - Withdraw from AWAITING_DISPATCH releases reservations BUT fee paid to Educator stays paid; Course/Expertise stays consumed.
  - Withdraw from DISPATCHED refused with clear message.
  - Withdraw from terminal state refused.
  - Authorization: non-requester attempting WITHDRAW refused.
  - `can_withdraw` field correctly populated in the requester's payload.

## Acceptance criteria

- New action lands end-to-end with all the state-transition cases tested.
- Withdrawal does NOT silently refund Educator-side committed resources — only requester-side reservations are released.
- `can_withdraw` field in the requester payload so the UI can show / hide the button correctly.
- Full test suite green (463 + new tests).
- No calibration drift (this is a flow control action, not a balance change).
- `RELEASE_NOTES.md` Unreleased section gets a new `### codex/training-request-withdraw-by-requester-2026-05-27` block.

## Out of scope

- Requester-supplied Expertise to unblock Educator (that's the separate `training-expertise-deadlock-2026-05-27` brief).
- Bulk withdraw (one batch at a time for now).
- Automatic withdrawal on long-pending requests — keep it player-driven for now; an "auto-withdraw after N seasons" policy can come later if playtesting shows it's needed.
