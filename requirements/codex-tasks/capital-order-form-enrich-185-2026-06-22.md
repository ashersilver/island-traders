# Brief — Enrich the Capital Equipment Order modal to match the #185 mockup (2026-06-22)

**Suggested owner:** Codex (frontend — `server/static/index.html` only).
**Relates to:** #185 (order form + mockup), #188 (maintenance pricing).
**Base off:** the branch carrying Capital Orders II (#185/#188 order modal + financing) —
currently `claude/integrate-qol-pollution-48-45`. If that has already merged to
`pre-release`, base off `origin/pre-release` instead. Confirm the modal described below
exists before starting.

## Rules of engagement (Codex — read every time)

- **Worktrees / no shared trees.** Work in the **primary checkout**
  (`/Users/ashleysilver/Documents/projects/island-traders`). Claude works in a separate
  `claude/*` worktree — do not edit it or run `git reset/checkout/stash` against it.
- **Branch.** `git fetch` first; cut a fresh branch off the base above named
  `codex/capital-order-form-enrich-2026-06-22`. Never commit onto `pre-release`/`master`.
- **PRs only.** Reach `pre-release` through a PR that Claude (integrator) merges. Link the
  issue (`Refs #185`). Update `RELEASE_NOTES.md` and bump `APP_VERSION` `.N` in
  `constants.py`.
- **Git discipline.** No `--no-verify`/`--amend`/force-push. Run the full `pytest` suite
  before handoff (this is a frontend-only change but keep the suite green).
- **Handoff.** "branch X at commit Y — ready to integrate."

## Why

The shipped order modal is minimal vs. the approved mockup. The user wants, this pass, an
**enriched modal** (NOT the full 3-column desk — that's a later issue): per-line prices, a
line-item quote summary, per-option costs + descriptions, a Standard Terms block, and info
(i) icons. The mockup is the visual + copy spec:
`requirements/mockups/capital-equipment-order-185.html` (see `.quote`, `.option`,
`.terms`, and the rail pricing/terms tables).

## Current state (ground truth)

All in `island_traders/server/static/index.html`:
- Modal markup: `<div class="overlay" id="capital-order-overlay"><div class="dialog">` near
  **line 1490** — term `<select id="cap-order-term">`, `cap-order-predictive`,
  `cap-order-spares`, `cap-order-expedited`, `cap-order-financing`, a single
  `cap-order-total` line, Cancel/Send buttons.
- JS near **line 2708-2760**: `openCapitalOrder(itemId)` (reads the item from
  `gameState.players[myPlayerIdx].capacity.capital_catalogue`), `CAP_CONTRACT_PER_100`
  (the #188 per-$100 table `{term:[baseline,predictive]}`), `updateCapOrderTotal()`
  (current single-total calc), `submitCapitalOrder()` (sends the `capital_order` WS msg).
- `openCapitalPicker()` (just added) lists buildable items and calls `openCapitalOrder`.
- Catalogue item fields available per item: `item_id, name, role, cost, cash_only,
  delivery_seasons, description, owned, failed, mandatory` (built server-side in
  `app.py` `_player_capacity`, ~line 2185).
- Pricing already mirrored client-side: maintenance =
  `CAP_CONTRACT_PER_100[term][predictive?1:0] * cost / 100`; spares = `0.15 * cost * kits`.

## What to build

Keep it a **modal**; do not build the nav/steps/printable-preview desk. Make every number
recompute live in `updateCapOrderTotal()`.

1. **Line-item Quote Summary** (mirror mockup `.quote`): rows for list price, maintenance/
   warranty contract (labelled with chosen term + "Predictive Maint." when on), manufacturer
   guarantee (`0.00` / "No charge"), spares ×N, a **Recommended total**, and a separate
   *contingent* line "+ Expedited repair (billed at failure, if eligible) ~`0.15·cost`".
2. **Per-option rows** for each toggle (maintenance, guarantee, spares, expedited,
   financing): show the option cost on the right and a one-line description (copy from the
   mockup `.option` blocks). Maintenance row keeps the term `<select>` + predictive toggle.
3. **Standard Terms** block (mockup `.terms` — the six bullets: repair ≈ 35% of list; #188
   per-quarter Weibull failure ×disasters/sabotage; each spares kit −50%; spares +50% if
   built at failure; standard repair completes next season; expedited needs spares + air
   freight).
4. **Info (i) icons** next to maintenance, spares, expedited, financing that reveal the
   relevant term detail on hover/focus/click. Reuse existing tooltip/popover/toast styling —
   **do not** add a JS/CSS library.
5. The buyer-facing form must **not** display the 2% manufacturer referral (internal only).

## Constraints & gotchas

- Pricing formulas must match the server (`maintenance_contract_cost` in
  `models/player.py`, `0.15·cost·kits`). Round to 2dp as the existing code does.
- `index.html` is large; keep the change as a clearly delimited block and reuse existing CSS
  variables/classes (`--gold`, `--dim`, `.dialog`, etc.) rather than inventing a palette.
- **Do not** change the `capital_order` WS message shape — a separate brief
  (`capital-order-negotiation-185-2026-06-22.md`) repurposes it into an offer; this brief is
  display-only so the two can land independently. If both are in flight, this one must not
  break the existing instant-submit path.

## Definition of done

- The modal shows the line-item quote, per-option costs + descriptions, Standard Terms, and
  working info icons, updating live as term/predictive/spares change.
- No referral shown to the buyer. Full `pytest` green. PR opened with RELEASE_NOTES +
  APP_VERSION bump, screenshots of the enriched modal attached.
