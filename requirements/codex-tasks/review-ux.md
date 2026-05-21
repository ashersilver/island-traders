# Codex Task - Review UX: Action Structure and Detail Popups

**Goal:** Rework the online game dashboard so players can understand what
actions are available, why they matter now, and what detail sits behind
high-level summaries such as personnel in training. The current UI exposes
the right engine capabilities, but it asks players to interpret a flat action
menu and scattered status surfaces under time pressure.

## Background

UX review on `pre-release` (2026-05-20/21) found that the dashboard is now
functionally rich but cognitively noisy:

- The action area renders every `TurnAction` as an equal button. Role-specific
  or context-specific actions such as insurance, loans, transport, patents,
  training, market actions, and info views all compete in one flat row.
- Decision Hints correctly identify many next problems, but they do not open
  the action that would address the problem.
- Personnel currently shows only aggregate in-training counts by worker band.
  The engine has training pipeline detail, but the server does not expose it
  as structured game-state data for a popup.
- The UI uses several detail patterns: modals for production constraints and
  market board, inline cards for loans/insurance, event-log text for training
  status and view actions. Players should not need to read the log to answer
  "where are my workers and when do they return?"
- The market board and market-buy dialog include resources with no current
  relevance, which hides urgent resources among blank rows.
- The Banker has moved to a service model, but the market still surfaces
  `Finance` as a commodity. Either hide it from market UI/state or document
  why it remains tradable.

## Branch

- **Base:** latest `pre-release`
- **Branch name:** `codex/review-ux`
- **Target for merge:** `pre-release`

## Files likely in scope

- `island_traders/server/static/index.html` - primary UI work surface
- `island_traders/server/app.py` - game-state payload additions
- `island_traders/server/ws_adapter.py` - action metadata if the grouped
  action menu is server-driven
- `island_traders/engine/turn.py` - read mostly; touch only if the UI needs
  new structured prompt metadata
- `island_traders/models/training.py` - read only unless exposing helper
  methods for training summaries is cleaner here
- `tests/test_server/` - game-state payload and server behavior tests
- Browser/manual verification against the local web UI

Avoid changing game balance, production math, training rules, or market
matching semantics as part of this UX pass.

## Requirements

### 1. Group the action menu by player intent

Replace the flat action button row with visually grouped sections:

- **Production:** Produce, Apply Patent
- **Trade:** Market Buy, Market Sell, Propose Deal
- **People:** Request Training, Review Training, Arrange Transport,
  Recruit Workers
- **Capital:** Purchase Equipment, Invest
- **Finance:** Take Loan, Offer Loan, Rollover Loan, View Loans,
  Buy Insurance, Sell Insurance, Manage Insurance
- **Info:** View Market, View Players, Inventory

Role- or context-specific actions should be hidden or disabled when they are
not meaningful for the current player. Disabled actions must explain why they
are unavailable, for example: "Only Banking and Insurance can sell policies"
or "No active loans to roll over." If hiding is simpler for v1, keep at least
one discoverable "More actions" area so players do not think features have
vanished.

`Produce` should remain visually prominent, but it should not be the only
action with semantic weight. A trading-critical hint should be allowed to
promote `Market Buy`; a training-critical hint should be allowed to promote
`Request Training`.

### 2. Connect Decision Hints to actions

Decision Hints should become actionable:

- A resource shortfall hint should offer an inline control that opens Market
  Buy filtered or focused to that resource.
- An equipment-capital hint should open the Production Constraints detail or
  Purchase Equipment/Invest flow with the relevant item visible.
- A workforce shortfall hint should open the Personnel/Training detail popup
  and offer Request Training when slots and workers are available.
- A loan or insurance hint should open the corresponding finance detail or
  management action.

Do not auto-submit any action from a hint. Hints may preselect or filter a
modal, but the player must confirm the final game action.

### 3. Add a Personnel detail popup

Make the Personnel summary clickable and add a popup that answers:

- How many workers are active, away, injured/absent if tracked, and total
- Counts by band and, where available, specific profession
- Training batches currently pending or in flight
- For each training batch: target profession, worker count, status, educator,
  transport mode, offered fee, return season/year, and any counter-message
- Capacity/deficit summary: missing professions for the island staffing plan
  and current university slot availability

The popup should degrade gracefully when no workers are in training:
"No workers currently in training" plus the current staffing summary.

### 4. Expose structured training pipeline data

Add a structured `training_pipeline` field to each player in game state. It
should be derived from the same source as the engine's current training-status
text and include enough data for the Personnel popup without scraping log
lines.

Suggested shape:

```json
{
  "batch_id": 3,
  "worker_count": 2,
  "target_profession": "Flight Crew",
  "status": "dispatched",
  "educator_player_id": 4,
  "educator_name": "Education Island",
  "transport_mode": "air_ticket",
  "dollops_to_educator": 80.0,
  "return_year": 1,
  "return_season": "Summer",
  "seasons_remaining": 1,
  "counter_message": null
}
```

Keep existing `workforce_training_bands` for compact rendering; the new field
is additive.

### 5. Standardize detail surfaces

Use a consistent popup pattern for:

- Production Constraints
- Personnel / Training
- Market Board
- Loans
- Insurance
- Inventory

The sidebar should stay a summary surface. Popups should carry dense detail
and relevant action entry points. Avoid moving critical detail only into the
event log.

### 6. Improve market filtering

Market Buy should prioritize:

1. Resources currently mentioned by Decision Hints or production shortfalls
2. Resources with current asks or bids
3. All other commodities in a collapsed/secondary area

Rows with no bid, no ask, and no current relevance should not dominate the
first viewport of the market-buy dialog.

### 7. Resolve the Finance commodity inconsistency

The Banker is now described as producing loans and insurance rather than a
tradable `Finance` commodity. Decide one of:

- Hide `Finance` from market state and UI if it is legacy-only; or
- Keep it visible but document its current purpose and make the Banker flows
  explain how it is used.

Do not silently leave `Finance` as an empty market row if it is not meant to
be traded.

## Acceptance criteria

- The action area is grouped by intent and no longer renders all actions as
  one undifferentiated button row.
- A Farmer does not see active `Sell Insurance` / `Offer Loan` controls as
  peer-level actions unless they hold a Banker role; unavailable finance
  actions are hidden or clearly disabled with a reason.
- Decision Hints can open the relevant action/detail surface without forcing
  final submission.
- Personnel opens a popup showing training batches, status, and return timing
  when workers are away for training.
- Structured `training_pipeline` data is present in the server game-state
  payload and covered by tests.
- Market Buy's first viewport prioritizes needed/available resources instead
  of blank rows.
- Finance commodity visibility is intentional and documented in code/tests or
  removed from the market UI/state.
- Existing tests pass.
- Browser verification covers at least desktop width and one narrow/mobile
  width, with screenshots or notes confirming no action groups, popup text, or
  controls overlap.

## Suggested implementation order

1. Add server-side action metadata and/or client-side grouping map.
2. Add `training_pipeline` to game state with tests.
3. Build the Personnel popup from structured data.
4. Link Decision Hints to existing modals/actions.
5. Filter/reorder Market Buy rows.
6. Resolve Finance commodity visibility.
7. Run tests and browser-check desktop/mobile layouts.

## Reference

- Action enum: `island_traders/engine/turn.py::TurnAction`
- Current action rendering: `island_traders/server/static/index.html::showActionPrompt`
- Current personnel rendering: `island_traders/server/static/index.html::renderGameState`
- Game-state payload: `island_traders/server/app.py::get_game_state`
- Current text-only training status:
  `island_traders/engine/turn.py::_print_training_status_for_player`
