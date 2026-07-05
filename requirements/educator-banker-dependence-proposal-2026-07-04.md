# Proposal — Educator & Banker Dependence (P2) — 2026-07-04

**Status: PROPOSAL for Ash review** (turns into a codex-tasks brief on approval).
Builds on Ash's direction: everyone buys food; Educator feeds students and runs
labs; Banker burns oil for electricity; every island needs base energy.

## What already exists (don't rebuild)

- **Food**: every island already consumes sustenance per population
  (`consume_sustenance`, meal counts, shortfall demand baskets, FOOD ALERTs).
  So "all have to buy food" is live — the gaps are the *extra* mouths
  (students) and the two roles' non-food inputs.
- **Educator lab inputs, partially**: Patents already gate on Reagents
  (`OUTPUT_PRODUCTION_INPUTS["Educator"]["Patents"] = {Reagents: 1}`).
- **Student transport**: training arrivals already consume air tickets /
  PassengerSeats.
- Both roles are already exposed to disease/disaster via their event charts
  (Teacher Strike, Pandemic Closure; Credit Crunch, Bank Crisis) — and P1.4
  severity + P1.1 sidelining deepen that automatically since both have
  workforces.

## Proposed additions

### 1. Universal energy floor (all seven islands)

Every island consumes **Oil = 1 + ceil(owned capital units / 4)** per season
("electricity"). Miner self-supplies (its own Oil stock counts).
- Unpaid (no Oil in stock, none bought) → **brownout**: production capacity
  −25% that season + QoL Stability −5. Never a hard stop — a drag, not a wall.
- Rationale: makes Oil the economy's base currency of dependence (Ash: "all
  islands will need some base level of oil aka energy") and gives the Miner
  seven steady customers instead of three.
- Note: Farmer/Miner/Transporter/Doctor already list Oil in
  `PRODUCTION_INPUTS`; the floor replaces *none* of that (production fuel ≠
  building electricity) but their floor is discounted to `ceil(units/4)`
  (no double base-1) so existing balance barely moves.

### 2. Educator

| Input | Proposal | Consumer |
|---|---|---|
| Student meals | +1 Food per enrolled student per season (on top of population sustenance) — boarding-school reality | Farmer |
| Lab consumables | Courses **and** Expertise runs consume Reagents 1 + Oil 1 per 10 output units (extends the existing Patents gate to all lab-based output) | Doctor (Reagents), Miner (Oil) |
| Campus insurance | New Banker product "campus cover": halves the yield hit of Teacher Strike / Pandemic Closure events; priced like medical insurance | Banker |
| Graduate send-off | Return leg of each graduating cohort consumes PassengerSeats (arrivals already do) | Transporter |

### 3. Banker

| Input | Proposal | Consumer |
|---|---|---|
| Electricity | Universal floor above (vaults and trading floors are power-hungry: Banker's divisor is /3 not /4) | Miner |
| Office operations | 1 Goods per season while ≥1 loan or policy is active ("stationery, systems, furniture") | Manufacturer |
| Food | Already covered by sustenance ✓ | Farmer |

### 4. Ideas beyond Ash's list (for consideration)

- **Expertise upkeep for professionals** (Banker + Doctor): 1 Expertise per
  season per 3 Manager-band workers — continuing education; makes the Educator
  a recurring seller, not a one-shot trainer. (Biggest structural win in this
  doc, slightly bigger change — flag separately.)
- **Audit season**: once per year the Banker pays the Educator 2 Expertise
  worth of "audit & compliance" — small, flavourful, closes the
  Banker→Educator edge which otherwise stays empty.
- **Goods as QoL fuel**: already in P1.1 (consumer goods component) — no
  further action here, just noting the Manufacturer edge to every island
  comes free with P1.1.

## Dependence matrix after this proposal (seller → buyer edges)

Every role then both sells to and buys from ≥3 others; the previously empty
Educator/Banker input rows disappear. (Full 7×7 matrix to be included in the
brief once numbers are approved.)

## Sim gates (when implemented)

Quantities above are deliberately small: target **no role share moves >2pts**
except Miner (+1–2pts intended, partially addressing its ~8% underweight) and
Educator (±2pts). 1000-game seed-42 before/after in the PR; brownout frequency
< 5% of island-seasons in sim (AI must learn to stock Oil — buy-buffer like
the spares one).

## Open questions for Ash

1. Energy floor: flat `1 + ceil(units/4)` ok, or scale by island size/pop?
2. Student meals: 1 Food/student/season right order of magnitude? (University
   capacity means ~2–6 students/season typically.)
3. Expertise-upkeep idea: in scope for this brief or parked?
