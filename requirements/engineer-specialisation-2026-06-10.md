# Requirement — Engineer: 3-season training + 4th-season speciality (issue #78)

**Status:** Fully specified, ready for Codex. Sequencing: after (or bundled
with) #75/#76 — same training tables, and Engineer is science-track per the
confirmed taxonomy (`reagents-gating-and-supply-chain-tests-2026-06-02.md` §A).

## Base change

- Engineer training duration: **2 → 3 seasons** (`models/profession.py`
  training-duration map; Engineer is Manager-band).
- Engineer remains **science-track**: each training season consumes Reagents
  (per #76). A 3–4 season engineer is intentionally a meaningful Reagents sink —
  this is a demand driver for the Doctor's Reagents line.
- All season-scaled costs apply per season as today: course slot, educator fee,
  PassengerSeats travel, per-head medical cover (`MEDICAL_PREMIUM_PER_HEAD`).

## Speciality (optional 4th season)

A trainee may extend to a **4th consecutive season** to graduate with one
speciality; alternatively, an already-qualified Engineer may **return later**
for any speciality as a **1-season** course (no repeat of the base 3; normal
per-season costs; still science-track). An engineer holds at most one
speciality; retraining to a different one replaces it (another 1-season
course). Display as e.g. `Engineer (Chemical)`.

### Effects

Passive, island-wide, active only while the engineer is **active** on the
island (not injured/absent/in training/contracted away — mirrors how
`workforce_active` already gates production). Per island, each speciality's
effect applies at most **twice** (a 2-stack cap prevents degenerate
engineer-farming). Numbers use the existing effects vocabulary and sit in the
same range as capital items (+2…+12 capacity, −1 labour relief, −0.2 input
relief):

| Speciality | Effect while active | Implementation hook |
|---|---|---|
| **Industrial** | +2 capacity on **every product line the island runs** (process/throughput organisation) | same mechanism as `CapitalItem.effects["capacity"]`, applied per produced output |
| **Mechanical** | Island capital **service life +25%** (e.g. 20 → 25 seasons), and `labour_relief {Technician: 1}` | service-life multiplier in `capital_book_value` / expiry checks; relief as per `farmer.harvester` |
| **Electrical** | Island **workforce efficiency +5 percentage points** (instrumentation/automation), cap +10 from stacking | additive bump where `average_efficiency` feeds production |
| **Chemical** | **−20% Oil input** on all recipes that consume Oil, and +2 Reagents capacity if the island produces Reagents | generalised `input_relief` (precedent: `miner.crusher` −0.2 Oil/Ore; `enhanced_crusher_smelter` ×0.5 multiplier) |

### Natural island fits (flavour, not enforced)

Any island may employ any speciality; the economics self-select: Industrial →
Manufacturer, Mechanical → equipment-heavy islands (Farmer/Miner/Transporter),
Electrical → any large workforce, Chemical → Miner (Oil/Metal) and Doctor
(Reagents).

## Acceptance criteria

1. Engineer base course is 3 seasons; speciality adds a 4th (or a later
   1-season return course).
2. A specialised engineer's effect is visible in the capacity payload
   (`_player_capacity`) and disappears while the engineer is inactive.
3. Stacking caps enforced (2 per speciality per island; Electrical capped at
   +10 points).
4. Reagents are consumed per training season for Engineer courses once #76
   lands.
5. Tests: duration change, one effect test per speciality, stacking cap,
   active/inactive gating.

## Out of scope

- Speciality-specific capital items or new resources.
- AI (`ai.py`) choosing to train specialised engineers (follow-up once #29 is
  picked up).
