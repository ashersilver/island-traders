# Brief — #18 Training costs to be covered: reconcile the model to spec (2026-06-17)

**Suggested owner:** Codex (engine: training model + turn fee logic).
**Base off:** current `origin/pre-release`.
**Tracking issue:** [#18](https://github.com/ashersilver/island-traders/issues/18).
File the work as `Closes #18`.
**Pairs with:** Claude surfaces any new/!changed fee components in the Training
Desk dialog (#158) + the fee breakdown. Second of {engine PR, UI PR} to merge
wires the integration; the first leaves a stub.

---

## Rules of engagement (Codex — read every time)

- **Worktrees / no shared trees.** You work in the **primary checkout**
  (`/Users/ashleysilver/Documents/projects/island-traders`). Claude works in a
  **separate worktree** on a `claude/*` branch. Do not edit Claude's worktree or
  run `git reset/checkout/stash` against it. Coordinate via pushed branches +
  PRs only.
- **Branch creation.** `git fetch`; confirm current
  (`git merge-base --is-ancestor origin/pre-release HEAD`); cut a fresh branch
  off `origin/pre-release`, e.g. `codex/training-costs-18-2026-06-17`. Never
  commit straight onto `pre-release` or `master`.
- **PRs only — no fast-forwards.** Every change reaches `pre-release` through a
  PR Claude merges. Do **not** push/fast-forward to `pre-release`. `Closes #18`.
  Update `RELEASE_NOTES.md` and bump `APP_VERSION` `.N` in `constants.py`.
- **Git discipline.** No `--no-verify`, no `--amend`, no force-push; new commits
  only. Run the **full** `pytest` suite before handoff.
- **Handoff.** "branch X at commit Y — ready to integrate" + a UI-stub note.

---

## The requirement (#18, verbatim)

Enrolment fees must cover, and training must differentiate by:

1. **Transportation** — *already covered.*
2. **Food and accommodation.**
3. **Duration of the course (1–4 seasons)** — e.g. Doctor is 4 seasons.
4. **Degree of expertise required** to train the person.
5. Generally the expertise required is **1 unit per season (semester) per
   course**.
6. Use of the **Apprenticeship training facility** reduces vocational training
   for technicians to **1 season** to qualify; **otherwise** they spend an
   **extra season** and **count as a 50% technician for one season** when they
   return to their island.

---

## Most of this already exists — audit before building

This requirement is **largely shipped** across the Education Model phases. Read
these first; the task is mostly **reconciling the model to the exact spec**, not
greenfield work.

- **Duration (1–4 seasons):** `away_seasons(profession)`
  (`island_traders/models/training.py:25`) → Manager-band uses
  `EDUCATION_SEASONS` (`island_traders/models/profession.py:192`, e.g. Doctor),
  Technician-band uses an apprenticeship away-duration. `duration_seasons` rides
  on `TrainingRequest` (`training.py:83`) and
  `TurnManager._training_duration_for_selection` (`turn.py:1481`).
- **Food & accommodation:** `TRAINEE_FOOD_ACCOM_PER_SEASON = 5.0`
  (`constants.py:716`) is already folded into the suggested fee
  (`turn.py:1178` → `food_accom += TRAINEE_FOOD_ACCOM_PER_SEASON * count *
  duration`).
- **Transport:** ticket cost via `dollops_to_transporter` and the
  Educator-supplied-tickets offset (`turn.py:1185`); cargo/flight options exist.
- **Expertise cost:** the suggested-fee loop already charges
  `expertise_price × courses × duration` — **but only for Manager-band courses**
  (`turn.py:1181`, `if band_of(profession) == WorkerBand.MANAGER`).
- **Apprenticeship facility:** `educator.technical_workshop`
  (`constants_capacity.py:245`, `effects={"technical_workshop_trainees": 6}`)
  exists and gates **concurrent technician capacity**
  (`technical_workshop_trainee_capacity`, used `turn.py:1805`).
- **Settling penalty:** a returning apprentice gets `settling_seasons` of
  reduced productivity (`workforce.py:25`, `:53`, `:109`) at
  `APPRENTICESHIP_SETTLING_EFFICIENCY = 0.75` for
  `APPRENTICESHIP_SETTLING_SEASONS = 1` (`profession.py:243`–`:245`).

The suggested-fee breakdown is computed/printed in `_action_request_training`
(`turn.py:1160`–`1194`).

## The gaps to close (this is the actual work)

1. **Apprenticeship facility should change *duration + penalty*, not just
   capacity (spec point 6).** Today the `technical_workshop` only gates how many
   technicians can train concurrently, and the **0.75 settling penalty applies
   to every returning apprentice regardless**. Per spec, make technician
   vocational training **conditional on the facility**:
   - **With** `educator.technical_workshop` at the campus → **1 season** away,
     **no** settling penalty.
   - **Without** it → **+1 season** away (so 2) **and** one settling season at
     **50%** efficiency on return.
   This means `away_seasons` / `_training_duration_for_selection` must take the
   chosen campus's facility into account, and the settling assignment
   (`workforce.py:109`) must be gated on the same condition.

2. **Settling efficiency value (spec says 50%).** `APPRENTICESHIP_SETTLING_
   EFFICIENCY` is `0.75`. Either change it to `0.5` to match the spec or, if
   0.75 was a deliberate balance call, document the divergence in
   `requirements/education-model.md` and the issue. Default to the spec (0.5)
   unless calibration says otherwise.

3. **Expertise = 1 unit/season/course for *all* course-bearing tracks (points
   4–5).** The fee loop charges expertise only for Manager-band. Confirm whether
   Technician-tier (apprenticeship) courses should also consume **1 Expertise
   per season per course** and, if so, extend the charge uniformly. Keep the
   "1 unit per season per course" rule explicit and centralised (a helper), so
   both the fee estimate and any actual consumption agree.

4. **Charge vs suggest — make the components actually settle.** The wizard
   computes a *suggested* fee and the player offers a number; verify the agreed
   fee/expertise/food-accom are actually **consumed/transferred** on
   approval/return (not merely displayed), and that the **#158 Training Desk
   batch path** (`_submit_training_batch_row`, `app.py`) applies the **same**
   duration/facility/penalty rules as the wizard. The batch path currently takes
   a client-supplied `dollops_to_educator`; ensure duration and the
   facility-conditional settling are computed server-side regardless of the
   offered fee.

5. **Doctor = 4 seasons (spec point 3).** Confirm `EDUCATION_SEASONS` yields the
   intended 1–4 spread and that Doctor is 4 (the spec calls it out explicitly);
   adjust if it reads 3.

## Constraints & gotchas

- **One source of truth for duration.** `away_seasons` and
  `_training_duration_for_selection` must not disagree once the facility
  condition is added — route both through one helper that takes
  `(profession, campus_player, specialty)`.
- **AI + sim.** The rule AI and the calibrated sim drive the same training path;
  a longer no-facility technician track + a 50% settling season will move
  workforce economics. Re-run `python -m island_traders.simulation.runner
  --games 1000 --seed 42` and report win-rate spread before/after; retune
  `config/event_charts.yaml` only if a role falls out of band.
- **Save/load.** `settling_seasons` already serialises; if you add a
  facility-conditional flag to a request/worker, extend `Game` save/load
  (`game.py`) and a round-trip test.
- **Don't double-count transport.** Point 1 is already covered; don't re-add a
  transport charge.

## Tests to add (`tests/test_engine`, `tests/test_models`, `tests/test_server`)

1. Technician trained **with** a `technical_workshop` at the campus → 1 season
   away, returns at full efficiency (no settling).
2. Technician trained **without** the facility → 2 seasons away, returns with one
   settling season at 50% efficiency; efficiency restores after one season.
3. Fee breakdown includes food/accom (per season × duration), transport, and
   expertise = 1/season/course for the relevant bands; the agreed amounts are
   actually transferred on approval/return.
4. #158 batch path computes the same duration + facility-conditional settling as
   the wizard, independent of the client-supplied fee.
5. Doctor course duration is 4 seasons; save/load round-trips any new fields.

## Definition of done

- Apprenticeship facility conditions technician **duration + settling**, settling
  at the spec's 50% (or documented divergence); expertise charged 1/season/course
  uniformly; fee components actually settle; wizard and #158 batch path agree.
- New tests green; **full suite green**; seeded sim re-run with before/after
  win-rate spread in the PR.
- `APP_VERSION` bump + `RELEASE_NOTES.md`; `education-model.md` updated.
- PR `Closes #18`; one-line note on UI integration (wired vs stub).
- Hand back: "branch X at commit Y — training-cost model reconciled" with any
  new fee-breakdown payload fields for the Training Desk UI.
