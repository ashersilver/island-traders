# Brief — Manufacturer producible lines: add Goods recipe + make TransportEquipment buildable (2026-06-23)

**Suggested owner:** Codex (capacity/recipe model + tests).
**Relates to:** playtest 2026-06-23 (Decision Hints only offered FarmMachinery / MiningEquipment /
MedicalDevices); fishing-roles overhaul; #185 (capital orders consume TransportEquipment).
**Base off:** `origin/pre-release` at **`a8853f0`** or later. `git fetch origin` and confirm
`git rev-parse origin/pre-release`.

## Rules of engagement (Codex — read every time)

- **Worktrees / no shared trees — do NOT use the primary checkout.** It holds unrelated Claude
  work. Create your own worktree:
  `git fetch origin && git worktree add -b codex/manufacturer-producible-lines-2026-06-23 ../it-codex-mfg origin/pre-release`
- **PRs only.** Reach `pre-release` via a PR Claude merges. Update `RELEASE_NOTES.md` and bump
  `APP_VERSION` `.N`.
- **Git discipline.** No `--no-verify`/`--amend`/force-push. Run the **full** `pytest` suite.
- **Handoff.** "branch X at commit Y — ready to integrate."

## Why (observed)

In the 2026-06-23 playtest the Manufacturer's Decision Hints offered only **FarmMachinery,
MiningEquipment, MedicalDevices** as producible — **Goods** and **TransportEquipment** were
missing. Investigation:

- The capacity/decision-hints model (`server/app.py` `_player_capacity`) iterates
  `recipes_for_role(PRODUCTION_RECIPES, role)`. For the Manufacturer, `PRODUCTION_RECIPES`
  (`constants_capacity.py`) contains **FarmMachinery, MiningEquipment, MedicalDevices,
  TransportEquipment** — but **no `Goods` recipe at all** (Goods exists only in
  `MANUFACTURER_PRODUCT_LINES` in `constants.py`). So Goods can never surface in capacity,
  decision hints, or the produce picker.
- **TransportEquipment** *is* in `PRODUCTION_RECIPES`, but the player couldn't produce it
  up front — it's gated by missing inputs and/or a capital item, so the frontend shows it as
  blocked rather than producible. The user wants TransportEquipment to be a normal buildable
  product line (it's consumed by ship/plane/shipyard capital orders).

## Spec

1. **Add a `Goods` `ProductionRecipe`** to `PRODUCTION_RECIPES` (`constants_capacity.py`),
   consistent with the `MANUFACTURER_PRODUCT_LINES["Goods"]` economics (inputs `Metal 1 + Oil 1`,
   output `Goods`, appropriate qty/labour). Make sure it flows through `recipes_for_role`,
   `compute_capacity`, the capacity payload, and the produce picker like the other lines.
   Reconcile the two sources of truth (`PRODUCTION_RECIPES` vs `MANUFACTURER_PRODUCT_LINES`) so
   they don't drift — ideally derive one from the other or add a test asserting every
   `MANUFACTURER_PRODUCT_LINES` key has a matching recipe.
2. **Make `TransportEquipment` producible from the start** to the same degree as the other
   manufacturer lines: confirm it isn't gated behind a capital item the Manufacturer doesn't
   begin with, and that with the Manufacturer's starting inputs it has non-zero
   `max_producible` (so Decision Hints shows "Produce TransportEquipment", not "Unblock"). If a
   capital gate is intended (e.g. a shipyard for high-end transport), make that explicit and
   documented rather than an accidental side effect of the recipe/capacity tables.
3. **Verify the full product-line set is offered** in `_choose_product_line` /
   `_offer_product_line_choices` (`engine/turn.py`) and in the capacity payload: all five —
   FarmMachinery, Goods, MiningEquipment, MedicalDevices, TransportEquipment.

## Tests

- Every `MANUFACTURER_PRODUCT_LINES` key has a corresponding `PRODUCTION_RECIPES` entry (guard
  test) — catches the Goods gap and prevents regressions.
- A Manufacturer with starting inventory has non-zero `max_producible` for Goods and
  TransportEquipment in the capacity payload.
- Full `pytest` suite green (baseline: **811 passing**).

## Open question for the user (note in PR)

- Should high-end TransportEquipment require a capital item (e.g. shipyard) to build, or be
  freely producible like FarmMachinery? Default: **freely producible** (match the others).
