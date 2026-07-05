# Brief — Economic Dependence: Energy Floor, Educator & Banker Inputs (2026-07-05)

**Status: APPROVED (Ash 2026-07-05) — implementation-ready.** P2a of the
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

Each island consumes **`1 + ceil(owned_capital_units / 4)` Oil per season** as
building electricity, auto-deducted at season upkeep (new sink, alongside
sustenance). `owned_capital_units` = Σ `capacity_units` of owned units (the
field added by `manufacturer-capacity-scaling-2026-07-04.md`; until that lands,
use owned-unit count).

- **On top of** existing `PRODUCTION_INPUTS` Oil (production fuel ≠ building
  power) — flat formula for all, per Ash 2026-07-05.
- **Brownout** when unmet (no Oil stock, none bought that season):
  production capacity **−25%** that season and QoL Stability **−5**
  (QoL from P1.1). Never a hard stop.
- The Miner's own Oil stock satisfies its floor.
- New: `ENERGY_FLOOR_BASE = 1`, `ENERGY_FLOOR_UNITS_PER_OIL = 4`,
  `BROWNOUT_CAPACITY_PENALTY = 0.25`.
- AI: extend the spares-style buy-buffer to keep ≥ next-season floor of Oil.

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

1. A 12-capacity-unit island consumes `1 + ceil(12/4) = 4` Oil/season; with no
   Oil it takes −25% capacity + QoL −5 that season (unit tests).
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
