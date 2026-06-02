# Brief — Lab Supplies/Reagents split + Kitchen tiers (2026-06-02)

**Status:** **Lab split (A) DONE** on `claude/lab-split-2026-06-02` (729 green).
Kitchens (C) with Codex. Original: **TEED UP FOR BUILD (2026-06-02).** Open `[CONFIRM]` params below are
now locked to the defaults in this Decisions block; all are **tunable in the
calibration pass** that follows this batch. Split: **Codex builds the kitchens**
(`requirements/codex-tasks/kitchen-tiers-2026-06-02.md`); **Claude builds the
lab split** (A1–A3, invasive rename + save-migration). Courses-production fix
already shipped.

## Locked decisions (2026-06-02)
- **Resource name:** `LaboratoryEquipment` → **`Reagents`** (display "Reagents").
  Chosen over "Lab Supplies" because it's unambiguous vs. the new durable
  "Laboratory Equipment" capital item.
- **Reagents production (Medical Sciences / Doctor):** a Doctor output line
  consuming **1 Oil + 1 Ore → 6 Reagents/season** (modest; Reagents are consumed
  in small per-unit amounts). Removed from `MANUFACTURER_PRODUCT_LINES`. Doctor
  keeps HealthServices + Vaccine; Educator/Doctor still *consume* Reagents.
- **New "Laboratory Equipment" capital** (`common.laboratory_equipment`):
  durable, cost **40 Dp**, delivery 1 season; passive capacity boost
  `effects.capacity = {Food:+2, Grain:+2, Ore:+2, HealthServices:+2, Vaccine:+1}`
  so it helps Agriculture, Mining, Medical (soil/sample testing). Passive boost,
  not an unlock.
- **Industrial Kitchen** (`common.industrial_kitchen`): opening-investment
  option, **20 Food/season, NO Chef**, cost **150 Dp**.
- **Manufacturing Kitchen** (existing `common.kitchen`): **10 Food/season**
  (up from 6), **still needs a Chef**, cost unchanged.
- **Industrial recipe efficiency:** keep the 2:1:1 ratio but the Industrial line
  is more efficient — **1 Grain + 0.5 Produce + 0.5 Protein per Food** (so 20
  Food = 20 Grain + 10 Produce + 10 Protein/season), vs. the manual kitchen's
  2:1:1. Keeps the ingredient load sane for a 20-Food run.

---

## A. "Laboratory Equipment" → consumable *Reagents* + new durable *Lab Equipment* capital

Today `LaboratoryEquipment` is a single **consumable resource**: a Manufacturer
product line, consumed each season by Educator (Expertise/Courses/Patents) and
Doctor. The name reads like durable capital, which it isn't. Split into two
distinct things:

### A1. Rename the consumable resource
- `ResourceType.LABORATORY_EQUIPMENT` value `"LaboratoryEquipment"` →
  **`"LabSupplies"`** (display **"Lab Supplies"**). **[CONFIRM name]** (user
  offered "Lab Supplies / Reagents" — I'll use *Lab Supplies* unless you prefer
  *Reagents*).
- Ripple: `BASE_PRICES`, `STARTING_INVENTORY`, `PRODUCTION_INPUTS`,
  `PRODUCTION_RECIPES`, `MANUFACTURER_PRODUCT_LINES`, capital-catalogue
  `effects`, the resource enum, UI labels, and a **save-migration** (old saves
  with `"LaboratoryEquipment"` inventory keys → `"LabSupplies"`).

### A2. Move production from Manufacturer → Medical Sciences (Doctor)
- Remove `LaboratoryEquipment`/Lab Supplies from `MANUFACTURER_PRODUCT_LINES`.
- The **Medical Sciences island (Doctor)** produces Lab Supplies from **Oil +
  Ore**. Proposed recipe **[CONFIRM]**: `2 Oil + 2 Ore → 10 Lab Supplies`
  per season (a Doctor output line, scaled like other outputs). Doctor's
  existing outputs (HealthServices, Vaccine) stay.
- Doctor still *consumes* Lab Supplies where it does today — i.e. Medical both
  produces (for sale to Educator) and self-consumes. **[CONFIRM]** this is
  intended (it is the natural reading: the lab makes its own reagents).

### A3. New durable capital item: "Laboratory Equipment" (soil/sample testing)
- New `CAPITAL_CATALOGUE` item `common.laboratory_equipment` **[CONFIRM id]**,
  durable (depreciates like other capital), usable by **Mining, Medical,
  Agriculture**.
- Effect (soil/sample testing → a yield/capacity boost). Proposed **[CONFIRM]**:
  `+capacity` to each role's primary output — e.g. Agriculture Food/Grain,
  Mining Ore, Medical HealthServices — say **+2 capacity** to the role's main
  output, cost ~**40 Dp**, delivery 1 season. Exact effect map needs your call
  (which output(s) each role boosts, and by how much).

> Open question for A3: is "Laboratory Equipment" a **prerequisite/unlock** for
> something (e.g. enables a soil-testing action or a quality bonus), or purely a
> passive capacity boost? Defaulting to passive capacity boost unless told.

---

## C. Kitchen tiers (Food production)

Today there is one `common.kitchen` capital item: produces
`KITCHEN_FOOD_PER_SEASON = 6` Food/season, runs automatically **only when
Chef-staffed**, consuming `KITCHEN_RECIPE` (2 Grain + 1 Produce + 1 Protein per
Food). Replace with two tiers:

### C1. Industrial Kitchen (opening-investment option)
- New capital item `common.industrial_kitchen` **[CONFIRM id]**, offered in the
  **opening investing catalogue** (and buyable later).
- **20 Food/season**, **no Chef required** (automated). **[CONFIRM no-chef]**
- Consumes ingredients pro-rata: at the current 2:1:1 recipe, 20 Food needs
  40 Grain + 20 Produce + 20 Protein/season — **[CONFIRM]** that ingredient
  load is acceptable, or scale the recipe down for the industrial line.
- Cost **[CONFIRM]** ~**150 Dp** (it's a major opening asset).

### C2. Manufacturing Kitchen (the chef-staffed one)
- The existing `common.kitchen` (sold by Manufacturing) → **10 Food/season**
  (up from 6), **still requires a Chef**.
- Cost unchanged **[CONFIRM]**.

### C3. Engine
- `run_kitchens` / `_run_one_kitchen` (`engine/production.py`) currently assume
  one kitchen type + a global Chef gate. Generalise to **per-item** food output
  and **per-item** chef requirement (Industrial = no chef, Manufacturing = chef).
- Keep idle-reason logging ("Industrial Kitchen idle: short on Grain" /
  "Kitchen idle: needs a Chef") so the player sees why.
- Surface a hint when an island holds a kitchen that can't run (missing chef or
  ingredients) — addresses the "I expected an option to make food" confusion.

---

## 3. Suggested execution split

| Piece | Owner | Files |
|---|---|---|
| A1 rename + save-migration | one owner (rename is invasive, do atomically) | `resource.py`, `constants.py`, `constants_capacity.py`, `game.py` save/load, UI labels |
| A2 Doctor reagent line + remove Manufacturer line | same owner as A1 (same constants) | `constants.py`, `constants_capacity.py` |
| A3 new Lab Equipment capital + effects | can follow A1/A2 | `constants_capacity.py`, capacity engine |
| C kitchen tiers | **independent** of A — good parallel candidate (Codex) | `constants.py`, `engine/production.py`, capital catalogue, UI hint |

A1–A3 share the constants/recipe files, so one owner should do them as a unit
(the rename touching every reference makes parallel edits conflict-prone). C is
cleanly separable (kitchen capital + `production.py::run_kitchens`) and is the
natural Codex hand-off if we want parallelism.

---

## 4. Tests
- A1: save with old `LaboratoryEquipment` key loads as `LabSupplies`; prices/
  recipes resolve; no dangling `"LaboratoryEquipment"` string references.
- A2: Doctor produces Lab Supplies from Oil+Ore; Manufacturer no longer offers
  the line; Educator can still buy Lab Supplies to run Courses.
- A3: owning Lab Equipment raises the boosted output's capacity for Mining/
  Medical/Agriculture; depreciates.
- C1/C2: Industrial Kitchen yields 20 Food/season without a Chef; Manufacturing
  Kitchen yields 10 with a Chef and is idle without one; both gate on
  ingredients with a clear idle reason.
