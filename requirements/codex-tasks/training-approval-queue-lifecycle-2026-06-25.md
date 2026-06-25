# Brief — Fix training approval/queue lifecycle (pending requests vanish) (2026-06-25)

**Owner:** Codex (training engine + tests). **Process:** see `_README.md` in this dir.
**Base off:** `origin/pre-release` — `git fetch origin`, confirm `git rev-parse --short
origin/pre-release` and the `APP_VERSION`, and quote both in your handoff. Work in your own
worktree; push your branch.

## Why (observed 2026-06-25)

The Educator's training approval queue loses pending requests:
- After **reordering** the queue, approving says **"nothing to approve."**
- Making a **new request** then **closing the review box without deciding** leaves the queue
  **empty** (the request is gone from the pending set). It only recovered after the user
  **rejected all** via "reject training" and re-added fresh requests.

So a pending request is being dropped from / wrongly transitioned out of the
`awaiting_educator` set by the reorder action and/or by opening-then-closing the review
without a decision.

## Where to look

- `island_traders/engine/turn.py`: `_action_review_training` (~615), `_action_reorder_training_queue`
  (~617), `_approve_training_request` (~2291), `_review_training_counteroffers` (~2361).
- `island_traders/models/training.py`: `TrainingStatus.AWAITING_EDUCATOR`, `educator_approve`
  (~356), `reorder_pending` (~616).
- `island_traders/server/app.py` ~2338 (`req.status.value == "awaiting_educator"` rendering),
  and the WS handlers that drive REVIEW_TRAINING / REORDER from the dashboard.

## Spec

1. **Reorder must be status-preserving.** `reorder_pending` (and the action that calls it) must
   only change ordering — never drop a request from, or change the status of, the pending
   (`awaiting_educator`) set.
2. **Review-without-decision is a no-op.** Opening the review prompt and closing it (cancel / no
   choice / timeout) must leave every still-pending request as `awaiting_educator` and
   re-reviewable next time. Nothing should consume/expire a request just because the prompt was
   shown.
3. **Approving/rejecting one keeps the rest.** Acting on one batch must not clear the others
   from the queue.
4. **Diagnose the exact transition** that currently drops them (likely the action loop marking
   the request handled, or reorder rebuilding the list and losing entries) and fix at the
   source; describe it in the PR.

## Tests
- Reorder a 3-request pending queue → all 3 still `awaiting_educator`, new order applied.
- Open the review, make **no** decision, close → all requests still pending and reviewable.
- Approve 1 of 3 → the other 2 remain pending.
- Full `pytest` green; quote the count.
