# Island Traders Release Notes

Release notes are required before merging a feature/fix branch into
`pre-release`.

## Unreleased

Branch: `codex/future-fixes`
Target: `pre-release`
Recommended version: `0.1`

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

- Issue #2 remains open: action menu can disappear for some players in
  multiplayer and may require rejoin.
- Cross-island machinery, leases, release-ready Help catalogue, island-ledger
  ownership model, and post-auction AI island purchase are documented future
  requirements, not complete implementations.

### Verification

- Test suite status: `161 passed`.
- Manual browser testing: server restarted on `127.0.0.1:8001`; live gameplay
  testing still recommended before final merge.
