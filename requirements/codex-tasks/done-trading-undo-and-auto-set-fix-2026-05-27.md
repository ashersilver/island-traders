# Codex Task — Done Trading: stop auto-setting + add Undo (2026-05-27)

**Owner:** Codex
**Origin:** [Triage `0.1.0-dev.2026-05-26.5`](../playtest-feedback/triage-0.1.0-dev.2026-05-26.5.md) §3.1. Cross-cutting bug reported by **all three** active playtesters — Comet Player 1 (Manufacturer), AyaySir (Mining), Codex Player (Banking). AyaySir tagged it **Critical**. Seven separate item references collapse into one root cause:

- "Action panel disappears after End Turn — no way back" (Comet 1 #2)
- "Open Market Buy → buttons disabled after End Turn" (Comet 1 #3)
- "Produce buttons visible but non-interactive after End Turn" (Comet 1 #4)
- "Done Trading ✓ shown before player clicked End Turn" (Comet 1 #10)
- "End Turn should be reversible until timer hits zero" (Comet 1 IMP-1)
- "Done Trading state auto-set at season start" (AyaySir BUG-01, **Critical**)
- "Open Market Buy → spinner forever in Done state" (AyaySir BUG-02)
- "Hint shortcuts should auto-undo Done Trading" (AyaySir IMP-04)
- "Done Trading must never be auto-set by the server" (AyaySir IMP-05)
- "Done Trading carrying into the next season" (Codex Player rollover defect)

## Goal

Two related fixes, plus a hint-button policy decision:

**A. Server stops auto-setting Done Trading.** The only legitimate entry to the Ready/Done state is an explicit player click on the "End Turn / Done Trading ✓" button. Audit every call site that ends up at `WSAdapter.mark_player_ready(engine_pid)` or `submit_ready(..., ready=True)` and remove the offending paths.

**B. Add an Undo Done Trading path.** While the season clock still shows time remaining and the player has not actually had their pending IO prompts drained, a player who is Done must be able to un-Done themselves and resume trading. Server side already half-supports this (`unmark_player_ready` exists and is called when `submit_ready(..., ready=False)` arrives). What's missing: an explicit player-facing path to trigger it after Done is set, plus a prompt-replay so the player's action menu comes back.

**C. Decision-Hint buttons in the Done state.** Today they stay visible but disabled, which Comet 1 #3 / #4 and AyaySir BUG-02 all flagged as a false affordance. Pick ONE of: (1) hint buttons auto-undo Done before triggering their action (AyaySir IMP-04's preference), or (2) hide hint buttons entirely while Done. Document the choice in the PR description.

## Branching

- **Base:** `pre-release` at `8b6fd37` (current head — playtest-feedback folder + triage) or later.
- **Branch name:** `codex/done-trading-undo-and-auto-set-fix-2026-05-27`
- **Target for merge:** `pre-release`. **Do not merge yourself.** Push the branch and stop. Claude will review.

## Spec

### Sub-issue A: stop auto-setting Done

Suspected (not yet confirmed) call sites — investigate each:

- `_on_player_done` in `server/app.py` adds `lobby_pid` to `season_human_done` when a turn naturally ends. Confirm this is fired only when the player's turn loop has actually completed via END_TURN, not on any other path.
- `_on_season_start` / `_on_season_end` in `server/app.py` — confirm these don't seed `season_ready_set` from the previous season.
- WS reconnect path — confirm a returning player isn't auto-marked Done by any state-sync code.
- `interrupt_all` in `WSAdapter` (called on season timeout and when all humans Ready) — confirm it doesn't *also* mark players Done; it should only unblock pending IO prompts.

Fix whichever paths are mis-firing. Add a clear log line at the legitimate call site (`submit_ready(ready=True)` from a real player click) so future audits can grep for `"Player {} marked Done (explicit click)"`.

### Sub-issue B: Undo Done

- New `TurnAction.UNDO_DONE_TRADING` or equivalent. Action group: same one as End Turn (`Info` or `Trade` depending on existing convention).
- Server side: a new `submit_unready(room_id, lobby_pid)` REST/WS endpoint that calls `submit_ready(ready=False)` and re-queues a fresh `choose_action` prompt for the player (use the existing `replay_pending_prompt` helper from the 2026-05-26 fix, or generate a new one if no prompt is pending).
- Client side: button visible whenever the player is in `season_human_done` AND `season_timer_end > now` AND the player is not in `season_ready_set`-by-timeout state. Wording: "Resume Trading" or "Undo End Turn — N seconds left". Disabled (with explanation) once the timer hits zero.
- Guard rail: if the engine's per-player turn loop has already exited (true end-of-turn, not just the Ready flag), the Undo MUST refuse cleanly with a clear message — "Your turn has fully closed; cannot resume." The Ready flag short-circuit in `choose_action` is reversible; the actual loop exit is not.

### Sub-issue C: Decision-Hint policy in Done state

Pick option 1 (preferred per playtester) unless you discover something fundamental that breaks it:

**Option 1 (preferred):** `_actOnHint(action)` in `index.html` calls Undo Done first when the player is currently Done, then triggers the action. Single click for the player; engine sees `unmark_player_ready` followed by the chosen action.

**Option 2 (fallback):** hide all hint shortcut buttons while the player is Done. Decision Hints text remains visible (advisory) but no action buttons appear. Simpler but less helpful.

Whichever you pick, the "spinner forever / disabled but visible" current state must NOT remain.

### Files to touch (suggested)

- `island_traders/server/app.py` — audit Ready-flag setters; add `submit_unready` path; ensure `replay_pending_prompt` fires on undo.
- `island_traders/server/ws_adapter.py` — confirm `mark_player_ready` / `unmark_player_ready` are pure flag flips with no side effects.
- `island_traders/engine/turn.py` — new `TurnAction.UNDO_DONE_TRADING`; hook to clear `_player_ready_flags` and re-enter the action loop.
- `island_traders/cli/prompts.py` — Fake adapter needs symmetric `unmark_player_ready` for tests.
- Tests: new `tests/test_server/test_done_trading_lifecycle.py` covering all the auto-set paths and the undo path.

### UI follow-up (Claude separate)

- Visible "Resume Trading" button on the dashboard whenever the player is Done with time remaining.
- Decision Hint buttons rewired per the chosen Option 1 / Option 2.
- Tooltip on the End Turn button itself: "You can undo this while time remains in the season."

## Tests

- `tests/test_server/test_done_trading_lifecycle.py` (new):
  - Player connects mid-season → NOT marked Done.
  - Season starts → player starts NOT Done.
  - Player completes the previous season → state resets cleanly at next `_on_season_start`.
  - Player clicks End Turn → Done set; subsequent Undo within the timer clears it and replays an action prompt.
  - Undo after natural turn-loop exit refuses with a clear message.
  - Two-human game: one player Done while the other is mid-action → second player can still complete normally.
- Regression: existing `submit_ready` tests should pass unchanged.

## Acceptance criteria

- Audit identifies and fixes every illegitimate setter of `mark_player_ready` / `submit_ready(ready=True)` server-side.
- "Resume Trading" / Undo End Turn path lands end-to-end (action → server unmark → prompt replay → client gets action menu back).
- Decision Hint buttons no longer present a false affordance in the Done state; Option 1 or Option 2 documented in the PR description.
- Full test suite green at the new baseline count (463 + new tests).
- `RELEASE_NOTES.md` Unreleased section gets a new `### codex/done-trading-undo-and-auto-set-fix-2026-05-27` block.
- Calibration sweep unchanged (this is state-sync + UX; no economic side effects).

## Out of scope

- Reconnection handling pausing the season timer (Comet 1 IMP-11) — separate concern, related to server stability not Done state.
- AI Educator behaviour around the queue (covered by `educator-approval-queue-2026-05-26` already merged).
- Reverting the 📋 Menu recovery button shipped in `claude/restore-action-menu-2026-05-26` — it's still useful as a defense-in-depth recovery path; the Resume Trading button is the explicit user-facing flow.
