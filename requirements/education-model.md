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
    description="1 Tutor / Instructor + 0.5 Professor per Course",
),
```

### Training requests

Training (Request Training action) now requires the Education Island to
have **Courses in inventory**:

- **Managerial training** (Professor-tier outputs — Doctor, Engineer,
  Banker, Farmer, Miner, Professor, Lecturer, Logistics Manager):
  1 Course per trainee.  *Capacity-gated by Professors.*
- **Technician / apprenticeship training** (Farming Technician,
  Veterinarian, Mining Technician, Oil Extraction Worker, Refinery
  Specialist, Mechanic, Assembly Worker, Flight Crew, Seaman, Warehouse
  Manager, Tutor, Banking Analyst, Banking Clerk, Medical Orderly):
  1 Course per trainee.  *Capacity-gated by Tutors / Instructors.*

When an Educator approves a training request, the Education Island debits
the relevant number of Courses from inventory.  No Courses → cannot approve
the request (it stays pending until next season's production refills).

### New profession: Instructor

The "Tutor" technician profession introduced with the workforce baseline
gets a sibling: **Instructor** (also Technician band, Education Island).

| Profession | Band | Notes |
|---|---|---|
| Professor | Manager | Senior faculty; tied to managerial training capacity |
| Lecturer | Manager | Junior faculty; supports Expertise / Courses production |
| Instructor *(new)* | Technician | Apprenticeship training delivery |
| Tutor | Technician | Apprenticeship training delivery (alternative title; consider folding into Instructor for simplicity) |

> **Open question:** is "Tutor" still a distinct profession, or should we
> consolidate the two technician roles into just "Instructor" so there's a
> clean Professor (M) / Instructor (T) pairing?  Recommendation: consolidate
> — keep Tutor as a display title only.  Decision needed before
> implementation.

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

## Open questions

1. **Tutor vs Instructor** — see above; recommendation: consolidate.
2. **Should Educators be able to *buy* Courses on the market** (e.g. from
   another Educator if there were two) or are Courses strictly a
   per-island production-then-consume resource that never trades?  Today's
   game has at most one Educator so the question is academic, but the
   answer shapes the resource enum's tradeable-flag.
3. **Patent recipe**: does Patents production still need its own inputs,
   or should it also consume Expertise (the way Courses do)?
4. **Should "self-training" on the Educator Island consume Courses?**
   See the related inbox item: Educator training its own workforce should
   skip the fee and transport.  But should it still consume Courses?
   Recommendation: yes — self-training still uses a Course (otherwise the
   Educator has unfair internal capacity).

---

## Impact summary

This is a substantial refactor.  Estimated touch surface:

- 1 enum rename (cascade across ~40 files via Knowledge → Expertise)
- 1 new enum entry (Courses)
- 1 new Profession enum entry (Instructor, possibly +1 Tutor removal)
- 4 dict updates in `constants.py`
- 2 new entries in `constants_capacity.py`
- 1 new flow step in `_action_request_training` and `_action_review_training`
- ~10 affected tests
- RULES.md, README.md, server `ROLE_INFO`, dashboard `Education` panel

Recommend doing Phase 1 (mechanical rename) as its own branch first, then
Phase 2 (Courses + training flow) as a second branch.  Don't combine.
