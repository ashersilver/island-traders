# Island Traders Release Notes

Release notes are required before merging a feature/fix branch into
`pre-release`.

## Unreleased

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
