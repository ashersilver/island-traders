# Education Model Refinement

Status: **draft requirements** (2026-05-15)
Source: playtest inbox items captured 2026-05-15
Touches: resources, professions, production recipes, training flow, RULES.md, UI

---

## Problem statement

Today the Education Island produces a single resource called **Knowledge**.
Training requests consume nothing tangible from the Education Island — they
just succeed as long as `UNIVERSITY_CAPACITY` has room.  This conflates two
distinct things:

1. **Expertise** — the intellectual capital the Education Island accumulates
   and sells as an input to Research, Healthcare, etc.
2. **Courses** — the discrete training slots that an island uses up when it
   sends workers to college.

Conflating them means an Education Island can't run out of teaching capacity
even when it should, and there's no in-game lever for "the university has
plenty of expertise on file but can't admit more students this season."

## Proposed model

### Resource rename + new resource

| Today | Tomorrow |
|---|---|
| `Knowledge` | `Expertise` *(renamed; same role, same price, same uses)* |
| — | `Courses` *(new resource, produced by Education)* |

Display label: "Expertise" replaces "Knowledge" everywhere player-facing.
Internally the `ResourceType` enum entry gets renamed
(`ResourceType.KNOWLEDGE` → `ResourceType.EXPERTISE`).

### Production recipes

The Education Island produces **both** outputs each season:

```
inputs : 1 LaboratoryEquipment   (unchanged)
outputs:
  Expertise           — driven by Manager (Professor / Lecturer) capacity
  Courses             — driven by Manager (Professor) + Technician
                        (Tutor / Instructor) capacity
  Patents             — already produced (1/season at full Manager load)
```

**Courses production consumes Expertise as an input.**  Each Course
"manufactured" costs ~1 Expertise.  This creates a natural cap: a single
Education Island can't print infinite Courses; it has to maintain its
Expertise stockpile.

Suggested starting recipe sketch:

```python
ProductionRecipe(
    role="Educator", output="Expertise",
    inputs={"LaboratoryEquipment": 0.25},
    manager_per_unit=1.0, technician_per_unit=0.5, worker_per_unit=0.5,
    description="1 Professor required per unit of Expertise",
),
ProductionRecipe(
    role="Educator", output="Courses",
    inputs={"LaboratoryEquipment": 0.1, "Expertise": 1.0},
    manager_per_unit=0.5, technician_per_unit=1.0, worker_per_unit=0.0,
    description="1 Instructor + 0.5 Professor per Course",
),
ProductionRecipe(
    role="Educator", output="Patents",
    inputs={"LaboratoryEquipment": 0.5, "Expertise": 0.25},
    manager_per_unit=2.0, technician_per_unit=1.0, worker_per_unit=0.0,
    description="Patents require a small Expertise input plus 2 Professors per unit",
),
```

> **Patents consume Expertise too** (confirmed 2026-05-15) — a small input
> (~0.25 Expertise per Patent).  Patents are still gated by Manager
> capacity (2 Professors per Patent); the Expertise input is the
> intellectual-capital cost on top.

### Training requests

Training (Request Training action) now requires the Education Island to
have **Courses in inventory**:

- **Managerial training** (Professor-tier outputs — Doctor, Engineer,
  Banker, Farmer, Miner, Professor, Lecturer, Logistics Manager):
  1 Course covers a *class* of up to **12 students**.  *Capacity-gated by
  Professors.*
- **Technician / apprenticeship training** (Farming Technician,
  Veterinarian, Mining Technician, Oil Extraction Worker, Refinery
  Specialist, Mechanic, Assembly Worker, Flight Crew, Seaman, Warehouse
  Manager, Banking Analyst, Banking Clerk, Medical Orderly):
  1 Course covers a *class* of up to **12 students**.  *Capacity-gated by
  Instructors.*

**Class-size rule (confirmed 2026-05-15):**
A single Course is a classroom slot, not a per-student token.  Up to
**12 trainees** can share one Course.  When an Educator approves a
training batch:

* If the batch has ≤ 12 trainees, **1 Course** is debited from inventory.
* If the batch has > 12 trainees, the system either splits the batch
  across multiple Courses (debiting `ceil(trainees / 12)`) or asks the
  Educator to re-submit smaller batches.  Recommendation: auto-split, with
  a confirmation prompt to the requester if the cost goes up.

No Courses → cannot approve the request (it stays pending until next
season's production refills).

> The 12-student class-size cap also applies to **self-training** (see
> below).  Multiple Professors / Banking Clerks / etc. on the Education
> Island can train as a single class on one Course.

### New profession: Instructor

The "Tutor" technician profession introduced with the workforce baseline
**consolidates into Instructor** (taking the consolidation path from this
spec's earlier open question).

| Profession | Band | Notes |
|---|---|---|
| Professor | Manager | Senior faculty; tied to managerial training capacity |
| Lecturer | Manager | Junior faculty; supports Expertise / Courses production |
| Instructor | Technician | Apprenticeship training delivery |

> **Migration note:** existing `Profession.TUTOR` enum entry, `BAND_TITLES`
> entry, `UNIVERSITY_CAPACITY` slot, and any starting-workforce reference
> are renamed to `Profession.INSTRUCTOR`.  "Tutor" can stay as an alternate
> display title (`BAND_TITLES["Educator"][WorkerBand.TECHNICIAN]` can
> include both names) but the canonical profession is Instructor.

### Starting workforce (Education Island)

Today: 1 Professor + 2 Tutors + 1 Unskilled = 4 workers.

**Proposed:** 4 Professors + 4 Instructors = 8 workers (no unskilled),
matching the inbox note that Education starts at a higher headcount because
its outputs gate every other island's growth.

> This bumps Education Island's `STARTING_WORKFORCE` from 4 → 8 and reshapes
> `STARTING_WORKERS_BY_PROFESSION`.

### Starting inventory

| Item | Why |
|---|---|
| 6 Expertise | First-season Course production isn't blocked while the new Expertise pipeline ramps |
| 5 Courses | Other islands can already train in Spring Y1 |
| 2 Lab Equipment | Standard 2-season runway (carried over from current) |

### Pricing

| Resource | Suggested base price |
|---|---|
| Expertise | 18 Dp *(unchanged from Knowledge today)* |
| Courses | 25 Dp *(scarcer and gated by Expertise consumption)* |

---

## Migration plan

Two-phase to keep the change tractable:

### Phase 1 — Rename (mechanical)

1. `ResourceType.KNOWLEDGE` → `ResourceType.EXPERTISE`.  Display label
   "Expertise" everywhere.
2. `BASE_PRICES["Knowledge"]` → `BASE_PRICES["Expertise"]`.
3. `BASE_PRODUCTION`, `PRODUCTION_INPUTS`, `STARTING_INVENTORY`,
   `MANUFACTURER_PRODUCT_LINES`, `ROLE_INFO` (server), and every test that
   names "Knowledge" gets renamed.
4. RULES.md, README.md updated.

Zero behavioural change — pure rename.  Aim: tests green at this point.

### Phase 2 — Courses + new training flow

1. Add `ResourceType.COURSES` and `BASE_PRICES["Courses"] = 25`.
2. Add the new Education recipes (Expertise + Courses + Patents).
3. Add `Profession.INSTRUCTOR` (or consolidate Tutor → Instructor per the
   open question above).
4. `UNIVERSITY_CAPACITY` re-segments by tier:
   - Manager-tier professions (Doctor, Engineer, Farmer, etc.) → require
     Professors *and* a Course.
   - Technician-tier professions (Mining Tech, Flight Crew, etc.) →
     require Instructors *and* a Course.
5. `_action_request_training` and `_action_review_training` debit a
   Course from the Educator's inventory on approval.  If no Courses, the
   request stays pending.
6. `STARTING_WORKFORCE[Educator] = 8`, `STARTING_WORKERS_BY_PROFESSION`
   updated to 4 Professors + 4 Instructors.
7. `STARTING_INVENTORY[Educator]` includes 6 Expertise + 5 Courses + 2
   Lab Equipment.
8. RULES.md updated with the new dynamic.
9. Tests cover: Course consumption on approval; manager vs technician
   capacity gating; Education Island can't approve more training than
   Courses available; AI Educator behaviour when Courses are short.

---

## Training cost components (Issue #18)

Different professions need different training depths.  The total fee a
requester pays the Educator should reflect the cost components, not be a
single flat number:

| Component | Notes |
|---|---|
| **Transportation** | Already covered (1 PassengerSeats per trainee, supplied by Educator).  Skipped for self-training. |
| **Food & accommodation** | Per-trainee, per-season-at-college.  Suggest 5 Dp per worker per season. |
| **Course duration (1–4 seasons)** | Profession-dependent.  Doctor = 4 seasons; Engineer / Banker / Professor / Lecturer / Logistics Manager / Farmer / Miner = 2 seasons; Nurse = 1 season; Technicians = 1 season *(with apprenticeship facility — see below)*. |
| **Expertise consumption** | **1 unit of Expertise per trainee per season** (i.e. a 4-season Doctor consumes 4 Expertise; a 2-season Engineer consumes 2 Expertise).  Replaces the flat "Expertise input" notion from the recipe sketch above. |
| **Course slot** | 1 Course per *class* (up to 12 students) — see Class-size rule. |
| **Educator base fee** | Suggest 20 Dp per trainee.  The Banker's actuarial / professional certification of the qualification, if applicable, layers on top. |

Suggested **fee suggestion** the prompt offers the requester:

```
suggested_total = (base_fee × trainees)
                + (food_per_season × trainees × course_duration)
                + (ticket_price × trainees)
                + (expertise_unit_price × trainees × course_duration)
```

### Apprenticeship facility (Technician training)

Technicians normally need **2 seasons** of training (1 season at the
Education Island + 1 season returning to their home island as a "partial
technician" at **50% productivity**).

If the home island has an **Apprenticeship Facility** capital item, the
return-island season is skipped: the technician comes back fully
qualified after 1 season.  This makes the apprenticeship facility a
meaningful capital purchase for islands that need to scale Technicians
quickly.

> **Open implementation question:** which capital items count as
> apprenticeship facilities?  Recommendation: add a new field
> `provides_apprenticeship_facility: bool` on `CapitalItem`; set true
> for relevant items like Manufacturer's Assembly Line, Mining's
> Foreman Office, Transporter's Crew Training Hall, etc.

### Duration table (under the new model)

| Profession | Band | Seasons |
|---|---|---|
| Doctor | Manager | 4 |
| Engineer | Manager | 2 |
| Banker | Manager | 2 |
| Professor | Manager | 2 |
| Lecturer | Manager | 2 |
| Logistics Manager | Manager | 2 |
| Farmer | Manager | 2 |
| Miner | Manager | 2 |
| Nurse | Manager | 1 |
| **Ecologist** | Technician | 2 *(new — see medical-laboratory.md)* |
| **Actuary** | Technician | 2 *(new — see medical-laboratory.md)* |
| All other Technicians | Technician | 1 with apprenticeship facility, 2 without |

---

## Open questions

1. **Tutor vs Instructor** — ✅ **Decided 2026-05-15:** consolidate into
   Instructor (single canonical Technician profession on Education
   Island).  Tutor stays as a display title alias only.
2. **Should Educators be able to *buy* Courses on the market** (e.g. from
   another Educator if there were two) or are Courses strictly a
   per-island production-then-consume resource that never trades?  Today's
   game has at most one Educator so the question is academic.  Default
   assumption (still open): **not market-tradable** — Courses are
   issued-and-consumed by the same Education Island.  Reconfirm if/when
   multi-Educator games are supported.
3. **Patent recipe** — ✅ **Decided 2026-05-15:** Patents also consume a
   small Expertise input (~0.25 Expertise per Patent) on top of the
   Laboratory Equipment + Professor capacity already required.
4. **Self-training Course consumption** — ✅ **Decided 2026-05-15:**
   self-training **still consumes 1 Course** even though it skips the
   educator fee and transport ticket.  Class-size cap of 12 applies, so
   multiple workers on the Education Island can train on the same Course.

---

## Impact summary

This is a substantial refactor.  Estimated touch surface:

- 1 enum rename (cascade across ~40 files via Knowledge → Expertise)
- 1 new enum entry (Courses)
- 1 Profession enum **rename** (Tutor → Instructor; the underlying slot
  in `STARTING_WORKERS_BY_PROFESSION` and `UNIVERSITY_CAPACITY` is
  preserved, just renamed)
- 4 dict updates in `constants.py`
- 2 new entries in `constants_capacity.py` (Courses recipe + Expertise
  added to Patents recipe inputs)
- 1 new constant: `MAX_CLASS_SIZE_PER_COURSE = 12`
- 1 new flow step in `_action_request_training` and `_action_review_training`
  (Course debit logic with class-size split)
- ~10 affected tests
- RULES.md, README.md, server `ROLE_INFO`, dashboard `Education` panel

Recommend doing Phase 1 (mechanical rename) as its own branch first, then
Phase 2 (Courses + training flow) as a second branch.  Don't combine.
