# Economics-Modelling Vision — Gap Analysis & Action Plan (2026-07-03)

Audit of the engine (pre-release @ `9938d48`) against Ash's economics-modelling
design goals. Each vision element is graded **DONE / PARTIAL / GAP** with the
code evidence, followed by a prioritized action plan. Items marked ⚙ are
brief-able as Codex tasks; items marked ✂ are surgical (integrator-scale).

---

## Scorecard

| # | Vision element | Status |
|---|----------------|--------|
| 1 | Each island produces outputs required by other islands | **DONE** |
| 2 | Outputs require inputs, generally purchased from other islands | **PARTIAL** — Educator & Banker consume nothing |
| 3 | Three worker tiers (unskilled / technical / academic), recruited from population | **DONE** |
| 4 | Islands equipped with capital equipment used to produce | **DONE** |
| 5 | Productivity = f(inputs, equipment, worker availability/experience/quals) | **DONE** (expertise-degradation floor scaffolded, disabled) |
| 6 | Seasons + events (disasters, pandemics, booms) affect productivity, machinery, workers | **PARTIAL** — yields ✓; machinery & worker-availability channels not wired |
| 7 | Manufacturer produces capital *capacity*; larger equipment consumes more units; spares + random failures | **PARTIAL** — capacity gating ✓, failures+spares ✓; unit consumption is flat 1 |
| 8 | Banking gated on capital + qualified bankers/clerks; insurance on actuaries/analysts | **PARTIAL** — insurance needs Actuary ✓; loans ungated |
| 9 | Medical island's HealthServices reduce disease/injury impact, improve QoL | **GAP** — HealthServices has no mechanical effect |
| 10 | Transport produces passenger seats (people) + freight (goods/machinery) | **DONE** (minor gap: capital-delivery freight) |
| 11 | One island produces oil, ore, and metal from oil + ore | **DONE** |
| 12 | Every island depends & is depended upon; all competitive | **PARTIAL** — Banker ~28%, Miner ~8%, Doctor ~9–12% vs ~14.3% par |

---

## Evidence per element

### 1. Cross-island outputs — DONE
Seven roles each with distinct outputs (`BASE_PRODUCTION`, `MANUFACTURER_PRODUCT_LINES`,
`FARMER_SEASONAL_CONVERSION` in constants.py). Consumers exist for every output
class (production inputs, capital orders, training, consumer demand loop).

### 2. Purchased inputs — PARTIAL
`PRODUCTION_INPUTS` (constants.py:181): Farmer←Oil; Miner←Oil+Freight;
Transporter←Oil+Food; Doctor←Expertise+Oil+Ore; Manufacturer←Metal+Oil(+Freight
per line); Metal←Ore×2+Oil (`OUTPUT_PRODUCTION_INPUTS`). **But Educator and
Banker have empty input maps** — they sell into the economy without buying from
it, weakening the "every island depends" loop (element 12).

### 3. Three-tier workforce — DONE
`WorkerBand` (profession.py:68): MANAGER (university-educated) / TECHNICIAN
(apprenticeship) / WORKER (untrained) — exactly the academic/technical/unskilled
triad. Population pool with recruit cap (`MAX_WORKFORCE_FRACTION_OF_POPULATION`,
player.py:620) and a Recruit action drawing unskilled residents.

### 4. Capital equipment — DONE
`CAPITAL_CATALOGUE` + capacity recipes (`constants_capacity.py`,
`models/capacity.py`); product lines gated on owning the right equipment.

### 5. Productivity function — DONE
Per-line skilled/unskilled labour requirements, worker efficiency from training
level + experience plateaus, `production_capacity`, event yield modifiers.
One dormant seam: `EXPERTISE_DEGRADATION_ENABLED = False` (graceful-degradation
floor, needs recalibration before activation — turn.py:1038 comment).

### 6. Seasons & events — PARTIAL
- Seasonal yields ✓ (`SEASONAL_YIELD` all roles, `FARMER_SEASONAL_CONVERSION`).
- Event charts ✓ (`config/event_charts.yaml`): per-role charts including Bumper
  Harvest, Drought, Earthquake, Flood, Rich Vein, Mine Collapse, Transport
  Strike, Pandemic Closure, Bull Market, Credit Crunch, Factory Fire, Disease
  Outbreak, Pandemic — natural disasters cascade at 0.5 (events.py:206).
- **Machinery channel missing**: `_capital_failure_multiplier` returns the
  constant 1.0 — its own docstring says disasters/strikes should raise the
  hazard "until those events are wired in" (game.py:929).
- **Worker-availability channel missing**: pandemics/disease events modify
  yield only; they don't sideline workers. Workplace injuries/fatalities exist
  (workforce_events.py) but are independent of the event system.

### 7. Manufacturer capacity model — PARTIAL (core is real)
- Capital orders route through the Manufacturer; settlement **requires and
  consumes the matching manufactured resource** (FarmMachinery / MiningEquipment /
  MedicalDevices / TransportEquipment) and **fails when stock is zero**
  (app.py:3841 "has no X to build Y") — the "capacity for capital equipment"
  vision is implemented.
- **Gap: consumption is flat** — settlement gives back exactly 1 unit
  regardless of item scale (`give_resources(manufactured_resource, 1)`).
  Vision: a shipyard-scale item should consume several capacity units and cost
  proportionally; a small crusher one.
- Spares ✓ (tradable 12 Dp, Metal 2+Oil 1→4 kits, repairs consume kits,
  AI buy-buffer — merged 2026-07-03 `b72164b`).
- Random failures ✓ with an **age-based hazard curve** per unit
  (`_failure_probability_for_age`, per-quarter rolls, warranty windows) —
  "failure patterns of complex equipment" satisfied at the age dimension;
  no per-item-complexity rate differentiation yet (all items share the curve).

### 8. Banking gating — PARTIAL
- Insurance: requires ≥1 Actuary ✓ (ws_adapter.py:83). No analyst-tier scaling.
- Loans: **no staffing or capital gate**. `LoanLedger` carries Phase-D
  reserve-ratio bookkeeping fields but they default 0.0 and don't constrain
  issuance; vault/trading-floor capital items don't set lending capacity.

### 9. Medical HealthServices — GAP
`HealthServices` is produced and appears in the consumer demand loop
(consumer.py:61) — i.e. it's a revenue sink only. Injury/fatality mitigation is
wired to **Banker insurance** (medical insurance halves injury rate, life
insurance halves fatalities — workforce_events.py:84-152), not to the Doctor's
product. Vaccines exist for flu dosing (flu.py). The medical island's headline
output does nothing mechanical for buyers — this is the largest single
divergence from the vision, and plausibly part of the Doctor's ~9–12% share.

### 10. Transport — DONE (one check)
Freight charged on every market trade (`apply_freight_charge`, trading.py),
per-line manufacturing freight surcharges, repair shipping consumes freight
(`EQUIPMENT_REPAIR_SHIP_FREIGHT`), passenger seats/air tickets consumed by
training transport. **Confirmed minor gap**: capital-equipment *delivery*
consumes no freight (repair shipping and consumer deliveries do —
`EQUIPMENT_REPAIR_SHIP_FREIGHT`, `CONSUMER_DELIVERY_FREIGHT_FEE_PER_UNIT` —
but capital settlement has no freight leg).

### 11. Miner chain — DONE
Ore + Oil outputs; Metal smelted from Ore×2 + Oil×1; enhanced crusher-smelter
shifts the recipe. Matches "oil, ore and metal from oil and ore" exactly.

### 12. Balance / competitiveness — PARTIAL (known)
1000-game sim shares: Banker ~28%, Manufacturer ~10.9%, Doctor ~9–12%,
Miner ~8% against ~14.3% par. `workforce-participation-rebalance-2026-07-01.md`
brief already queued with Codex.

---

## Action plan (prioritized)

### P1 — vision-critical mechanics

**A. Make HealthServices mechanically real (Doctor)** ⚙
Purchased HealthServices stock should reduce disease/injury impact and improve
QoL, alongside (not replacing) insurance:
- Consume held HealthServices during workplace-risk rolls → injury-rate
  reduction (stacking rule vs medical insurance: multiplicative, capped).
- Disease Outbreak / Pandemic events check buyer's HealthServices (and
  Vaccine) stock → mitigate the yield/worker hit.
- QoL: HealthServices consumption feeds population growth modifier.
- Sim gate: Doctor share moves toward par without unbalancing Banker insurance.
Files: workforce_events.py, events.py, consumer.py, constants.py.

**B. Capacity-unit scaling for capital orders (Manufacturer)** ⚙
Add `capacity_units` per catalogue item (board-scale: 1 for small tools up to
3–4 for shipyard/liner-class). Settlement requires and consumes N units;
list/negotiated price already scales via catalogue cost. AI buy-buffer and
order-desk previews updated to show units. Sim gate: Manufacturer share stable
(±1pt) — pure availability constraint, not a price change.
Files: constants_capacity.py, turn.py `_manufactured_resource_for_capital_item`
neighborhood, app.py settlement, engine/ai.py.

**C. Banking staffing + capital gates (Banker)** ⚙
- Loans: lending capacity = f(vault/trading-floor capital, Banker-profession
  headcount); clerks (Technician band) scale concurrent-loan count. Activate
  the dormant Phase-D reserve-ratio fields as the constraint.
- Insurance: Actuary required (exists) + actuarial-analyst count caps policies
  in force.
- This is also the natural brake on the Banker's 28% over-performance —
  coordinate with the workforce-rebalance brief rather than double-nerfing.
Files: models/loan.py, turn.py loan/insurance actions, ws_adapter gating.

**D. Wire events into machinery & worker availability** ✂/⚙
- `_capital_failure_multiplier`: earthquake/flood/strike multiply failure
  hazard (the seam exists with a docstring promising exactly this).
- Pandemic/Disease Outbreak: temporarily sideline a fraction of workforce
  (availability, not death), mitigated by HealthServices/Vaccine (ties into A).
Files: game.py:929, events.py, workforce_events.py.

### P2 — dependence tightening

**E. Educator & Banker input dependence** ⚙ (design decision first)
Give both a purchased input so every island buys: e.g. Educator consumes Goods
(teaching materials) per Courses run; Banker consumes Goods/Expertise
(operations) per season of active lending. Small quantities — dependence, not
a tax. Sim gate: no share moves >2pts.

**F. Capital-delivery freight** ✂
Add a freight charge on capital-order delivery (machinery transfer between
islands) — mirrors the existing repair-shipping freight leg. Confirmed absent.

### P3 — calibration (in flight)

**G. Workforce-participation rebalance** — already briefed
(`workforce-participation-rebalance-2026-07-01.md`, awaiting Codex). Re-baseline
after A–C land, since they move the same islands.

**H. Expertise-degradation floor** — re-tune and enable
`EXPERTISE_DEGRADATION_ENABLED` once A–C settle (it failed calibration when
first attempted; the hook is callable and tested).

### Sequencing note
A and C both shift Doctor/Banker economics — land them before re-running G's
calibration. B and D are orthogonal to share balance and can go any time.
Every item gets the standard 1000-game seed-42 sim gate before merge
(lesson from the spares delivery: verify against the same base commit).
