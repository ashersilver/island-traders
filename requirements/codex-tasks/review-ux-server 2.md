# Codex Task — UX Review: Server Payload Additions

**Owner:** Codex
**Pairs with:** Claude UI work in [`requirements/implementation-plans/review-ux-plan.md`](../implementation-plans/review-ux-plan.md)
**Original brief:** [`requirements/codex-tasks/review-ux.md`](review-ux.md) (full spec; this file is the server-only slice)
**Mockups:** [`requirements/mockups/review-ux.html`](../mockups/review-ux.html)

## Goal

Make the data Claude needs for the grouped action menu, Personnel popup, hint-clicks, and `Finance` removal available in the existing server payloads. **No client-side changes** — this is a pure server pass. Claude's UI work depends on these shapes landing first.

## Branching

- **Base:** `pre-release` (current head as of fetch; verify with `git fetch origin pre-release && git log --oneline origin/pre-release -1`)
- **Branch name:** `codex/ux-server-payload`
- **Target for merge:** `pre-release` — **but do not merge yourself.** Push the branch and stop; Claude will review and signal merge timing (see "When to stop" below).

```bash
git fetch origin
git checkout -b codex/ux-server-payload origin/pre-release
```

## Scope — exactly these four items

### 1. Action-prompt payload metadata

Extend the action-prompt message produced for `showActionPrompt` (currently a flat list of `{value, label}` per option) with grouping and gating metadata.

**Per option, add:**

```json
{
  "value": "buy_market",
  "label": "Market Buy",
  "group": "Trade",
  "enabled": true,
  "disabled_reason": null,
  "recommended": false
}
```

**Group taxonomy (use exactly these labels):**

- `Production` — Produce, Apply Patent
- `Trade` — Market Buy, Market Sell, Propose Deal
- `People` — Request Training, Review Training, Arrange Transport, Recruit Workers
- `Capital` — Purchase Equipment, Invest
- `Finance` — Take Loan, Offer Loan, Rollover Loan, View Loans, Buy Insurance, Sell Insurance, Manage Insurance
- `Info` — View Market, View Players, Inventory

**Rules:**

- `enabled: false` actions must include a one-line `disabled_reason` (e.g. `"Only Banking can sell policies"`, `"No active loans to roll over"`).
- Role-irrelevant actions (e.g. `SELL_INSURANCE` for a Farmer) — prefer `enabled: false` with reason. Hiding is acceptable when an action is **never** meaningful for a role; in that case omit it from the list rather than including with `enabled: false`.
- `recommended` is reserved for Phase 4 wiring (Decision Hints promoting an action). For Phase 1, default to `false` everywhere.
- Source of truth is the engine — derive grouping/gating from `TurnAction` and current game/role state in `app.py` / `ws_adapter.py`. Do **not** hardcode a mapping in `static/index.html`.

**Files likely touched:**

- `island_traders/server/app.py` — where action prompts are built
- `island_traders/server/ws_adapter.py` — if grouping is computed at adapter level
- `island_traders/engine/turn.py` — **read only.** Touch only if a new helper method is genuinely cleaner; otherwise leave alone.

### 2. `training_pipeline` in game state

Add a new field `training_pipeline: list[dict]` to each player dict in `get_game_state` (in `island_traders/server/app.py`, around the existing `workforce_training_bands` field at line ~1633).

**Per-batch shape (see brief §4):**

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

**Rules:**

- Derive from the same source as `_print_training_status_for_player` in `island_traders/engine/turn.py`. Read only — do not change engine behavior.
- Keep `workforce_training_bands` as-is; this field is additive.
- Empty list when the player has no batches in flight.
- Status values should match existing engine vocabulary (e.g. `pending`, `dispatched`, `returning`, etc.). Document the enum in a comment near the field.

### 3. Hide `Finance` from market state

**Decision (confirmed 2026-05-21):** `Finance` is no longer a tradable commodity since Phase D1 made the Banker a service provider (loans / insurance). It must disappear from market UI and market state.

- Remove `Finance` from the `market_data` dict in `get_game_state` (the loop over `ResourceType` at line ~1679).
- Audit other server surfaces that report market quotes / supply / demand and exclude `Finance` consistently.
- **Do not** remove `ResourceType.FINANCE` from the enum or any engine constants — only stop *surfacing it as a tradable market commodity*. Loans and insurance still flow Dollops; that stays untouched.
- Add a comment near the exclusion explaining why (link to Phase D1 in `RELEASE_NOTES.md`).

### 4. Structured `target` on Decision Hints

The Decision Hints panel is currently text-only. Claude's Phase 4 UI work needs to make each hint clickable and open the right modal. To avoid parsing English on the client, annotate each hint with a structured `target`:

```json
{
  "text": "Short on Oil for next season's production.",
  "severity": "warn",
  "target": {
    "type": "resource_shortfall",
    "resource": "Oil"
  }
}
```

**`target.type` taxonomy:**

- `resource_shortfall` → `{ resource: "<ResourceType.value>" }`
- `equipment_shortfall` → `{ capital_item: "<item_id>" }`
- `workforce_shortfall` → `{ profession: "<Profession.value>" }`
- `loan_due` / `loan_offer` → `{ loan_id: <int> }`
- `insurance_review` → `{ policy_id: <int> }`
- `none` — fallback for hints that don't map to a specific action

**Rules:**

- Add the field alongside existing hint output; keep `text` as-is so older clients still render.
- If a hint genuinely has no actionable target, use `{ type: "none" }` — do not omit the field.
- Hint generation lives wherever the existing Decision Hints are produced. Find it via `grep -nE "Decision Hint|decision_hint|decision-hint"` and add `target` at the point of construction.

## Out of scope (do not touch)

- Any file under `island_traders/server/static/` — this is Claude's territory.
- Game balance: production math, training rules, market matching, capital lifecycle, loan / insurance math.
- New engine methods unless absolutely required (and only if read-only helpers).
- Mockup 4 / island art / SVG / intro screen — explicitly deferred.

## Tests required

Add to `tests/test_server/`:

1. `test_action_payload_grouping` — for a player with one role, the action-prompt payload includes correct `group` for every option and at least one `enabled: false` case with a `disabled_reason`.
2. `test_action_payload_finance_gated` — a Farmer's action payload does not include `SELL_INSURANCE` (or includes it disabled with the expected reason).
3. `test_training_pipeline_shape` — `get_game_state` returns `training_pipeline` as a list; when a player has a batch in flight, the dict contains all 12 keys listed above with correct types.
4. `test_training_pipeline_empty` — `training_pipeline == []` when no batches in flight.
5. `test_finance_hidden_from_market_data` — `get_game_state(...)["market"]` (or wherever market state lives) does **not** contain a `Finance` key.
6. `test_decision_hint_target_structured` — for a hint generated when a player is short on Oil, the hint dict contains `target == {"type": "resource_shortfall", "resource": "Oil"}`.

Run the full suite. **The acceptance bar is the full suite green, not just the new tests.**

```bash
pytest
```

Expected suite size at branch creation: ~346 tests passing (verify with a clean run on `origin/pre-release` first). Final suite must be 346 + 6 = 352 (or more if test scaffolding needed extra cases).

## When to stop

Stop and push when **all** of these are true:

- All four scope items implemented.
- All six new tests written and passing.
- Full `pytest` suite green.
- `RELEASE_NOTES.md` has a new section under `## Unreleased` describing the four additions (existing `pre-release` merge gate — see `requirements/release-process.md`).
- Signed-off commits per the existing convention (`git commit --signoff`).

**Do not:**

- Modify `static/index.html` or any other client-side file.
- Merge the branch into `pre-release` yourself.
- Tag a release or touch `master`.
- Run the simulation calibration or rebalance event charts (separate Codex task at `requirements/codex-tasks/balance-calibration-2026-05.md`).

## What to push

```bash
git push -u origin codex/ux-server-payload
```

Open a PR from `codex/ux-server-payload` → `pre-release` with:

- A summary of the four changes
- The `RELEASE_NOTES.md` excerpt (so reviewers can see the release-note entry)
- A test-suite confirmation line (e.g. "352 passing")

## When to wait for Claude's merge instruction

After pushing the branch and opening the PR:

1. **Wait** for Claude to confirm payload shapes match the UI plan.
2. **Wait** for Claude to merge — Claude's Phase 2 UI work consumes these shapes and the project convention is one merge into `pre-release` at a time.
3. If Claude requests a shape change, land the change as a follow-up commit on the same branch (`codex/ux-server-payload`) — do not open a second branch.
4. Once Claude merges, the branch is done. Subsequent UI iterations are Claude's responsibility.

## Reference

- `island_traders/server/app.py::get_game_state` (line ~1574) — where payload assembly happens
- `island_traders/server/app.py` market_data loop (line ~1679) — Finance exclusion lands here
- `island_traders/engine/turn.py::TurnAction` — enum being grouped
- `island_traders/engine/turn.py::_print_training_status_for_player` — text-only source for the new structured pipeline
- `island_traders/server/static/index.html::showActionPrompt` (line ~2716) — **read only**, just to confirm the shape Claude expects
- Mockup 1 in `requirements/mockups/review-ux.html` (line ~455) — visual reference for grouping
