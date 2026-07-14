# Brief — Break the Educator self-training chicken-and-egg deadlock (2026-06-22)

**Suggested owner:** Codex (training engine + tests).
**Relates to:** training-staffing-2026-05 (per-concurrent-course staffing), training-shared-classrooms.
**Base off:** `origin/pre-release` at **`9e07b41`** (the commit that added these briefs) or
later. This is the exact, canonical version — `git fetch origin` and confirm
`git rev-parse origin/pre-release` resolves to `9e07b41` (or a newer pre-release tip).

## Rules of engagement (Codex — read every time)

- **Worktrees / no shared trees — do NOT use the primary checkout.** The primary checkout
  (`/Users/ashleysilver/Documents/projects/island-traders`) currently holds **unrelated
  uncommitted Claude work** (in-progress room-rejoin edits to `server/app.py` +
  `tests/test_server/test_join_rejoin.py` on branch `claude/integrate-qol-pollution-48-45`).
  Ignore it and leave it untouched. Create your **own dedicated worktree** off the base and
  work there — this is exactly how PR #192 was done:
  `git fetch origin && git worktree add -b codex/education-self-training-deadlock-2026-06-22 ../it-codex-education origin/pre-release`
- **Branch.** Cut a fresh branch off the base above; never commit onto `pre-release`/`master`.
- **PRs only.** Reach `pre-release` through a PR Claude merges. Update `RELEASE_NOTES.md` and
  bump `APP_VERSION` `.N` in `constants.py`.
- **Git discipline.** No `--no-verify`/`--amend`/force-push. Run the **full** `pytest` suite
  before handoff.
- **Handoff.** "branch X at commit Y — ready to integrate."

## Why (symptom)

Playtest 2026-06-22: the Educator hits a **chicken-and-egg deadlock**. Running courses
consumes the Educator's own faculty/teaching capacity (per the training-staffing-2026-05
model: each concurrent course locks Professors / Technical Directors for the full course
duration). But the Educator also needs to **train its own faculty** (grow more Professors /
Technical Directors / Lecturers) to expand capacity — and that self-training itself needs
the very capacity that's already fully consumed. So the Educator can neither train its own
workers nor free capacity to take **external** trainees from other islands. The pipeline
locks up.

## What exists today (diagnose before changing)

- `island_traders/models/training.py`:
  - `TrainingRequest` with a `transport_mode == "self_training"` path
    (`training.py` ~line 166) — the Educator training its own workers.
  - `TrainingRegistry`, `_classrooms_needed`, `cohort_trainees_committed`,
    `MAX_CLASS_SIZE_PER_COURSE`, the per-concurrent-course staffing gate.
- `island_traders/constants.py`:
  - `STARTING_WORKERS_BY_PROFESSION["Educator"]` (~line 430) — the Educator's seed faculty.
  - Education slot / capacity items in `constants_capacity.py`
    (`educator.lecture_hall` `education_slots`, etc.).
- The admission gate that produces the deadlock: when an Educator's faculty is fully
  committed to running courses, a **self-training** request for new faculty is rejected for
  lack of staffing/capacity, so faculty never grows.

**First deliverable: a short written diagnosis** in the PR description identifying the exact
gate(s) that block self-training when capacity is saturated. The fix below is the intended
shape — adjust if the diagnosis shows a cleaner cut.

## Spec — desired behaviour

Pick the approach that the diagnosis supports; the **goal** is: an Educator can always make
forward progress growing its own faculty, even when current capacity is fully committed.
Candidate mechanisms (Codex chooses, justify in PR):

1. **Self-training reserved lane.** Self-training of the Educator's *own* faculty does not
   compete for the same locked teaching-staff slots that external courses use — e.g. a
   senior faculty member can mentor one self-training cohort *in addition to* running a
   course, or self-training draws from a separate small reserve. This guarantees the
   Educator can always bootstrap.

2. **Adequate seed faculty.** Raise `STARTING_WORKERS_BY_PROFESSION["Educator"]` so the
   Educator begins with enough Professors / Technical Directors to run at least one external
   course **and** one self-training cohort concurrently — removing the cold-start lock
   without changing the gate logic. (Simplest; may be combined with #1.)

3. **Self-training priority/queueing.** When capacity is saturated, self-training requests
   are admitted ahead of external ones (the Educator must be able to grow before it serves
   others), with clear log messaging.

**Whichever is chosen:**
- The Educator must be able to go from its starting state to accepting external trainees
  without manual deadlock-breaking.
- External islands' training requests must still eventually be servable (no permanent
  starvation of external trainees in favour of endless self-training — cap self-training
  appropriately).
- Clear turn-log messaging when a self-training cohort is admitted / deferred and why.

## Tests

- A regression test reproducing the deadlock on the **old** behaviour (Educator at starting
  state, faculty fully committed) and proving the new behaviour lets the Educator train its
  own faculty and subsequently accept an external trainee.
- Self-training does not permanently starve external requests.
- Full `pytest` suite green (baseline: **799 passing** on `9e07b41`).

## Coordinate

This brief overlaps the training-staffing model. If the diagnosis shows the deadlock is
inherent to that model's per-course locking, prefer mechanism #1 or #2 over rewriting the
staffing gate. Flag any cross-cutting change to Claude before expanding scope.
