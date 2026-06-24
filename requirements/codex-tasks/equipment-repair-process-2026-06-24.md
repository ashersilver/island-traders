# Brief — Repair process for damaged / failed capital equipment (2026-06-24)

**Suggested owner:** Codex (capital model + server WS + tests). Frontend repair control is Claude's.
**Relates to:** capital-equipment-individual-tracking-and-failure (failure model), #185 capital orders,
the Build & Develop picker (already shows "⚠ N failed — rebuild").
**Base off:** `origin/pre-release` at the current tip (`git fetch origin` and confirm; was `f235dce`).

## Rules of engagement (Codex — read every time)

- **Worktrees / no shared trees — do NOT use the primary checkout.** It holds unrelated Claude
  work. Create your own worktree:
  `git fetch origin && git worktree add -b codex/equipment-repair-2026-06-24 ../it-codex-repair origin/pre-release`
- **PRs only.** Reach `pre-release` via a PR Claude merges. Update `RELEASE_NOTES.md` and bump
  `APP_VERSION` `.N`.
- **Git discipline.** No `--no-verify`/`--amend`/force-push. Run the **full** `pytest` suite.
- **Handoff.** "branch X at commit Y — ready to integrate", noting the **frontend** repair control
  is Claude's (you provide the WS contract + `game_state` fields).

## Why (observed)

Playtest 2026-06-24: "We need a repair process for equipment that is damaged, for any island and
for the manufacturer himself." Capital units can **fail** (the failure model + `Player.failed_capital`
tracking already exist; the Build & Develop picker now shows "⚠ N failed — rebuild"), but there is
**no way to actually repair a failed unit** — failed equipment just sits idle (it doesn't count in
`effective_capital_inventory`, so it produces nothing). Players need an explicit repair action.

## Spec

1. **Repair action (engine + WS).** Add a way to repair a failed capital unit and return it to
   service. It should work for **any island** (each island repairs its own failed capital) **and the
   Manufacturer's own equipment**. Define the cost model — pick what fits the economy and confirm
   with the user (see open questions): e.g. a Dp cost and/or **spares** consumption (the Manufacturer
   already produces `ResourceType.SPARES`; a spares-kit attached to a unit, or generic spares from a
   warehouse, is the natural repair currency), possibly plus a season of downtime.
2. **Spares integration.** A unit delivered with `spares_attached` should be repairable **using its
   own spares first** (no Dp), then falling back to a paid/generic-spares repair when spares run out.
   Tie into the existing spares warehouse (`manufacturer.warehouse`) + `manufacture_spares`.
3. **Manufacturer self-repair.** The Manufacturer must be able to repair its own failed production
   capital the same way (it's both producer and owner) — make sure the self-build settlement path
   doesn't conflict (self-builds settle immediately; repair is a separate action).
4. **State + log.** A repaired unit re-enters `effective_capital_inventory` (produces again next
   season). Clear turn-log messaging ("Repaired {item} for {cost}; back in service next season").
5. **`game_state` for the UI.** Expose, per owned capital item: `failed` count, whether it's
   repairable now, the repair cost (Dp and/or spares), and a repair action id — so Claude can add a
   **Repair** control in the Build & Develop panel (which already lists failed units). You provide the
   fields + WS contract; Claude wires the button.

## Tests

- A failed unit can be repaired (any role) → it re-enters effective capital and produces next season.
- Repair consumes the defined cost (spares first if attached, then Dp/generic spares); a player who
  can't afford the repair is rejected with a clear message (and the unit stays failed).
- The Manufacturer can repair its own failed capital.
- Full `pytest` suite green (baseline: **818 passing**).

## Open questions for the user (note in PR)

1. Repair **cost model**: spares-only, Dp-only, or spares-then-Dp fallback? (Suggested: use attached
   spares first, then a Dp cost.)
2. Is there **downtime** (a unit is out for a season after repair) or is it instant?
3. Can a unit fail **permanently** after N repairs, or is it always repairable?
