# Codex Task — Shared training classrooms (same profession + season) (2026-05-29)

**Owner:** Codex
**Origin:** Playtest 2026-05-29, issue #3. *"If approval for training is delayed,
and a later request comes in for the same training, both requests can be
accommodated in the same course. If one engineer request is approved and starts
immediately, another request to train an engineer in the same season should not
require an additional Course slot — it shares the existing engineer course."*

## The problem

A Course is a classroom holding up to `MAX_CLASS_SIZE_PER_COURSE = 12` trainees.
Today every training **batch** (request) is charged Course slots independently:

- `courses_needed(n) = ceil(n / 12)` is computed **per request**.
- `_training_capacity_status` / `_consume_training_capacity`
  (`island_traders/engine/turn.py`) gate and debit `Course` + `Expertise`
  **per batch**.
- `_courses_in_flight` (`island_traders/models/training.py`) counts **one course
  per in-flight request**, regardless of how full each classroom is.

So two separate 1-trainee "Engineer" requests in the same season each burn a
full Course slot (+ Expertise) and each count as a separate concurrent course —
even though both trainees would fit in **one** 12-seat classroom.

## Goal

Make Course slots, Course-Expertise, and concurrent-course staffing accounting
**shared per cohort**, where a cohort = `(educator_id, target_profession,
season the course runs)`. Within a cohort, trainees fill classrooms of 12 before
a new classroom (Course slot) is needed. A later same-profession, same-season
request fills leftover seats in an already-committed classroom at **zero
incremental Course/Expertise cost** until the classroom is full.

## Branching
- **Base:** `pre-release` (current head; rebase if it moves).
- **Branch:** `codex/training-shared-classrooms-2026-05-29`
- **Target:** `pre-release`. **Push and stop** — do not merge. Claude reviews.

## Spec

### Cohort definition
A cohort is keyed by `(educator_id, target_profession, cohort_season)` where
`cohort_season` is the season the course **starts/runs**:
- For `DISPATCHED` requests: `(dispatched_year, dispatched_season)`.
- For `AWAITING_TRANSPORT` (approved, not yet dispatched) requests: treat as the
  **current** season being processed (they will dispatch this season).

Only `AWAITING_TRANSPORT` and `DISPATCHED` requests count toward a cohort (same
statuses `_courses_in_flight` already uses). Rejected/completed never count.

### Incremental classrooms (the core change)
When admitting a new batch of `n` trainees into a cohort that already has
`existing` committed trainees:

```
classrooms(t) = ceil(t / MAX_CLASS_SIZE_PER_COURSE)
incremental_courses = classrooms(existing + n) − classrooms(existing)
```

- `_training_capacity_status(educator, req)` must gate on `incremental_courses`
  (Course slots on hand, Expertise needed) — **not** `courses_needed(n)`.
- `_consume_training_capacity(educator, req)` must debit `incremental_courses`
  Course slots and the matching Expertise (2×incremental for Manager-tier,
  1×incremental for Technician-tier). When `incremental_courses == 0`, debit
  nothing (the batch rides an existing classroom).
- The concurrency gate (`manager_courses_in_flight` /
  `technical_courses_in_flight`, via `_courses_in_flight`) must count **distinct
  classrooms per cohort** (sum of `classrooms(cohort_trainees)` across cohorts of
  that band), not one-per-request. So two shared 1-trainee engineer batches =
  **1** course in flight, not 2.

### Suggested implementation
Add to `TrainingRegistry` (`models/training.py`) a helper, e.g.:
```python
def cohort_trainees_committed(self, educator_id, profession,
                              year, season, exclude_batch_id=None) -> int:
    """Trainees already committed (AWAITING_TRANSPORT or DISPATCHED) in the
    same (educator, profession, course-running season) cohort."""
```
and refactor `_courses_in_flight` to sum classrooms per cohort for the band.
Then update the two `turn.py` capacity methods to use
`incremental_courses` computed from `cohort_trainees_committed`.

Keep `courses_needed(n)` (still the right answer for a standalone cohort) but
compute admission/debit incrementally against the cohort.

### Unchanged
- The Technical Workshop **per-trainee** seat gate
  (`technical_trainees_in_flight` vs workshop seats) already aggregates trainees
  correctly — leave it as is.
- University annual/seasonal caps (`capacity_remaining`) are unchanged.
- Self-training and cross-island flows, dispatch/return timing — unchanged.

## Tests (`tests/test_engine/` — add a focused file)
- Two separate 1-trainee same-profession requests **in the same season** consume
  **one** Course slot total (second batch debits 0), and count as **1** concurrent
  course in flight.
- A 12-seat classroom fills: the 13th trainee in the cohort triggers a **second**
  Course slot + its Expertise.
- Different professions, or the same profession in a **different season**, do
  **not** share — each opens its own classroom.
- Manager-tier Expertise (2/classroom) and Technician-tier Expertise
  (1/classroom) are charged per **incremental** classroom, not per batch.
- Regression: a single large batch (e.g. 13 trainees) still needs 2 classrooms
  exactly as before.

## Seam note
This touches `models/training.py` (new cohort helper + `_courses_in_flight`
refactor) and `engine/turn.py` (`_training_capacity_status`,
`_consume_training_capacity`). Claude has a small concurrent edit in
`turn.py::_action_review_staffing_requests` (a different method — staffing, not
training), so conflicts are unlikely; per the merge-order rule, whoever merges
second re-applies around the other's hunk. Coordinate via these line-distinct
methods.
