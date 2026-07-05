# Brief — Economic Dependence: Energy Floor, Educator & Banker Inputs (2026-07-05)

**Status: APPROVED, §1 REVISED 2026-07-05 after Codex's sim probe — the energy
floor now targets fixed energy-intensive plant + softened brownout (see §1).**
P2a of the
economics-vision program. Pairs with `continuing-education-expertise-2026-07-05.md`
(P2b — the Expertise upkeep mechanic; land either order, both consume Expertise
from the same islands). **Suggested owner:** Codex ; Claude (UI: energy/brownout
+ student-load indicators). **Base off:** current `origin/pre-release`
(post-`51c4a9e`). **Follows:** `_README.md`.

## Goal

Close the two empty input rows (Educator, Banker) and give the Miner seven
steady Oil customers, so "every island depends and is depended upon" holds.
All quantities small — dependence, not taxation.

## 1. Universal energy floor (all seven islands)

**REVISED 2026-07-05 (Ash) — supersedes the "all capacity units" formula.**
The literal `1 + ceil(all_capacity_units / 4)` failed the sim badly (200-game
probe: 72% brownouts literal; after AI fixes, brownout <5% but Farmer collapsed
to 6.3% and Manufacturer spiked to 24.3%). Root cause: a per-island Oil charge
is *regressive* (huge share of a low-margin Farmer/Doctor's revenue, trivial for
the Manufacturer) and double-charges roles that already buy Oil to produce; the
−25% brownout cliff amplified any shortfall into a food/QoL cascade.

**New model — energy = grid electricity for FIXED, POWER-HUNGRY PLANT only:**

```
energy_oil(island) = ENERGY_BASE
                   + ceil( Σ capacity_units of owned ENERGY_INTENSIVE items
                           / ENERGY_DIVISOR )
```

- `ENERGY_BASE = 1` — flat, universal. This *is* the vision's "base level of oil
  aka energy": every island buys ≥1 Oil/season → seven Miner customers, minimal
  distortion.
- `ENERGY_DIVISOR = 4` — **the magnitude tuning knob** (raise to 6 or 8 to
  "halve" the surcharge).
- `ENERGY_INTENSIVE` — a new per-`CapitalItem` flag, **DEFAULT False**. True only
  for fixed, grid-powered heavy plant:
  - Miner: `refinery`, `oil_rig`, `enhanced_crusher_smelter`, `crusher`, `excavator`
  - Manufacturer: `foundry`, `assembly_line`, `precision_workshop`, `shipyard`
  - Doctor: `vaccine_lab`, `cold_chain_storage`, `operating_theatre`
  - Educator: `research_lab`, `computer_cluster`
  - **False (zero energy) for everything else** — storage/warehouses/sheds,
    offices (`vault`, `trading_floor`, `underwriting_desk`, `reinsurance_treaty`),
    classrooms (`lecture_hall`, `library`, `technical_workshop`), all kitchens,
    `hospital_ward`, `reagent_lab`, `laboratory_equipment`, and **all mobile
    fuel-burners** — tractors, harvesters, fishing boats, cargo/passenger
    **planes**, cargo ship, passenger liner. Their fuel is already a
    `PRODUCTION_INPUTS` Oil cost; an electricity floor would double-count.
  This targeting is deliberately *corrective*: it relieves Farmer/Transporter
  (mobile + storage = zero) and taxes the over-performing Manufacturer
  (foundry/shipyard), moving shares the right way, not just smaller.
- The Miner self-supplies its floor from own Oil (net free — its bump is intended).
- **On top of** existing `PRODUCTION_INPUTS` Oil.

**Brownout (unmet floor) — SOFTENED** (the −25% cliff was the cascade
amplifier): production capacity **−10%** and QoL Stability **−3**, **prorated by
the unmet fraction** (not all-or-nothing). Never a hard stop.

- New: `ENERGY_BASE = 1`, `ENERGY_DIVISOR = 4`, `BROWNOUT_CAPACITY_PENALTY = 0.10`,
  `BROWNOUT_QOL_PENALTY = 3`. `ENERGY_INTENSIVE` flag per catalogue item.
- AI: extend the spares-style buy-buffer to keep ≥ next-season floor of Oil.

**Tuning protocol (the sim gate is the arbiter):** start BASE 1 / DIVISOR 4 /
brownout −10%. Sweep `ENERGY_DIVISOR` up (6, 8 = "halve") until **brownout <5%
AND every non-Miner role within ±2pts** (Miner +1–2pts intended). If Doctor
stays >2pts low, lighten the medical intensive set (drop `cold_chain_storage`,
then `operating_theatre`) before touching BASE. Quote the swept constants +
before/after share±σ in the PR.

## 2. Student food via inflated population

Per Ash: the Educator feeds students by **adding in-residence students to the
population** used for the sustenance meal calculation — reuse `consume_sustenance`,
don't invent a per-student Food line.

- Educator's `meals_needed` computed on
  `population + students_in_residence_this_season` (count from
  `training.active_for_player` residents physically on campus).
- **Verify no double-feeding**: home islands must exclude away-trainees from
  their own sustenance via the existing `absent_residents` hook
  (player.py:723). If they don't today, wire it here so a worker is fed at
  exactly one island per season.
- Shortfall behaves like normal sustenance shortfall (existing FOOD ALERT +
  demand basket), scaled up by the student load.

## 3. Educator lab consumables

Extend the existing Patents-only Reagents gate
(`OUTPUT_PRODUCTION_INPUTS["Educator"]["Patents"]`) to lab-based output:
Courses **and** Expertise runs consume **Reagents 1 + Oil 1 per 10 output
units** produced. Classroom teaching (the base Courses/Expertise a Lecturer
delivers) is unaffected below the 10-unit step; only lab-scale runs pay.
Buyers: Doctor (Reagents), Miner (Oil).

## 4. Banker operating inputs

- Energy floor (§1) covers electricity — vaults/trading floors are power-hungry,
  so Banker uses divisor **/3** not /4 (`ENERGY_FLOOR_UNITS_PER_OIL` overridable
  per role; Banker = 3).
- **Office Goods**: 1 Goods per season while the Banker has ≥1 active loan or
  policy ("systems, stationery, furniture"). Unmet → no penalty beyond not
  having spent it (soft — it's flavour dependence on the Manufacturer, not a
  gate). `BANKER_OFFICE_GOODS_PER_SEASON = 1`.
- Food already covered by universal sustenance ✓.

## Files

constants.py (new constants), models/player.py (energy floor consumption,
student-inflated sustenance, absent_residents check), engine/game.py (season
upkeep order: sustenance → energy → production; brownout capacity hook),
engine/production.py (Educator lab step, brownout multiplier),
engine/consumer.py (unchanged), engine/ai.py (Oil buy-buffer), server UI (Claude).

## Acceptance criteria

1. An island whose ONLY energy-intensive plant is a shipyard (4 units) consumes
   `1 + ceil(4/4) = 2` Oil/season; an island with only a fishing boat + storage
   (both zero-energy) consumes just the `ENERGY_BASE = 1`. Unmet floor →
   −10% capacity + QoL −3, prorated by the unmet fraction (unit tests).
2. Educator with 4 in-residence students needs meals for population+4; a worker
   training away is fed only at the Educator (no double count).
3. Educator producing 20 Expertise consumes 2 Reagents + 2 Oil (lab step);
   producing 8 consumes 0 (below step).
4. Banker with an active loan consumes 1 Goods/season.
5. Full pytest; **1000-game seed-42 sim** (new share±σ metrics): Miner **+1–2pts**
   (intended, addresses ~8% underweight), all others within ±2pts; brownout <5%
   of island-seasons; Oil produced vs consumed both rise. Before/after share±σ
   table + Oil flow in the PR.

## Out of scope

Continuing-education Expertise upkeep (P2b), campus insurance product (park —
propose separately if §2 shortfalls prove too punishing without it).
