# Codex Task — Training Staffing Redesign (2026-05-25)

**Owner:** Codex
**Replaces:** the current Course-inventory + apprenticeship-slot-pool gates on training admission.
**Origin:** playtest 2026-05-24, the user observed cross-island Farmer training stuck at `awaiting_educator`. Log diagnosis showed both "apprenticeship slot pool full" (#4) and "needs N PassengerSeats" (#5) failure messages. The slot-pool concept was an implicit physical-plant gate; the user redesigned it as **explicit per-concurrent-course staffing**.

## Goal

Replace the current training-admission gates (`Courses` inventory check for Manager-tier + `Instructor count + apprenticeship_slot_capacity` for Technician-tier) with **per-concurrent-course staffing requirements**, locked for the **full course duration**. New roles, new accounting, but the existing `Courses` resource economics and the apprenticeship-pool capital items survive (with a rename).

## Branching

- **Base:** `pre-release` at `0aae64f` ("Merge codex/balance-calibration-2026-05") or later. Run `git fetch origin && git checkout -b codex/training-staffing-2026-05 origin/pre-release` to start.
- **Branch name:** `codex/training-staffing-2026-05`
- **Target for merge:** `pre-release` — **do not merge yourself.** Push the branch and stop. Claude will review and signal merge timing.

## What has shipped since you last touched training (mini-changelog)

- **AI Trading v2** (`4e56ead`) — Banker proactive loans + MBA reserve gate, AI take/rollover loans, AI INVEST mid-game.
- **Balance Calibration** (`0aae64f`) — three engine bugs fixed (external depositor loan repayment crash; buy_from_offers seller credit; Manufacturer Freight + bid-aware line choice). Balance levers tuned to ±5pp of 14.3% per role. AI list-only-with-bid filter added.
- **Sustenance basket model** (pending merge, `claude/sustenance-basket-model`) — 5-resource sustenance basket replacing legacy Food/Fish demand. Does NOT affect training, but be aware Player.population_food_fish_needs is gone.
- **Bug #2 fix** — `GameManager._ws_lock` + identity-aware `unregister_ws`. Server-only.
- **Auction stuck-at-zero fix** (parked locally on `claude/bug-auction-stuck-at-zero`) — not yet merged.

**Baseline test count: 369 passing** on `0aae64f`.

## Spec — the new model

### New Profession

Add `Profession.TECHNICAL_DIRECTOR = "TechnicalDirector"` to `island_traders/models/profession.py`. Senior tier-1 role for the Educator's technical (vocational / apprenticeship) faculty, parallel to Professor in the academic faculty.

- **Band:** `WorkerBand.MANAGER`.
- **PROFESSION_LABEL:** `"Technical Director"`.
- **EDUCATION_SEASONS:** 2 (same as other Managers).
- **STARTING_WORKERS_BY_PROFESSION["Educator"]:** add a baseline Technical Director (suggested 1 — bare minimum to run any technical course; Educator can train more via the existing Course pipeline once running).

### Staffing rules — per concurrent course, locked for course duration

**Manager-tier course** (target profession is Manager-band: Nurse / Doctor / Professor / Banker / Lecturer / Technical Director / Manufacturer Manager / etc.):

| Resource | Per concurrent course | Persistence |
|---|---|---|
| Professor | 0.5 | locked for the course's full duration |
| Lecturer  | 1.0 | locked for the course's full duration |
| Expertise | 2   | debited at dispatch |
| Course    | 1   | debited at dispatch (existing behaviour) |

**Technical-tier course** (target profession is Technician-band: Farming Technician / Mining Technician / Flight Crew / Mechanic / Instructor / etc.):

| Resource | Per concurrent course | Persistence |
|---|---|---|
| Technical Director | 0.5 | locked for the course's full duration |
| Instructor         | 1.0 | locked for the course's full duration |
| Expertise          | 1   | debited at dispatch |
| Course             | 1   | debited at dispatch (existing behaviour) |

**Interpretation of "0.5":** the senior role (Professor / Technical Director) supervises **two concurrent courses** at once. So 1 Professor → can supervise up to 2 simultaneous Manager-tier courses; 1 Lecturer → can lead 1 Manager-tier course (no sharing); ditto Technical Director / Instructor for technical courses.

**Capacity formulas:**

```
manager_capacity   = min(Professors * 2,        Lecturers)
technical_capacity = min(TechnicalDirectors * 2, Instructors)
```

Cap each at the **available** count after subtracting in-flight commitments — see "State tracking" below.

### Course = a batch
For accounting purposes, **1 course = 1 batch** (one `TrainingRequest`). Batch sizes still allow multiple trainees per course (subject to the existing `courses_needed = ceil(trainees/12)` rule — *don't change that*; one batch may consume more than 1 `Course` resource if it's >12 trainees, but it's still one **course** for staffing-capacity accounting).

### Technical Workshop prerequisite (renamed apprenticeship_programme)

Rename the capital item `educator.apprenticeship_programme` → `educator.technical_workshop`:

- `item_id`: `"educator.technical_workshop"` (was `"educator.apprenticeship_programme"`)
- `name`: `"Technical Workshop"` (was `"Apprenticeship Programme"`)
- `effects`: `{"technical_workshop_slots": 3}` (was `{"apprenticeship_slots": 3}`)
- `description`: `"+3 Technical Workshop slots (prerequisite for technical-tier courses)"`
- Keep `cost: 60.0`, `delivery_seasons: 0`.

The workshop is a **physical-plant prerequisite** for Technical courses: an Educator without any technical workshop slots **cannot run technical courses at all**, regardless of staffing. With workshops, the technical course capacity becomes:

```
technical_capacity = min(
    TechnicalDirectors * 2,
    Instructors,
    technical_workshop_slot_capacity,
)
```

Manager courses have **no equivalent workshop prerequisite** — staffing alone gates them.

The existing `apprenticeship_slot_capacity` helper in `island_traders/models/capacity.py` is renamed to `technical_workshop_slot_capacity` (sums `effects['technical_workshop_slots']` from owned items).

### State tracking — courses-in-flight commitments

Add to `TrainingRegistry` (`island_traders/models/training.py`):

```python
def manager_courses_in_flight(self, educator_id: int) -> int:
    """Count concurrent Manager-tier courses currently held by this
    Educator (status ∈ {DISPATCHED}; AWAITING_TRANSPORT also counts as
    a committed staff slot since the staff are reserved as soon as the
    Educator approves)."""

def technical_courses_in_flight(self, educator_id: int) -> int:
    """As above, for Technician-tier courses."""
```

Both count `TrainingRequest`s where `req.educator_id == educator_id` AND `req.status in (AWAITING_TRANSPORT, DISPATCHED)` AND the target profession's band matches.

Staff are committed from the moment of approval (status flips to `AWAITING_TRANSPORT`) and freed when `process_returns` flips the batch to `COMPLETED`. A rejection or counter-rejection frees the staff (status becomes `REJECTED`).

### Rewrite `TurnManager._training_capacity_status`

In `island_traders/engine/turn.py`, replace the current implementation. New shape:

```python
def _training_capacity_status(self, educator: Player, req) -> tuple[bool, str]:
    band = band_of(req.target_profession)
    n_courses = 1  # one batch = one course (staffing-accounting unit)
    
    if band == WorkerBand.MANAGER:
        prof = educator.workforce.count_profession(Profession.PROFESSOR.value)
        lect = educator.workforce.count_profession(Profession.LECTURER.value)
        max_concurrent = min(prof * 2, lect)
        in_flight = self.training.manager_courses_in_flight(educator.player_id)
        if max_concurrent - in_flight < n_courses:
            return False, (
                f"Manager-course staffing full: {in_flight}/{max_concurrent} "
                f"concurrent courses (need 0.5 Professor + 1 Lecturer per course; "
                f"have {prof} Professor(s), {lect} Lecturer(s))."
            )
        # Expertise gate (debited at dispatch; check here for clarity)
        if educator.inventory.get(ResourceType.EXPERTISE) < 2 * n_courses:
            return False, f"needs {2 * n_courses} Expertise for this course."
        # Course-slot gate (existing logic — courses_needed = ceil(trainees / 12))
        need_courses = self.courses_needed(len(req.worker_ids))
        if educator.inventory.get(ResourceType.COURSES) < need_courses:
            return False, f"needs {need_courses} Course slot(s) ({educator.inventory.get(ResourceType.COURSES)} on hand)."
        return True, ""
    
    if band == WorkerBand.TECHNICIAN:
        td = educator.workforce.count_profession(Profession.TECHNICAL_DIRECTOR.value)
        inst = educator.workforce.count_profession(Profession.INSTRUCTOR.value)
        workshop = technical_workshop_slot_capacity(
            CAPITAL_CATALOGUE, educator.capital_inventory
        )
        if workshop <= 0:
            return False, "no Technical Workshop on the Education Island (prerequisite for technical courses)."
        max_concurrent = min(td * 2, inst, workshop)
        in_flight = self.training.technical_courses_in_flight(educator.player_id)
        if max_concurrent - in_flight < n_courses:
            return False, (
                f"Technical-course capacity full: {in_flight}/{max_concurrent} "
                f"concurrent courses (need 0.5 Technical Director + 1 Instructor per course; "
                f"limited by workshops: {workshop})."
            )
        if educator.inventory.get(ResourceType.EXPERTISE) < 1 * n_courses:
            return False, f"needs {1 * n_courses} Expertise for this course."
        need_courses = self.courses_needed(len(req.worker_ids))
        if educator.inventory.get(ResourceType.COURSES) < need_courses:
            return False, f"needs {need_courses} Course slot(s) ({educator.inventory.get(ResourceType.COURSES)} on hand)."
        return True, ""
    
    # Worker-band trainees (Unskilled → entry-level) don't exist in the engine
    # today; if they did, default to True.
    return True, ""
```

### Rewrite `TurnManager._consume_training_capacity`

Debit the per-course Expertise and Course slot at admission (same as today's Course debit; add Expertise). Staff are NOT debited from inventory — they're committed via the in-flight state tracking, freed when the course completes.

```python
def _consume_training_capacity(self, educator: Player, req) -> str:
    band = band_of(req.target_profession)
    n_courses = 1
    need_courses = self.courses_needed(len(req.worker_ids))
    educator.give_resources(ResourceType.COURSES, need_courses)
    if band == WorkerBand.MANAGER:
        educator.give_resources(ResourceType.EXPERTISE, 2 * n_courses)
        return f"{need_courses} Course slot(s) + 2 Expertise for the Manager-tier course"
    if band == WorkerBand.TECHNICIAN:
        educator.give_resources(ResourceType.EXPERTISE, 1 * n_courses)
        return f"{need_courses} Course slot(s) + 1 Expertise for the technical course"
    return f"{need_courses} Course slot(s)"
```

## Out of scope (do not touch)

- `island_traders/server/static/` — Claude UI domain.
- `island_traders/server/app.py` connection plumbing (WS reconnect race fix lives here).
- `island_traders/engine/ai.py` proactive Educator behaviour changes (separate Claude task if needed). The new gate may make Educator AI auto-decline more often; that's expected and a follow-up.
- The training transport / PassengerSeats flow — unrelated to this redesign. The user's bug-1 secondary symptom (#5 PassengerSeats shortage) will be addressed separately.
- Game balance constants (`AI_OFFER_MARKUP`, prices, etc.) — calibration was just tuned; don't drift it.
- `requirements/codex-tasks/balance-calibration-2026-05.md` re-run — that's a separate sequenced task after this lands.

## Tests required

Add to `tests/test_engine/` (suggested file: `test_training_staffing.py`):

1. `test_manager_capacity_min_of_2x_professor_and_lecturer` — 3 Prof + 5 Lect → capacity = min(6, 5) = 5; 1 Prof + 5 Lect → min(2, 5) = 2; 2 Prof + 0 Lect → 0.
2. `test_technical_capacity_min_of_2x_td_inst_and_workshops` — 2 TD + 3 Inst + 4 workshop slots → min(4, 3, 4) = 3; with 0 workshops → 0.
3. `test_technical_course_requires_workshop_prerequisite` — Educator with full TD + Instructor staff but no workshops → request blocked with a clear "no Technical Workshop" message.
4. `test_manager_course_does_not_require_workshop` — Manager-tier course is fine without a workshop.
5. `test_staff_locked_for_course_duration` — admit a Manager course → in-flight goes to 1 → admit a second concurrent Manager course → in-flight at 2 → ensure the count holds across multiple seasons until the first course's return tick → after return, in-flight drops by 1.
6. `test_expertise_debited_per_course` — Manager-tier debits 2 Expertise; Technical-tier debits 1.
7. `test_course_slot_debited_per_course_unchanged` — existing courses_needed = ceil(trainees/12) still applies.
8. `test_capacity_blocks_third_manager_course_when_lecturers_pinned` — illustrates the per-concurrent-course lock with realistic numbers.
9. `test_technical_workshop_capital_item_renamed` — `educator.technical_workshop` exists in catalogue with `effects['technical_workshop_slots']`; legacy `educator.apprenticeship_programme` is absent.
10. `test_legacy_apprenticeship_slot_callers_updated` — sanity test that no code path still references `apprenticeship_slot_capacity` or `apprenticeship_slots`.

Run the full suite. **Bar is the full suite green plus the new tests.**

```bash
PYTHONPATH=. .venv/bin/pytest -q
```

Expected: ≥ `369 + N` passing where N is the number of new tests. Several existing training tests will need updating to the new gate (Education Phase 3 tests in particular — Manager-tier courses now need Professor + Lecturer counts, not just Course inventory).

## Migration / breaking changes to call out

- **Save file compatibility**: `educator.apprenticeship_programme` in saved `capital_inventory` dicts won't match the new `educator.technical_workshop` key. Add a migration step in the save-load path (likely `island_traders/server/app.py` or wherever capital inventory loads — grep for `apprenticeship_programme`) that maps the old key to the new on load.
- **STARTING_WORKERS_BY_PROFESSION["Educator"]**: must include `Technical Director` baseline. Without it, **no fresh game can run any technical courses** (workshops alone don't help — staffing also gates).
- **Existing tests**: any test asserting `apprenticeship_slot_capacity`, `Profession.INSTRUCTOR < 1` gate, or specifying training capacity in terms of slot pool will break and need updating.
- **Game balance**: this changes how many concurrent training requests can run. May slow down workforce upgrades in early game (especially Technical courses, which now need both Technical Director AND workshops AND Instructor). The next calibration pass should re-baseline.

## When to stop and hand off

Push the branch when **all** of these are true:

- All Manager-tier and Technical-tier staffing rules implemented per spec.
- `educator.technical_workshop` catalogue item rename complete, with save migration.
- New `Profession.TECHNICAL_DIRECTOR` integrated (enum + label + EDUCATION_SEASONS + STARTING_WORKERS).
- `TrainingRegistry.manager_courses_in_flight` + `technical_courses_in_flight` added.
- `TurnManager._training_capacity_status` + `_consume_training_capacity` rewritten.
- `apprenticeship_slot_capacity` → `technical_workshop_slot_capacity` rename complete.
- 10 new tests + suite green.
- `RELEASE_NOTES.md` has a new `### codex/training-staffing-2026-05` section.
- Signed-off commits (`git commit --signoff`).

**Do not:**

- Modify any client-side file or the WS reconnect plumbing.
- Touch balance constants (calibration just landed).
- Merge into `pre-release` yourself.
- Tag a release.
- Start AI Educator proactive-buying behavior changes (separate scope).

## What to push

```bash
git push -u origin codex/training-staffing-2026-05
```

Open a PR from `codex/training-staffing-2026-05` → `pre-release` with:

- Summary of the spec items implemented
- New test count delta (369 → N)
- A note flagging the calibration re-run as a follow-up (training admission rates will shift).

## When to wait for merge

After pushing:

1. **Wait** for Claude to review the PR. There are several interactions with prior work to verify (Phase 3 settling, Course-debit timing, AI Educator auto-decline behavior).
2. **Wait** for Claude to merge.
3. If Claude requests changes, land them as follow-up commits on the same branch.

## Reference

- **Current training capacity check:** `island_traders/engine/turn.py::_training_capacity_status` (~line 980).
- **Current consume helper:** `_consume_training_capacity` (just below).
- **Apprenticeship slot helper (to rename):** `island_traders/models/capacity.py::apprenticeship_slot_capacity` (~line 129).
- **Apprenticeship capital item (to rename):** `island_traders/constants_capacity.py` `educator.apprenticeship_programme` (~line 207).
- **Profession enum:** `island_traders/models/profession.py::Profession` (add `TECHNICAL_DIRECTOR`).
- **Profession labels:** `PROFESSION_LABEL` dict in the same file.
- **EDUCATION_SEASONS:** in profession.py (Manager Education duration table).
- **STARTING_WORKERS_BY_PROFESSION:** in profession.py — Educator's baseline workforce.
- **TrainingRegistry:** `island_traders/models/training.py` — add the two `*_courses_in_flight` helpers.
- **Existing related TODO:** `TODO.md` Education Phase 3 (Phase 3 work already shipped; this redesign extends that pipeline).
- **Phase 3 spec it amends:** `requirements/education-model.md` — update once the implementation lands (docs-second).

## Notes for Claude on review

When this lands, the prior bug-1 follow-up items still pending are:

- Educator AI proactive PassengerSeats acquisition (separate task).
- Calibration re-run accounting for the new admission cadence (queue `codex/balance-calibration-2026-Q3` or similar).
- Update `RULES.md` Education chapter (separate doc-reconciliation task).
