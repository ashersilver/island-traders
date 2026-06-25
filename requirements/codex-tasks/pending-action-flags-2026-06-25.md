# Brief — Per-island pending-action flags (for action-button highlighting) (2026-06-25)

**Owner:** Codex (game_state flags + tests). **Process:** see `_README.md`.
**Base off:** `origin/pre-release` (fetch first; quote tip + APP_VERSION). Own worktree; push.
**Frontend is Claude's** (the button highlighting).

## Why

Action-menu buttons should **highlight when that island has a pending action waiting on it** —
e.g. the Transporter's **Arrange Transport** when a training cohort needs a ride, the Doctor's
**Review Staffing Requests** when nurses are requested, the Educator's **Review Training** when
requests await approval, etc. Today the player has to hunt for what needs doing.

## What already exists

`game_state` already carries some of this (per viewer): `deals_awaiting_me`,
`capital_negotiations_awaiting_me`, `training_decisions`. The role-specific ones (transport,
staffing) are **not** surfaced.

## Spec

1. **Consolidated `pending_actions` list in `game_state`** for the viewing player — a list of
   stable action keys that currently need this island's attention, computed from engine state.
   Cover at least:
   - `review_training` — Educator has `awaiting_educator` requests.
   - `arrange_transport` — a training cohort assigned to this Transporter awaits transport.
   - `review_staffing` — staffing/nurse requests await this island.
   - `review_deals` — `deals_awaiting_me` non-empty.
   - `review_capital_order` — `capital_negotiations_awaiting_me` non-empty.
   - `repair_capital` — this island has repairable failed capital.
   Use the existing per-viewer computation in `get_game_state` (`server/app.py` ~4100–4600) and
   the engine request registries (training, staffing, transport, deals).
2. **Keys must match the action-menu option values** the dashboard already uses (so the
   frontend can map key → button without a translation table). List the canonical keys in the
   PR.

## Frontend (Claude, after merge)
- Highlight each action-menu button whose action key is in `pending_actions` (a glow/badge),
  and optionally a count. Clear when the pending item is handled (next `game_state`).

## Tests
- An Educator with awaiting requests → `pending_actions` contains `review_training`.
- A cohort needing transport → the assigned Transporter's `pending_actions` has
  `arrange_transport`; others don't.
- Staffing request → `review_staffing` for the target island only.
- Full `pytest` green; quote the count.
