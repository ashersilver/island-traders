# UX Review Implementation Plan

**Source brief:** [`requirements/codex-tasks/review-ux.md`](../codex-tasks/review-ux.md)
**Source mockups:** [`requirements/mockups/review-ux.html`](../mockups/review-ux.html), [`review-ux-print.html`](../mockups/review-ux-print.html)
**Decided 2026-05-21. Updated 2026-05-24 (all in-scope phases shipped).**

## Status — 2026-05-24

All in-scope phases (1–6 + follow-ups) have shipped to `pre-release`. The
deferred graphical work (Mockup 4, island-art treatment) is still
deferred — see "Out — deferred" below.

| Phase | Branch | Status | Merge |
|---|---|---|---|
| 1. Server payload | `codex/ux-server-payload` | ✅ shipped | PR #31 |
| 2. Grouped action menu | `claude/ux-action-grouping` | ✅ shipped | `edf4131` |
| 3. Personnel popup | `claude/ux-personnel-popup` | ✅ shipped | `cdeebba` |
| 4. Hints → actions | `claude/ux-hints-to-actions` | ✅ shipped | (post-`6f80abb`) |
| 5. Market Buy filter + hint focus | `claude/ux-market-filter` | ✅ shipped | (post-`6f80abb`) |
| 6a. Shared popup shell | `claude/ux-popup-shell` | ✅ shipped | `a270766` |
| 6b. Loans/Insurance/Inventory popups | `claude/ux-popup-followups` | ✅ shipped | (post-Phase 5) |

**Defect surfaced during Phase 3 playtest (2026-05-24):**
self-trained workers never graduated. Fixed in
`claude/training-return-bug` (merged as `399165e`). The Personnel
popup's `seasons_remaining = 0` rows made the misalignment visible
between the registry-side completion and the workforce-side worker
state. Three regression tests added.

## Follow-ups identified during implementation

These came out of the work but were deliberately scoped out of their
parent branch to keep merges tight. None block the original plan.

- **Server gating on state-dependent actions.** Codex's Phase 1
  payload only gates by role + `APPLY_PATENT` inventory.
  `ROLLOVER_LOAN` / `VIEW_LOANS` / `MANAGE_INSURANCE` should also be
  gated by "has loans" / "has policies" with the right
  `disabled_reason`. Currently the UI shows these as enabled even when
  the player has nothing to act on.
- **Client hint renderer → server `decision_hints` reconciliation.**
  Codex's server-side `decision_hints` field (with structured
  `target`) exists but the client's own `renderDecisionHints` still
  computes hints locally. Loan / insurance hint kinds therefore never
  reach the UI today. Switching the client to consume server hints
  (or wiring loan/insurance hint detection into the client renderer)
  is the natural next step.
- **In-modal preselection for non-Market-Buy actions.** Phase 5
  landed Market Buy preselection (jump to row, gold ring). Equivalent
  preselection for `workforce_shortfall` → Request Training (jump
  the Request Training modal straight to the target profession) and
  `equipment_shortfall` → Production Constraints (focus the binding
  output) would close the loop on Phase 4's hint plumbing.
- **Inventory popup valuation.** Currently uses current ask price.
  TODO Financial Model section already specs "lower of cost or
  market" + "last-deal price" — apply that here for consistency with
  the wealth calculation.
- **Capacity / deficit section inside Personnel popup.** The brief
  asks for "missing professions for the island staffing plan and
  current university slot availability." Deferred from Phase 3
  because the data shape needed cross-referencing
  `pd["capacity"]` and the staffing blueprint. Worth doing in a
  follow-up once the hint preselection above lands.
- **Inline action affordances inside Loans / Insurance popups.**
  e.g. a "Cancel policy" button inside the Insurance popup that
  dispatches `MANAGE_INSURANCE` preselected to that policy_id.
  Same `sendResponse`-during-prompt pattern as Phase 4. Deferred
  to avoid creeping the popup-followups branch.

## Ownership split

Work is split along the **server / UI** seam:

- **Codex** owns server-side payload work — see [`requirements/codex-tasks/review-ux-server.md`](../codex-tasks/review-ux-server.md).
- **Claude** owns all client-side UI work (HTML/CSS/JS in `island_traders/server/static/index.html`).

Codex's server payload lands first so Claude's UI work can consume it.

## Scope

**In** — brief §1–7 + Mockups 1–3:

1. Group the action menu by intent
2. Connect Decision Hints to actions
3. Personnel detail popup
4. Structured `training_pipeline` payload
5. Standardize detail surfaces (Production / Personnel / Market / Loans / Insurance / Inventory)
6. Market Buy first-viewport filtering
7. Resolve `Finance` commodity inconsistency — **decision: hide from market state + UI**

**Out — deferred (graphical work):**

- Mockup 4 — Graphic Background Review (art treatment, cutouts, modal backdrops, brightness, intro screen art)
- TODO #7 — All-player summary on island layout SVG
- TODO #8 — Intro screen with island graphics
- TODO #23 *graphic* portion — text-only island popup may land in Phase 6; the graphic itself is deferred

## Overlap with existing TODO / requirements

| UX brief item | Existing TODO / spec | Reconciliation |
|---|---|---|
| Action grouping | — | Net-new |
| Decision Hint → action | TODO #3 (action alerts) | Different surface; independent |
| Personnel popup | TODO #20 (panel counts — done); Education Phase 3 (data — done) | Next layer; no engine changes |
| `training_pipeline` payload | Education Phase 3 internals already compute it | Serializer-only addition |
| Standardize popups | Production Capacity TODO (Constraint Popup); #22 (Market Board grid — done) | Consolidates the modal shell |
| Market Buy filter | #22 (pricing UX — done) | Direct extension |
| Finance commodity | Phase D1 made Banker a service provider | **Hide from market state + UI** |
| #23 island popup | TODO #23 wants graphic | Text-only version in Phase 6; graphic deferred |

## Phased branches

Each phase = one branch off `pre-release`, mergeable independently, gated by a `RELEASE_NOTES.md` section per project rule.

### Phase 1 — Server: action metadata + game-state additions  **(Codex)**

**Branch:** `codex/ux-server-payload`
**Brief:** [`requirements/codex-tasks/review-ux-server.md`](../codex-tasks/review-ux-server.md)

- Extend action-prompt payload with `{group, enabled, disabled_reason, recommended}` per action.
- Add `training_pipeline: [...]` to each player in `get_game_state`.
- Hide `Finance` from `market_data` dict and any market-state surfaces.
- Annotate Decision Hints with a structured `target` (e.g. `{type: "resource_shortfall", resource: "Oil"}`) so the client can wire clicks without parsing English.

**Verify:** all existing server/engine tests green; new tests in `tests/test_server/` for the four payload additions.

### Phase 2 — Client: grouped action menu  **(Claude)**

**Branch:** `claude/ux-action-grouping`

- Rewrite `showActionPrompt` to render Mockup 1 layout (Production / Trade / People / Capital / Finance / Info), driven by Phase 1 metadata.
- Disabled buttons show tooltip with `disabled_reason`. Hidden when irrelevant for the role.
- `Produce` keeps highlight; `recommended: true` adds gold tint per mockup.
- Mobile: groups stack vertically; manual check at ~390px.

**Depends on:** Phase 1 merged.

### Phase 3 — Personnel detail popup  **(Claude)**

**Branch:** `claude/ux-personnel-popup`

- Sidebar Personnel summary becomes clickable → popup driven by `training_pipeline` + `workforce_bands` + `workforce_training_bands`.
- Sections per Mockup 2: Training Pipeline (batches with target profession, status, educator, return season, fee, counter-message) + Staffing Plan (deficits, university availability).
- Empty state: "No workers currently in training."
- Adds Inventory popup using the same shared modal shell (covers one Phase 6 target).

**Depends on:** Phase 1 merged.

### Phase 4 — Decision Hints become actionable  **(Claude)**

**Branch:** `claude/ux-hints-to-actions`

- Each hint gets an inline button opening the relevant modal, using the `target` from Phase 1:
  - `resource_shortfall` → Market Buy preselected to that resource
  - `equipment_shortfall` → Production Constraints / Purchase Equipment
  - `workforce_shortfall` → Personnel popup → Request Training (target profession preselected)
  - `loan_*` / `insurance_*` → corresponding management surface
- Hints may set `recommended: true` on action metadata; client renders gold tint.
- **Hard constraint:** hints never auto-submit. They preselect and open; the user confirms.

**Depends on:** Phases 1, 2, 3 merged.

### Phase 5 — Market Buy filter / ordering  **(Claude)**

**Branch:** `claude/ux-market-filter`

- Reorder rows: (1) hint-mentioned / shortfall resources; (2) resources with live asks or bids; (3) collapsed "All other commodities" section.
- Honor hint preselection from Phase 4.

**Depends on:** Phases 1, 4 merged.

### Phase 6 — Standardize popup shell + remaining surfaces  **(Claude)**

Ended up split into two branches because the shell could land
parallel to the Codex Phase 1 wait while the new popups had to wait
for Phase 1's payload.

**Branch 6a:** `claude/ux-popup-shell` — shared `showPopup(title, body, opts)`
helper + `.popup-footer` CSS + refactored Production Constraints,
Market Board, Market Buy to use it. Landed early (in parallel with
Codex Phase 1) since it has no payload dependency.

**Branch 6b:** `claude/ux-popup-followups` — new Loans / Insurance /
Inventory popups using the shell. Sidebar surfaces get a `⊕`
"Details" button next to their header. The text-only island
detail popup (TODO #23 minus the graphic) was further deferred to
the graphical follow-up.

### Phase 7 — Verification gate  **(joint)**

- `pytest` green at the head of each phase branch before merge.
- Manual browser pass at desktop + narrow (~390px) width, screenshots in the PR.
- `RELEASE_NOTES.md` entry per phase branch.

## Sequencing — actual order shipped

```
Phase 6a  popup-shell      ────► merged early (no payload dependency)
Codex 1   server payload   ────► merged via PR #31
  ├─ Phase 2  action grouping
  ├─ Phase 3  Personnel popup
  ├─ Phase 4  hints → actions      (after 1+2+3)
  ├─ Phase 5  market filter        (after 4)
  └─ Phase 6b popup followups      (independent — branched off Phase 1)
Bug-fix:  training-return          (post-Phase 3, surfaced by popup)
```

## Coordination — historical

These rules governed the parallel Codex / Claude work while phases
were in flight; preserved here so future cross-agent splits can
mirror the pattern:

- Claude did not start Phase 2 until Codex's Phase 1 was merged to `pre-release`.
- Codex did not modify any file under `island_traders/server/static/`.
- Claude did not modify `get_game_state`, action-prompt payload, or market-data serialization without Codex sign-off.
- Either side could flag a server-shape adjustment via a comment on the relevant PR; the change landed on a follow-up Codex branch.
