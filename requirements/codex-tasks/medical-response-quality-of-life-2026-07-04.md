# Brief — Medical Response & Quality of Life (2026-07-04)

**Status: APPROVED (Ash 2026-07-05) — implementation-ready.** Nurse bonus cap
(+20%) confirmed; Medical Supplies rename confirmed as specced.
**Suggested owner:** Codex (engine) + Claude (UI: QoL panel, care prompts).
**Base off:** `origin/pre-release` @ `9938d48`, APP_VERSION `0.1.5-dev.2026-06-22.18`.
**Follows:** `_README.md` working agreement. Pairs with
`business-cycle-severity-events-2026-07-04.md` (severity feeds care demand) and
the existing `vaccines-flu-season-49-2026-06-18.md` (vaccines stay as specced).

## Problem

`HealthServices` is a revenue sink with no mechanical effect (consumer.py:61
demand only). Injury/disease mitigation is wired to Banker insurance
(workforce_events.py:84–152), not to the Doctor's product or staff. `Nurse`
exists as a profession but does nothing. The medical island's economic story —
"reduce the impact of disease and injury, improve quality of life" — has no
mechanics behind it.

## Design overview

Three connected systems: **Medical Supplies** (the tradable good), **Care**
(staff + supplies treating sick/injured workers, locally or by medevac), and a
**Quality-of-Life index** (nutrition + medical coverage + consumer goods →
productivity and population growth).

### 1. Medical Supplies (replaces HealthServices as the tradable good)

Real-world analogy: hospitals don't sell "health services" into a warehouse —
they deliver care by consuming **medical consumables**: pharmaceuticals,
dressings/IV fluids, PPE, diagnostic kits. The tradable thing is the supplies;
the *service* is what staff do with them.

- **Recommended (v1): rename** `ResourceType.HEALTH_SERVICES` →
  `MEDICAL_SUPPLIES` (display "Medical Supplies"), keep BASE_PRICES and the
  Doctor's production recipe (Expertise + Oil + Ore per PRODUCTION_INPUTS).
  One resource, meaning changed from service-output to consumable stock.
  Migration: enum value + UI strings + consumer demand key.
- Alternatives considered (for review, not recommended for v1):
  - Split into two goods (Pharmaceuticals from Reagents; TraumaKits from
    Reagents+Goods) — richer, but doubles market surface and AI complexity.
  - Keep HealthServices non-tradable and auto-generated — loses the "islands
    stockpile against a pandemic" gameplay Ash wants.
- Consumer demand loop keys switch to MedicalSupplies unchanged in volume.
- Islands **stockpile** supplies; all care mechanics below consume them.

### 2. Care: staff × supplies → treatment

New per-season care resolution (runs after workforce risk rolls and event
application, before production):

- **Care capacity** per island: `DOCTOR_TREATMENTS_PER_SEASON = 3` per resident
  Doctor-profession worker, `NURSE_TREATMENTS_PER_SEASON = 2` per Nurse.
- **Each treatment consumes 1 MedicalSupplies** from the island's stock.
  No supplies → no treatment (capacity idle).
- **Sidelining model** (new): an injured worker (workplace roll or disaster
  casualty) or sick worker (pandemic/disease event) is *sidelined* — removed
  from effective workforce — for `UNTREATED_RECOVERY_SEASONS = 2`.
  Treated on the season of injury → `TREATED_RECOVERY_SEASONS = 1`.
- **Medevac** (uses the Transporter + Doctor): when local care capacity or
  supplies run out, the player may transfer patients to the Medical island:
  consumes `MEDEVAC_SEATS = 2` PassengerSeats per patient (round trip), a
  `MEDEVAC_FEE = 8` Dp treatment fee paid to the Doctor, and 1 MedicalSupplies
  from the **Doctor's** stock. Treated recovery (1 season). Player chooses
  which patients (skilled workers are the obvious picks — surface band/
  profession in the picker). Doctor gains a fee income stream and a reason to
  hold stock; Transporter sells seats outside the training pipeline.
- Insurance interplay: medical insurance keeps its *probability* reduction
  (halves injury rate); care reduces *duration/impact* after the fact. They
  stack by design — belt and braces, no double-dip on the same axis.

### 3. Nurses raise the standard of living

- **Nurse coverage bonus**: +10% productivity per Nurse per 15 workforce
  members, **capped at +20%** (i.e. 2 nurses per 30 workers saturate), and
  requires `NURSE_UPKEEP_SUPPLIES = 1` MedicalSupplies per nurse per season
  (unpaid → that nurse's bonus inactive that season).
  Delivered **through the QoL index** (below), not as a separate multiplier,
  so it can't stack with itself.

### 4. Quality-of-Life index (0–100, per island, recomputed each season)

| Component | Points | Source |
|-----------|--------|--------|
| Nutrition | 0–30 | full sustenance met = 20; meal *variety* (≥3 food types consumed) = +10 (hooks `consume_sustenance`) |
| Medical coverage | 0–35 | active medical insurance = 10; nurse coverage ratio (nurses×15/workforce, capped 1.0) × 15; supplies stocked ≥ 1 per 10 pop = 10 |
| Consumer goods | 0–20 | goods consumed this season ≥ consumer demand plan = 20, pro-rata below |
| Stability | 0–15 | baseline 15; −10 while pandemic/disaster active; −5 if any workers sidelined untreated |

- **Productivity multiplier**: linear map QoL 0 → 0.85, 50 → 1.00, 100 → 1.15.
  Applied in `production_capacity` alongside efficiency.
- **Population growth modifier**: existing growth × (0.5 + QoL/100).
- Business cycle (P1.4 brief) drifts the Stability component ±5.
- UI: QoL score + component breakdown on the island panel; alert when a
  component is starving the score.

### 5. Pandemic shape (interface to P1.4)

Pandemics run `PANDEMIC_DURATION_SEASONS = 2` (persistent event state), sideline
a severity-scaled share of workforce as *sick*; treated workers return after 1
season. Vaccines (existing #49 brief) reduce the sidelined share; care reduces
duration. Constants live in the P1.4 brief; this brief owns the care response.

## Files

constants.py (new constants above), models/resource.py (rename),
models/player.py (sidelined workers, QoL state), engine/workforce_events.py
(sidelining + care resolution), engine/turn.py (medevac action/prompt),
engine/production.py (QoL multiplier), engine/consumer.py (key rename),
engine/game.py (season order: risks → care → production), server UI (Claude).

## Acceptance criteria

1. Treatment consumes supplies and halves recovery; no supplies → full 2-season
   sideline. Unit tests for capacity math, supply starvation, medevac transfer.
2. Nurse bonus: 2 nurses / 30 workers with upkeep paid → +20% via QoL; unpaid
   upkeep drops it.
3. QoL: all-components island ≈ 100 → ×1.15; starved island ≈ 15–25 → ×0.87–0.90.
4. Full pytest green; **1000-game seed-42 sim**: Doctor share rises toward
   ~14.3% par (from ~9–12%); no other role moves >2pts; MedicalSupplies trades
   ≥ 3 units/game average.

## Out of scope

Vaccine mechanics (#49 brief), severity dice and pandemic yield hits (P1.4),
hospital capital items' care-capacity effects (follow-up once base lands).
