# UX Review Implementation Plan

**Source brief:** [`requirements/codex-tasks/review-ux.md`](../codex-tasks/review-ux.md)
**Source mockups:** [`requirements/mockups/review-ux.html`](../mockups/review-ux.html), [`review-ux-print.html`](../mockups/review-ux-print.html)
**Decided 2026-05-21.**

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

**Branch:** `claude/ux-popup-consolidation`

- Refactor Production Constraints / Market Board / Loans / Insurance / Inventory popups to a shared modal shell (header / close / cancel / footer-actions zone).
- Sidebar stays summary-only.
- Optional: text-only island detail popup (TODO #23 minus the graphic).

**Depends on:** Phases 3, 4, 5 merged.

### Phase 7 — Verification gate  **(joint)**

- `pytest` green at the head of each phase branch before merge.
- Manual browser pass at desktop + narrow (~390px) width, screenshots in the PR.
- `RELEASE_NOTES.md` entry per phase branch.

## Sequencing summary

```
Codex          Phase 1 ──────────────► [merge] ──┐
                                                 │
Claude (UI)                Phase 2 ◄─────────────┤ (any order)
                           Phase 3 ◄─────────────┘
                           Phase 4 (after 2 + 3)
                           Phase 5 (after 4)
                           Phase 6 (after 3, 4, 5)
```

## Coordination

- Claude does not start Phase 2 until Codex's Phase 1 is merged to `pre-release`.
- Codex does not modify any file under `island_traders/server/static/`.
- Claude does not modify `get_game_state`, action-prompt payload, or market-data serialization without Codex sign-off.
- Either side can flag a server-shape adjustment via a comment on the relevant PR; the change lands on a follow-up Codex branch.
