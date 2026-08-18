# BOM package — per-item build inputs, mapping fixes, Biochemicals (2026-08-12)

Ash-approved design (2026-08-12 session, network diagram signed off). Goal:
machinery must *cost* the Manufacturer real inputs scaled to perceived value —
subassemblies it can pre-build for stock, extra energy for long builds, and
sea freight for anything physically shipped — and the commodity tiers get a
value-added cross-island chain (Biochemicals).

**Base off `claude/wave7.3-cnc-workshop` (PR #248), or `origin/pre-release`
once #248 is merged** — the CNC Workshop item must exist so it gets a BOM.

**Workflow (working agreement):** work in your own clone; DO NOT `git commit`
(sandbox keeps `.git` read-only) — report "files ready at <path>"; Claude
reviews, runs the full suite, commits with your attribution, and PRs.
Do NOT touch `STARTING_INVENTORY` or run deep price calibration — Claude
re-derives starting inventory and runs the multi-seed calibration afterwards
as part of the 0.1.6 release pass.

## Part A — `build_inputs`: per-item capital BOM (engine change)

Today a capital build consumes only `capacity_units ×` one role-mapped
equipment resource (`_manufactured_resource_for_capital_item`,
engine/turn.py). Add an explicit per-item BOM:

1. **Field** — `models/capacity.py` `CapitalItem`: add
   `build_inputs: dict[str, float] = field(default_factory=dict)`
   (resource-name → qty). Semantics: consumed by the MANUFACTURER at
   settlement, IN ADDITION to nothing — when `build_inputs` is non-empty it
   REPLACES the legacy role-mapped `capacity_units` consumption entirely
   (subassemblies are listed explicitly in the BOM). When empty, legacy
   behaviour is unchanged (fallback path stays).
2. **Catalogue rebuild** — `constants_capacity.py`
   `_multiply_capital_capacity` reconstructs every `CapitalItem`
   field-by-field: it MUST copy `build_inputs` through (unscaled — BOMs are
   player-facing units).
3. **Settlement** — `server/app.py` `_settle_capital_negotiation`: when the
   item has `build_inputs`, verify the manufacturer holds every listed
   resource (mirror the existing guard style) and consume them all at the
   point the legacy path calls `give_resources(manufactured_resource,
   required_units)`. `cash_only` items skip as today. The Wave 5.3 self-build
   (20% price) path still consumes the BOM.
4. **Feasibility everywhere settlement is reachable** —
   `_handle_capital_order` accept-time check and
   `_capital_negotiation_units_short` (the Wave-9 backorder drain gate) must
   account for `build_inputs`: units_short = the max shortfall across BOM
   lines (so a queued order waits until the WHOLE BOM is on hand; keep the
   head-of-queue blocking semantics). No resource escrow at order time —
   consume only at settlement, exactly like today.
5. **What-If / order desk** — wherever the client is told "needs N ×
   <resource>" for a capital order, surface the BOM lines instead of the
   single resource (search for `units_required` payload fields).

## Part B — the BOMs (catalogue data)

Legend: FM/ME/TE/MD/G = FarmMachinery / MiningEquipment / TransportEquipment /
MedicalDevices / Goods subassembly units; Oil = build energy (scales with
`delivery_seasons`); Freight = sea shipping (self-propelled craft = 0).

| item | build_inputs |
|---|---|
| farmer.tractor | FM 1, Oil 1, Freight 1 |
| farmer.harvester | FM 2, Oil 4, Freight 2 |
| farmer.fishing_boat | FM 1, Oil 2 |
| farmer.livestock_barn | FM 2, Oil 1, Freight 1 |
| farmer.industrial_kitchen | FM 1, Oil 2, Freight 1 |
| farmer.storage_building | FM 1, Oil 1, Freight 1 |
| miner.excavator | ME 2, Oil 2, Freight 2 |
| miner.crusher | ME 1, Oil 2, Freight 1 |
| miner.enhanced_crusher_smelter | ME 3, Oil 6, Freight 2 |
| miner.oil_rig | ME 3, Oil 6, Freight 4  ← sea platform, the flagship case |
| miner.refinery | ME 3, Oil 6, Freight 3 |
| transporter.cargo_ship | TE 3, Oil 2 |
| transporter.cargo_plane | TE 4, Oil 4 |
| transporter.passenger_liner | TE 3, Oil 2 |
| transporter.passenger_plane | TE 4, Oil 4 |
| educator.lecture_hall | G 1, Oil 1, Freight 1 |
| educator.library | G 1, Oil 1, Freight 1 |
| educator.research_lab | G 2, MD 2, Oil 4, Freight 1 |
| educator.computer_cluster | G 2, Oil 3, Freight 1 |
| educator.technical_workshop | G 1, ME 1, Oil 1, Freight 1 |
| banker.vault | G 1, Metal 3, Oil 1, Freight 1 |
| banker.trading_floor | G 2, Oil 1, Freight 1 |
| banker.underwriting_desk | G 1, Oil 1 |
| banker.reinsurance_treaty | (convert to cash_only — it's paper) |
| manufacturer.foundry | ME 1, Metal 2, Oil 2, Freight 1 |
| manufacturer.assembly_line | ME 1, Oil 2, Freight 1 |
| manufacturer.small_warehouse | G 1, Oil 1 |
| manufacturer.warehouse | G 1, Metal 1, Oil 1, Freight 1 |
| manufacturer.precision_workshop | ME 2, Oil 4, Freight 1 |
| manufacturer.cnc_workshop | ME 2, Oil 4, Freight 1 |
| manufacturer.shipyard | ME 2, TE 2, Oil 6, Freight 2 |
| doctor.hospital_ward | MD 2, Oil 1, Freight 1 |
| doctor.operating_theatre | MD 3, Oil 4, Freight 1 |
| doctor.vaccine_lab | MD 2, Oil 4, Freight 1 |
| doctor.cold_chain_storage | MD 1, Oil 2, Freight 1 |
| doctor.pathology_lab | MD 1, Oil 1, Freight 1 |
| doctor.reagent_lab | MD 1, Oil 2, Freight 1 |
| Transporter bulk/cold warehouses (7.2b) | G 1, Metal 1, Oil 1, Freight 1 each |
| common.* kitchens / laboratory_equipment | keep cash_only |

Any item added since this table was drafted: derive by analogy (subassembly
by role/nature, Oil ≈ 1 + 2×delivery_seasons ± energy_intensive, Freight by
sea/heaviness, self-propelled = 0).

**Cost re-derivation (perceived value):** recompute each item's `cost` as
round(BOM value at BASE_PRICES × 1.6 margin, to a clean number). The oil
rig must land far above the tractor — that's the point. Keep relative
ordering sensible; flag any item whose new cost moves >3× either way.

## Part C — Biochemicals (new commodity) + second-order BOM tweaks

New cross-island value chain: **Miner refines it, Doctor pharma-grades it.**

1. `ResourceType.BIOCHEMICALS = "Biochemicals"` (tradable). BASE_PRICES ≈ 14
   (placeholder — Claude's calibration pass finalises).
2. **Miner production**: BASE_PRODUCTION adds Biochemicals ~2/season (small);
   gate it on the **Refinery** via equipment capacity — add
   `"Biochemicals": N` to `miner.refinery` effects capacity so no refinery →
   equipment_cap 0 → cannot produce. PRODUCTION_RECIPES entry:
   `Miner / Biochemicals: inputs {Oil 1.0, Ore 0.5}` (+ sensible labour).
3. **Reagents re-based** (Doctor): inputs become
   `{Biochemicals 1.0, Expertise 0.25}` (was Oil+Ore). Update both
   PRODUCTION_RECIPES and any Doctor line data.
4. **Industrial chemistry split**: MedicalDevices inputs += Biochemicals 0.5;
   Goods inputs += Biochemicals 0.25 — in BOTH `MANUFACTURER_PRODUCT_LINES`
   (constants.py) and the canonical `PRODUCTION_RECIPES`
   (constants_capacity.py). Patents stay on Reagents.
5. Food inputs += Oil 0.25 (processing energy) — both structures if present.
6. `dependency_graph.py` should pick the new edges up automatically from
   PRODUCTION_RECIPES — verify the dependency map renders Biochemicals.
7. AI/agent awareness: the engine sim AI trades on generic price signals — no
   persona work needed here; do NOT edit the separate agents repo.

## Verification gates

- Full pytest green; new tests: settlement consumes the BOM (and blocks /
  queues when short), backorder drain waits for the whole BOM, catalogue
  completeness (every non-cash-only item has a BOM), `_multiply_...` copies
  the field, cost ≈ BOM value × margin sanity, Biochemicals recipe + refinery
  gate, Reagents/Goods/MedicalDevices new inputs, zero conjured resources.
- 3 same-seed sims (42/7/100) vs base: every role within ±10% mean net worth
  (this WILL shift the economy — that's expected; Claude recalibrates after —
  but flag anything beyond ±10%).
- Flow-health report (produced/consumed/traded per game) for Biochemicals,
  Freight, Metal, Oil — a dead Biochemicals line is a finding, not a failure.

Deliverable: files ready in your clone + a summary of test results, sim
numbers, and the flow-health table. Claude integrates.
