# Codex Task — §21 Balance-aware Sustenance Model (+ RULES.md Doctor fix)

**Goal:** Replace the legacy Food/Fish demand path with the balance-aware
sustenance model specified in `requirements/production-capacity-model.md
§21`, and fix the stale Doctor-workforce numbers in `RULES.md`.

This is the dependency that Education **Phase 3's "campus load"** hooks
into — Claude is implementing Phase 3 in parallel and will surface a
visiting-trainee count for the Education Island; this task owns the
demand-model side that consumes it (see "Campus-load interface" below).

## Background

`requirements/production-capacity-model.md §21` ("Food demand model
refinement") is fully specified but **not yet implemented**:

- `island_traders/models/player.py::population_food_fish_needs()` still
  uses the legacy model: `food = ceil(population / 50)`,
  `fish = ceil(population/100) + ceil(educated/8)`. Every island looks
  "hungry" from turn 1, which masks growth-driven demand and makes the
  Farmer fight an uphill battle.
- There is **no** `BASE_POPULATION_SELF_FED` constant yet.
- The forward-looking runway warnings already exist in
  `island_traders/server/app.py` (~line 1741, `sustenance_alerts`) and
  are roughly per §21 already — keep them; just make sure they read the
  refactored `population_food_fish_needs()` correctly.

## Branch

- **Base:** `pre-release` (latest `origin/pre-release` HEAD — currently
  the `claude/docs-phase3-reconcile` merge `11ec312` or later)
- **Branch name:** `codex/sustenance-model`
- **Target for merge:** `pre-release`

## Scope — what to implement

### 1. §21 base-self-fed refactor

- Add `BASE_POPULATION_SELF_FED = 100` to `island_traders/constants.py`.
- Refactor `Player.population_food_fish_needs()` so the island's first
  `BASE_POPULATION_SELF_FED` residents generate **zero** marginal market
  Food demand (they live off subsistence agriculture / local fishery).
  Only population *above* that baseline creates marginal demand
  (suggested: **+1 Food/season per resident over baseline**, tunable).
- The educated-workforce Fish signal (`ceil(educated/8)`) stays as a
  separate, unchanged layer on top.
- Do **not** merely rename Food/Fish — the model must not double-count
  packaged Food vs raw ingredients (per §21's "Legacy implementation
  note").

### 2. Campus-load interface (the Phase 3 seam)

Education Phase 3 (Claude, branch `claude/education-phase3`) computes a
count of **visiting trainees currently away at the Education Island**.
Expose the consumption side here:

- Add an **optional** `extra_residents: int = 0` parameter (or a clearly
  named equivalent) to `population_food_fish_needs()` so a caller can add
  transient mouths to the marginal-demand calculation **without** mutating
  the resident `population`.
- These visiting trainees count as marginal residents (they are *over*
  baseline by definition) → each adds +1 Food/season for the seasons they
  are on campus.
- Server integration (passing the real visiting-trainee count in) is
  **Claude's Phase 3 responsibility** — you only need to provide and test
  the parameter. Default `0` must be behaviourally identical to omitting
  it. Document the parameter contract in the docstring.

### 3. RULES.md Doctor workforce fix (standing bug, CLAUDE.md task #2)

`RULES.md`'s Doctor/Healthcare section states stale numbers (workforce
12, Nurses 10) that predate the current constants. Correct values from
`island_traders/constants.py`: **6 total workers = 2 Doctors + 4
Nurses**. Find the Doctor section and correct it. (If the medical-lab
rename has not landed yet, keep the existing "Healthcare/Doctor"
heading — only fix the numbers.)

## Files in scope

- `island_traders/constants.py` — add `BASE_POPULATION_SELF_FED`
  (additive; safe)
- `island_traders/models/player.py` — `population_food_fish_needs()`
  refactor + `extra_residents` param
- `island_traders/server/app.py` — only the `sustenance_alerts` block
  (~1741) if needed so runway maths still reads correctly
- `RULES.md` — Doctor workforce numbers
- `tests/test_models/` and `tests/test_server/` — add/adjust coverage
- `RELEASE_NOTES.md` — add a `### codex/sustenance-model` section

## Files OUT of scope (Claude is actively editing these for Phase 3)

- `island_traders/engine/turn.py`
- `island_traders/models/training.py`
- `island_traders/models/profession.py`
- `island_traders/models/workforce.py`
- `island_traders/constants_capacity.py`
- `requirements/education-model.md`

`server/app.py` is shared: Claude's Phase 3 only adds a *new* campus-load
field elsewhere in the game-state payload and will not touch the
`sustenance_alerts` block — keep your edits confined to that block to
avoid conflicts. If you must touch anything in the OUT list, stop and
coordinate via a `RELEASE_NOTES.md` note before merging.

## Acceptance criteria

- ✅ An island at exactly `BASE_POPULATION_SELF_FED` residents and no
  educated-workforce signal generates **0** marginal Food demand.
- ✅ Population growth above baseline produces a proportional, testable
  marginal Food demand.
- ✅ `population_food_fish_needs(extra_residents=N)` adds exactly N
  marginal residents' worth of demand; default is identical to the
  no-arg call.
- ✅ Server `sustenance_alerts` runway warnings still compute correctly
  against the new model (warn < 2 seasons, urgent < 1, recommended
  purchase = `max(0, 2×need − on_hand)`).
- ✅ `RULES.md` Doctor section shows 6 workers (2 Doctors + 4 Nurses).
- ✅ Full suite green: `.venv/bin/python -m pytest tests/` (≥ 283
  passing — that's the current `pre-release` baseline).
- ✅ `RELEASE_NOTES.md` has a `### codex/sustenance-model` section.

## Hand-off

1. `git add -A && git commit -s ...` (DCO sign-off required — see
   `CONTRIBUTING.md`)
2. `git push -u origin codex/sustenance-model`
3. Merge locally to `pre-release` and push, or open a PR — the
   established workflow this session has been local merges + push.
4. RELEASE_NOTES section header at the top of `## Unreleased` won't
   conflict with Claude's `### claude/education-phase3` section.

## Reference

- Spec: `requirements/production-capacity-model.md §21` (verbatim source
  of truth — read it before starting).
- Campus-load rationale: `requirements/education-model.md` → "Campus
  load" subsection (Claude's Phase 3 spec, for context on the seam).
