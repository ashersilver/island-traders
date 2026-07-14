# Brief — Manufacturer Capacity Scaling & Equipment Lifecycle Parity (2026-07-04)

**Status: APPROVED DIRECTION (Ash 2026-07-04) — implementation-ready.**
**Suggested owner:** Codex (engine + settlement) ; Claude integrates + order-desk UI.
**Base off:** `origin/pre-release` @ `9938d48`, APP_VERSION `0.1.5-dev.2026-06-22.18`.
**Follows:** `_README.md` working agreement.

## Problem

Capital-order settlement consumes exactly **1** manufactured unit regardless of
scale (`app.py` settlement: `give_resources(manufactured_resource, 1)`); a
shipyard costs the Manufacturer the same capacity as a hand crusher. There is
no cash cost to run a build, no seasonal ceiling on durable-equipment output,
repairs consume a flat 1 Spares kit, and invest-phase / cash_only equipment
never fails (only ordered units get per-unit failure rolls).

## Design

### 1. `capacity_units` per catalogue item

New `CapitalItem.capacity_units: int = 1` (models/capacity.py). Rule of thumb
`clamp(round(cost/80), 1, 4)`, then hand-tuned. Initial table (non-cash_only):

| Item (examples) | cost | units |
|---|---|---|
| tractor, crusher, storage_building | ≤80 | 1 |
| harvester ("Combine Harvester"), livestock_barn, hospital_ward, excavator | ~90–150 | 2 |
| oil_rig, refinery, enhanced_crusher_smelter, operating_theatre, cargo_ship | ~160–260 | 3 |
| shipyard, passenger_liner, cargo_plane, research_lab | ≥280 | 4 |

Codex: generate the full table from the live catalogue with the rule, list it
in the PR description, and apply judgment where flavour demands (a plane is 4
even if cost says 3).

- **Settlement** (`app.py` `_settle_capital_negotiation`): require
  `manufacturer.inventory >= item.capacity_units` of the matching resource,
  error message includes the shortfall ("needs 3 × TransportEquipment, has 1"),
  consume `capacity_units`.
- **Order desk / capital picker UI**: show units per item and the
  Manufacturer's current stock of the matching resource.
- AI (`engine/ai.py`): buy-buffer and order heuristics account for units.

### 2. Build cash cost per line run

New `build_cost_dollops` per MANUFACTURER_PRODUCT_LINES entry — consumables/
energy overhead, paid by the Manufacturer on produce:

| Line | Dp per unit produced |
|---|---|
| FarmMachinery | 3 |
| MiningEquipment | 4 |
| TransportEquipment | 4 |
| MedicalDevices | 3 |
| Spares | 1 |
| Goods | 0.2 |

Insufficient cash blocks the run with a clear message (and shows in the
produce-button context line: "· 3 Dp/unit build cost").

### 3. Seasonal durable-output cap

`MANUFACTURER_DURABLE_CAP_BASE = 6` units/season summed across the four
durable equipment lines (FarmMachinery, MiningEquipment, TransportEquipment,
MedicalDevices — Goods and Spares uncapped). Owning **assembly_line** → +2;
**precision_workshop** → +2 (max 10). Enforced in `production_options` /
`produce_product` (max_qty clamps against remaining seasonal allowance);
allowance surfaces in the produce-button context and the capacity panel.
This is "invest in your own capacity to grow" made literal.

### 4. Failure parity for all owned equipment

Every owned capital unit — invest-phase, ordered, leased, cash_only (kitchens)
— becomes a `capital_units` entry with `acquired_tick` and takes the standard
age-based failure roll (`_process_equipment_failures`). Invest-phase items
currently outside the per-unit system get backfilled units at game start.
Audit pass: any catalogue item with empty `effects` gets a minimal benefit
(there should be none — list in PR if found). cash_only items repair with
Spares like everything else.

### 5. Proportional spares on repair

Repair consumes `item.capacity_units × 1` Spares (Combine Harvester at 2 units
→ 2 kits), same freight legs as today (`EQUIPMENT_REPAIR_SHIP_FREIGHT`/`AIR`).
Repair quotes, the AI spares buy-buffer (target stock = 2 × max owned
capacity_units), and the deficiency report all update.

## Files

models/capacity.py, constants_capacity.py (units table),
constants.py (cap + build costs), engine/production.py (cap clamp, build cost),
engine/game.py (failure parity backfill, proportional spares),
server/app.py (settlement N units), engine/ai.py, server UI (Claude).

## Acceptance criteria

1. Ordering a 3-unit item with 2 in stock fails with the shortfall message;
   with 3 in stock consumes exactly 3.
2. Durable lines refuse output beyond the seasonal allowance; allowance rises
   with assembly_line/precision_workshop ownership.
3. A failed 2-unit item's repair consumes 2 Spares; 1 kit on hand → repair
   pends (existing pending-repair path).
4. An invest-phase tractor can fail and be repaired like an ordered one.
5. Full pytest; **1000-game seed-42 sim**: Manufacturer share within ±1pt of
   baseline (availability constraint, not a price change); Spares consumption
   per game rises; no other role moves >2pts. Quote before/after tables in PR.

## Out of scope

Capital-delivery freight (separate ✂ item), per-item failure-rate curves
(all items keep the shared age curve for now), loan/financing changes (P1.3).
