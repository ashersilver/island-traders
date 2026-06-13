# Brief — Equipment as durable capital + Metal smelted from Ore (2026-06-12)

**Suggested owner:** Codex (production model + economy; needs a recalibration pass).
**Base off:** current `origin/pre-release`.
**Issues:** file two — "Production: equipment (FarmMachinery/MiningEquipment) is a
durable capital good, not a per-season consumable" (`area: economy`) and
"Production: Metal is smelted from Ore + energy" (`area: economy`). From
maintainer playtest 2026-06-12. **Part 1 fixes an active gameplay break** (the
whole archipelago starves when the Farmer runs out of FarmMachinery).

---

## Part 1 — Equipment is durable capital, not a consumable

### The bug
`FarmMachinery` and `MiningEquipment` exist in **two contradictory forms**:
1. **Durable capital** — `farmer.tractor` etc. in `constants_capacity.py`
   (`cost`, `effects.capacity`, depreciation `service_life_seasons`). Correct.
2. **Consumable resource** — Manufacturer outputs (`MANUFACTURER_PRODUCT_LINES`)
   that producers **burn 1/season** as a hard-gated input
   (`FARMER_SEASONAL_CONVERSION` inputs `{FarmMachinery:1, Oil:1}`;
   `PRODUCTION_INPUTS["Miner"]` `{Oil:1, Freight:1, MiningEquipment:1}`).

Consuming a whole tractor every season to grow crops is economically incoherent,
and because `produce()` **hard-raises `InsufficientInputsError` with no floor**
(`engine/production.py`), a FarmMachinery stockout drops Farmer output to **zero**
→ no Food → **the whole chain starves**. The Farmer only carries a 2-season
buffer, so any hiccup in the Manufacturer→Farmer supply triggers it.

### Maintainer decision
**Make equipment durable capital, not a per-season consumable.**

### Target model
- **Remove equipment from per-season *consumed* inputs.** Drop `FarmMachinery`
  from `FARMER_SEASONAL_CONVERSION` inputs and `MiningEquipment` from
  `PRODUCTION_INPUTS["Miner"]`. Genuine consumables (fuel = `Oil`, raw materials)
  stay. After this, an equipment shortage **cannot zero production** — output
  scales with capital capacity over the `production_capacity` floor (the capacity
  model already exists: `effective_capital_inventory`, `effects.capacity`,
  `production.py:474/540`).
- **The `FarmMachinery`/`MiningEquipment` *resource* stays tradeable but installs
  as durable capital on acquisition** (recommended — keeps the Manufacturer's
  market). When a producer buys/receives a unit of the equipment resource, it is
  added to their capital inventory as the corresponding durable item (depreciating
  over `service_life_seasons`, boosting `effects.capacity`), **not** held as a
  consumable. Reconcile with the existing `farmer.tractor`/`miner.*` capital items
  and the `_manufactured_resource_for_capital_item` mapping (`turn.py`) — pick one
  representation; don't leave both a consumable and a capital form of the same
  thing.
  - *Alternative if simpler:* deprecate the equipment resource entirely and have
    producers buy the capital items for cash directly from the Manufacturer. Costs
    the Manufacturer a tradeable line, so the install-as-capital route is preferred.
- **Production floor stays meaningful:** with no owned equipment, a producer still
  makes its `production_capacity` baseline (so Food never fully stops); owned
  equipment capital adds capacity on top. This is the real fix for the starvation.

### Watch-outs
- The Manufacturer's viability depends on selling equipment — keep demand intact
  (now durable, so it's periodic replacement demand driven by depreciation, not
  per-season). Make sure depreciation actually creates recurring replacement
  demand or the Manufacturer loses its market.
- This changes input costs across the board → **recalibrate** (Part 3).

---

## Part 2 — Metal is smelted from Ore (+ energy)

### The bug
The Miner produces **Ore, Metal, and Oil as parallel co-products** from a flat
seasonal input; **Metal has no Ore input** (`OUTPUT_PRODUCTION_INPUTS` only holds
`Educator/Patents`). So making Metal doesn't draw down Ore — there is no smelting
chain.

### Maintainer decision — **chain Metal from Ore + Oil.**
- Add `OUTPUT_PRODUCTION_INPUTS["Miner"]["Metal"] = {"Ore": N, "Oil": M}` (start
  ~`{Ore: 2, Oil: 1}` per Metal-batch unit; calibrate). The engine already
  supports per-output inputs via `_output_inputs` / `_affordable_output_inputs`
  (it skips an output the producer can't afford the specific inputs for), so Metal
  only smelts when Ore is on hand.
- **Within-season timing:** inputs are consumed from inventory at season start,
  but the Miner also *produces* Ore that same season (co-product). So smelting
  draws on the Miner's *starting/prior-season* Ore (starting inventory has Ore=3;
  each season's Ore output replenishes for the next). Confirm the steady state is
  sustainable; size `N` so the Miner can both sell some Ore and smelt Metal.
- Net effect: the Miner becomes a **net Ore consumer** (smelts part of its own
  ore), Metal supply now tracks Ore availability, and Ore↔Metal prices couple —
  realistic. Affects the Manufacturer (Metal is its key input) → recalibrate.

---

## Part 3 — Recalibration & acceptance
Both parts change the production economics the v0.1.2 balance was tuned against.
- **Acceptance:** full suite green; `--games 1000 --seed 42` shows (a) no
  Food/starvation collapse from equipment stockouts (B1/B2 `starvation` for
  FarmMachinery → ~0; Food trade/production stable), (b) Metal production draws
  down Ore (B1/B2 shows Ore consumed > 0 by the Miner), (c) the 7-role win-rate
  spread stays within roughly the v0.1.2 band (no role < ~8% or > ~22%), and
  (d) the Manufacturer keeps a viable equipment market (durable replacement
  demand). Report before/after win% + money supply + the relevant flows.
- APP_VERSION bump + RELEASE_NOTES (player-facing: equipment is now durable
  capital you own, not a consumable; mining smelts metal from ore).

## Anchors
`constants.py`: `FARMER_SEASONAL_CONVERSION`, `PRODUCTION_INPUTS`,
`BASE_PRODUCTION`, `OUTPUT_PRODUCTION_INPUTS`, `MANUFACTURER_PRODUCT_LINES`,
`STARTING_INVENTORY`. `constants_capacity.py`: `farmer.tractor` & the
Manufacturer `ProductionRecipe`s (L505+). `engine/production.py`: `produce`,
`_all_inputs`, `_output_inputs`, `_affordable_output_inputs`, the
`production_capacity` floor (L474/540). `engine/turn.py`:
`_manufactured_resource_for_capital_item`.
