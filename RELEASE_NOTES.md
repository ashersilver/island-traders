# Island Traders Release Notes

Release notes are required before merging a feature/fix branch into
`pre-release`.

## Unreleased

### claude/loans-and-insurance

Branch: `claude/loans-and-insurance`
Target: `pre-release`
Closes: GitHub #5, #6

#### Player-Facing Changes

- **Loan roll-over (Issue #6).** New `Roll Over Loan` action in the player
  action menu. The borrower picks an active loan, chooses a new term (1-3
  years), and the Banker quotes a new rate. The old loan's repayment becomes
  the new loan's principal — no cash moves at rollover, the new advance
  exactly covers the old repayment. Useful at or before maturity to extend
  obligations or to lock in a fresh rate quote.
- **Insurance review & cancellation (Issue #5).** New `Manage Insurance`
  action lists the player's active policies with seasons remaining and the
  pro-rata refund amount. Cancellation deactivates the policy and the Banker
  pays out a pro-rata refund (`premium × seasons_remaining / total_seasons`).
- Loans and Insurance side panels in the dashboard now show structured
  per-loan / per-policy detail: principal, rate, term, repayment amount,
  maturity date, seasons remaining, and cancel refund.
- Loans nearing maturity (≤1 season) and policies nearing expiry (≤1 season)
  are highlighted in gold to flag the renewal decision.

#### Engine

- New `LoanStatus.ROLLED_OVER`.
- New `Loan.rolled_over_from_loan_id` traceability field.
- New `LoanLedger.rollover_loan(loan_id, new_rate, new_term_years, year,
  season) -> Loan`. Refuses non-active loans or out-of-range terms.
- New `InsurancePolicy.seasons_remaining()` and `cancel_refund()` methods.
- New `Player.cancel_insurance_policy(policy_id, year, season) -> float` —
  returns the refund amount; caller is responsible for the cash transfer.
- New `TurnAction.ROLLOVER_LOAN` and `TurnAction.MANAGE_INSURANCE` with
  full prompt-chain implementations in `engine/turn.py`. Funding-side loans
  (lender_id == -1) are filtered out of rollover candidates.

#### Server

- `get_game_state` payload now includes `loans_detail` (structured per-loan
  info: role, principal, rate, term, maturity, seasons-to-maturity) and
  `policies_detail` (structured per-policy info: type, premium, expiry,
  seasons-remaining, cancel-refund). The plain `policies` string list is
  retained for back-compat.

#### Tests

- 15 new engine tests in `tests/test_engine/test_loan_rollover_and_insurance.py`:
  ledger primitives, action-level end-to-end (rollover, cancel, confirm-no
  cancellation), external bank funding-loan filtering, pro-rata math edge
  cases, double-cancel guard.
- 3 new server tests in `tests/test_server/test_game_state_loans_policies.py`
  covering the structured payload shape.

#### Verification

- Test suite: `194 passed` (up from 176 baseline).

---

### claude/pause-game

Branch: `claude/pause-game`
Target: `pre-release`
Closes: GitHub #1

#### Player-Facing Changes

- **Pause / Resume game (host only).** The room creator can pause the game at
  any point during auction, investing, or running phases. While paused:
  * All timers freeze (auction, investing, season-action, pre-season).
  * A full-screen "Game Paused" overlay covers the screen for every client.
  * Only the host sees the Resume button.
  * Players can still click Ready while paused, but the game does not advance
    until the host resumes.
- On resume, every timer end-epoch is bumped forward by the pause duration so
  no one loses time. If everyone clicked Ready while paused, the phase closes
  immediately on resume.

#### Server-Side

- New `paused: bool` and `paused_at: float` fields on `GameRoom`.
- New `request_pause(room_id, lobby_player_id, paused)` GameManager method,
  host-only.
- `_do_pause` cancels asyncio timer tasks (auction / investing / season);
  `_do_resume` reschedules them with the remaining seconds and bumps
  `*_timer_end` epochs forward.
- Pre-season game-thread wait loop now polls in 0.5s slices and respects
  `room.paused` — `pre_season_end` is bumped forward on resume so the wait
  naturally extends.
- `submit_ready` collects Ready presses during pause but does NOT fire
  `interrupt_all` or `_pre_season_done.set` until resume.
- WS protocol: client → `{type: "pause_request", paused: bool}`; server →
  `game_paused` / `game_resumed` broadcasts; `pause_ack` reply.
- Reconnecting clients receive `game_paused` if the game is currently paused.
- `room.to_dict()` now includes `creator_id` (so clients know who's host) and
  `paused`.

#### Tests

- New `tests/test_server/test_pause_game.py` — 12 tests covering host gating,
  pause/resume round-trip, timer-end bumping for auction/investing/season/
  pre-season, ready-during-pause queueing, quorum-on-resume short-circuit,
  and asyncio timer-task cancellation.
- Fixed `test_concurrent_ensure_player_does_not_create_duplicate_events`
  isinstance check (`threading.Lock` is a factory function on Python 3.9, not
  a class).

#### Verification

- Test suite: `176 passed`.

---

### claude/fix-action-menu-bug2

Branch: `claude/fix-action-menu-bug2`
Target: `pre-release`

#### Fixes

- **Fixed Bug #2: action menu stops displaying for some players.** Root cause
  was three race conditions in `WebSocketIOAdapter`:
  1. `_ensure_player` was not thread-safe — concurrent calls for the same
     player could create duplicate `Event`/`Lock` objects, leaving threads
     waiting on different Events.
  2. `_send_and_wait` had a split-lock gap between `event.clear()` and storing
     the pending message, allowing `interrupt_all()` or `receive_response()` to
     fire in the gap and be lost.
  3. No logging on timeouts or `None` responses made the issue hard to diagnose.
- Added structured logging in `ws_adapter.py` (choose_action, _send_and_wait)
  and `app.py` (unmapped lobby player IDs).
- Fixed `test_loans.py` Python 3.9 compatibility (missing `from __future__
  import annotations`).

#### Tests

- Added `test_concurrent_ensure_player_does_not_create_duplicate_events` —
  verifies thread-safe lazy initialisation with a 4-thread barrier.
- Added `test_response_during_send_and_wait_is_not_swallowed` — verifies
  near-instantaneous responses are not lost.

#### Verification

- Test suite: `135 passed, 2 skipped`.

---

### claude/test-fixes-and-spec-cleanup

Branch: `claude/test-fixes-and-spec-cleanup`
Target: `pre-release`

#### Balance Changes

- Every island now starts with sufficient resources for at least 2 seasons of
  production inputs (previously 1 season). Gives players breathing room to
  establish trade relationships before running out of critical inputs.

#### Fixes

- Fixed `test_loans.py` Python 3.9 compatibility (missing `from __future__
  import annotations`).
- Cleaned up spec cross-references between `production-capacity-model.md` and
  `island-ledger.md` to eliminate duplication.

#### Tests

- Added `test_every_island_starts_with_at_least_two_seasons_of_inputs`
  invariant test covering all 7 roles.
- Updated `test_economy_balance.py` assertions to match new starting inventory.

#### Verification

- Test suite: `135 passed, 2 skipped`.

---

## 0.1 (codex/future-fixes)

Branch: `codex/future-fixes`
Merged to: `pre-release`

### Player-Facing Changes

- Expanded browser dashboard with richer production capacity, funding-rate,
  market, training, loan, and deal-response flows.
- Added island artwork backgrounds and a wider right-hand market/info panel.
- Renamed player-facing role labels to island specialties, while preserving
  existing internal role identifiers.
- Added Release Notes and release-process documentation before the
  `pre-release` merge gate.

### Rules / Balance Changes

- Added Metal as an intermediate resource; Manufacturing product lines now use
  Metal instead of raw Ore.
- Reduced Mining Oil production and added Metal smelting with enhanced crusher
  and smelter support.
- Added mid-game capital equipment purchases from Manufacturing output.
- Added population-based Food/Fish demand signals, with educated workforces
  increasing Fish demand.
- Added richer loan terms, posted funding rates, banker quote logic, and
  net-wealth treatment including loans and depreciated equipment.
- Documented future requirements for cross-island machinery, product/equipment
  Help text, post-auction human island guarantees, and Claude worktree usage.

### Fixes

- Fixed deal response flow so counterparties can review pending deals on their
  turn.
- Fixed selected-product production so players choose what and how many to
  produce.
- Fixed training review/counteroffer flows and air-ticket requirements.
- Fixed multi-role Banker loan access.
- Fixed market board modal dismissal verification tracking.
- Fixed production capacity and constraint reporting around ordered/owned
  capital equipment.

### Known Issues / Follow-Up

- ~~Issue #2 remains open~~ — fixed in `claude/fix-action-menu-bug2`.
- Cross-island machinery, leases, release-ready Help catalogue, island-ledger
  ownership model, and post-auction AI island purchase are documented future
  requirements, not complete implementations.

### Verification

- Test suite status: `161 passed`.
- Manual browser testing: server restarted on `127.0.0.1:8001`; live gameplay
  testing still recommended before final merge.
