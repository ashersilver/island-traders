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

### Training requests — two distinct pipelines

> **Decided 2026-05-17:** Courses (university) and vocational
> apprenticeship are **distinct, non-overlapping** pipelines.  A
> Technician request does **not** consume a Course; a Manager request
> does **not** consume an apprenticeship slot.

**Manager-tier training (university — Course-gated):**
Professor-tier outputs — Doctor, Engineer, Banker, Farmer, Miner,
Professor, Lecturer, Logistics Manager.

- Gated by **Courses in inventory** *and* Professor capacity.
- 1 Course covers a *class* of up to **12 students** (class-size rule
  below).
- Trainees travel to the Education Island for the profession's full
  course duration (see Duration table — Doctor 3 seasons, most Managers
  2, Nurse 1).

**Technician-tier training (vocational apprenticeship — slot-pool gated):**
Farming Technician, Horticulturalist, Veterinarian, Mining Technician,
Oil Extraction Worker, Refinery Specialist, Mechanic, Assembly Worker,
Flight Crew, Seaman, Warehouse Manager, Banking Analyst, Banking Clerk,
Medical Orderly, Instructor (+ future Ecologist / Actuary).

- Gated by the Educator's **apprenticeship slot pool** (the
  `educator.apprenticeship_programme` capital, `apprenticeship_slots`)
  **and Instructor (trainer) capacity** — **not** by Courses.
- The apprentice spends **1 season at the Education Island**, then
  returns home and works at **75% productivity for exactly one season**
  before reaching 100%.
- No "in-house apprenticeship sellable token" — that idea is dropped.

**Class-size rule (Manager-tier Courses, confirmed 2026-05-15):**
A single Course is a classroom slot, not a per-student token.  Up to
**12 trainees** can share one Course.  When an Educator approves a
Manager-tier batch:

* If the batch has ≤ 12 trainees, **1 Course** is debited from inventory.
* If the batch has > 12 trainees, the system splits the batch across
  multiple Courses (debiting `ceil(trainees / 12)`).  Recommendation:
  auto-split, with a confirmation prompt to the requester if the cost
  goes up.

No Courses → a Manager-tier request stays pending until next season's
Course production refills.  No free apprenticeship slot → a
Technician-tier request stays pending until a slot frees up.

> The 12-student class-size cap applies to Manager-tier **self-training**
> too.  Multiple Professors / Lecturers on the Education Island can train
> as a single class on one Course.  Technician self-training instead
> consumes an apprenticeship slot.

> **Phase 2 reconciliation note:** Phase 2 (merged) currently debits a
> Course for *all* tiers including Technicians.  **Phase 3 scopes the
> Course-debit to Manager-tier only**; Technician training switches to
> the apprenticeship-slot-pool gate described above.

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

Three phases.  **Phase 1 and Phase 2 are done and merged**
(`pre-release` ≥ `3948582`); Phase 3 is the next work.

### Phase 1 — Rename (mechanical) — ✅ DONE (`claude/education-phase1-rename`)

1. `ResourceType.KNOWLEDGE` → `ResourceType.EXPERTISE`.  Display label
   "Expertise" everywhere.
2. `BASE_PRICES["Knowledge"]` → `BASE_PRICES["Expertise"]`.
3. `BASE_PRODUCTION`, `PRODUCTION_INPUTS`, `STARTING_INVENTORY`,
   `MANUFACTURER_PRODUCT_LINES`, `ROLE_INFO` (server), and every test that
   names "Knowledge" gets renamed.
4. RULES.md, README.md updated.

Zero behavioural change — pure rename.  Tests green (262).

### Phase 2 — Courses + new training flow — ✅ DONE (`claude/education-phase2`)

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

> Phase 2 as shipped Course-gates **all** tiers.  Phase 3 corrects this
> so Courses gate Manager-tier only and Technicians use the
> apprenticeship slot pool (decision (a), 2026-05-17).

### Phase 3 — Training cost components + apprenticeship pipeline (Issue #18) — ⏳ NEXT

See the **Training cost components** section below for the full spec.
Summary of what Phase 3 implements:

1. Scope the Phase-2 Course-debit to **Manager-tier only**.
2. Technician training → **apprenticeship slot pool**
   (`educator.apprenticeship_programme`) + Instructor (trainer) gate;
   1 season at Education, then **75% productivity for one season** on
   return, then 100%.
3. Profession-dependent **course duration** (Doctor **3**, other
   Managers 2, Nurse 1; Technicians 1 season away).
4. **1 Expertise per Course per season** (not per trainee).
5. Per-trainee **food & accommodation** cost in the fee suggestion +
   **campus load** (visiting trainees raise the Education Island's
   marginal sustenance demand via the new balance-aware model — §21 of
   `production-capacity-model.md`; do **not** reuse the legacy Food/Fish
   path).
6. `EDUCATION_SEASONS[DOCTOR]` 2 → **3** in code.

---

## Training cost components (Issue #18 — Phase 3)

Different professions need different training depths.  The total fee a
requester pays the Educator should reflect the cost components, not be a
single flat number:

| Component | Notes |
|---|---|
| **Transportation** | Already covered (1 PassengerSeats per trainee, supplied by Educator).  Skipped for self-training. |
| **Food & accommodation** | Per-trainee, per-season-at-college.  Suggest 5 Dp per worker per season. |
| **Course duration (1–4 seasons)** | Profession-dependent.  Doctor = 4 seasons; Engineer / Banker / Professor / Lecturer / Logistics Manager / Farmer / Miner = 2 seasons; Nurse = 1 season; Technicians = 1 season *(with apprenticeship facility — see below)*. |
| **Expertise consumption** | **1 unit of Expertise per Course per season**, not per trainee.  A Course is the teaching unit; up to 12 attendees share that same Expertise cost. |
| **Course slot** | 1 Course per *class* (up to 12 students) — see Class-size rule. |
| **Educator base fee** | Suggest 20 Dp per trainee.  The Banker's actuarial / professional certification of the qualification, if applicable, layers on top. |

Suggested **fee suggestion** the prompt offers the requester:

```
suggested_total = (base_fee × trainees)
                + (food_per_season × trainees × course_duration)
                + (ticket_price × trainees)
                + (expertise_unit_price × courses_needed × course_duration)
```

This keeps the classroom economy coherent: adding students to an existing
Course raises food and transport costs, but does **not** multiply the
Expertise burned by the class.

### Campus load

While trainees are away at the Education Island, they become part of its
seasonal operating burden:

- they require **Food** in addition to the island's resident population;
- they require accommodation / upkeep, represented in the training fee;
- they should be surfaced in the Education UX as **campus load**, e.g.
  “8 visiting trainees next season → +8 Food demand”.

This makes Education a real place rather than a magical certification portal:
approving more students creates revenue, but also raises the island's own
short-term sustenance needs until those trainees return home.

### Apprenticeship pipeline (Technician training) — canonical model

> **Decided 2026-05-17.**  This supersedes both the earlier
> "home-island Apprenticeship Facility" idea here *and*
> `production-capacity-model.md §8`'s "apprentice never leaves home"
> model.  `production-capacity-model.md §8` is updated to point here.

- Technician apprenticeship is gated by the Educator's **apprenticeship
  slot pool** (`educator.apprenticeship_programme` capital,
  `apprenticeship_slots`) **and Instructor (trainer) capacity** — *not*
  by Courses.
- The apprentice spends **1 season at the Education Island** (away from
  their home island).
- On return they work at **75% productivity for exactly one season**,
  then **100%** from the following season.
- There is **no** in-house cross-island apprenticeship sellable token,
  and **no** `provides_apprenticeship_facility` capital flag — the
  single gating mechanism is the Educator slot pool + Instructors.

> **Code implication:** `APPRENTICESHIP_SEASONS` currently encodes 2 for
> every Technician (a flat "away" duration).  Phase 3 changes the *away*
> duration to **1** season and adds the separate post-return
> "75%-for-one-season" productivity ramp on the home island.

### Duration table (canonical — under the Phase 3 model)

"Seasons away at Education" — for Technicians the home-island
75%-productivity settling season is *additional* and is not counted as
"away" time.

| Profession | Band | Seasons away | Notes |
|---|---|---|---|
| Doctor | Manager | **3** | (was ambiguous 2-vs-4; ruled 3 on 2026-05-17) |
| Engineer | Manager | 2 | |
| Banker | Manager | 2 | |
| Professor | Manager | 2 | |
| Lecturer | Manager | 2 | |
| Logistics Manager | Manager | 2 | |
| Farmer | Manager | 2 | |
| Miner | Manager | 2 | |
| Nurse | Manager | 1 | |
| **Ecologist** | Technician | 1 | + 1 settling season @ 75% *(new — see medical-laboratory.md)* |
| **Actuary** | Technician | 1 | + 1 settling season @ 75% *(new — see medical-laboratory.md)* |
| All other Technicians | Technician | 1 | + 1 settling season @ 75% on the home island |

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
   Manager-tier self-training **still consumes 1 Course** even though it
   skips the educator fee and transport ticket.  Class-size cap of 12
   applies.  Technician self-training consumes an apprenticeship slot
   instead (decision (a)).
5. **Courses vs apprenticeship pipelines** — ✅ **Decided 2026-05-17:**
   distinct and non-overlapping (decision (a)).  Manager-tier =
   Course-gated; Technician-tier = apprenticeship-slot-pool +
   Instructor gated, **not** Course-gated.
6. **Doctor training duration** — ✅ **Decided 2026-05-17:** **3 seasons**
   (not 2, not 4).  `EDUCATION_SEASONS[DOCTOR]` 2→3 in Phase 3.
7. **Apprenticeship mechanic** — ✅ **Decided 2026-05-17:** 1 season
   away at Education + 1 settling season @ 75% on the home island;
   gated by the Educator slot pool + Instructors; no home-island
   facility flag; no sellable token.

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

### Training-request UX extension

When a player opens **Request Training**, the game should show the island's
current formal-profession deficits against its staffing plan before asking
what to train. If several required professions are missing at once, the player
should be able to submit one bundled request for all currently requestable
deficits rather than repeating the same flow profession-by-profession. The
bundle still resolves into per-profession training batches under the hood so
University capacity, educator approval, and transport rules remain explicit.
