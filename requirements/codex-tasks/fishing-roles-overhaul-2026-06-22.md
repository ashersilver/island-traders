# Brief — Fishing & farming roles overhaul: Marine Biologist + Fish Processing Technician (2026-06-22)

**Suggested owner:** Codex (profession model + production engine + constants + tests).
**Relates to:** engineer-specialisation, balance-calibration, the Farmer specialist model.
**Base off:** `origin/pre-release` (currently `94bf44c`). `git fetch` first; cut
`codex/fishing-roles-overhaul-2026-06-22` off it.

## Rules of engagement (Codex — read every time)

- **Worktrees / no shared trees.** Work in the **primary checkout**
  (`/Users/ashleysilver/Documents/projects/island-traders`). Claude works in a separate
  `claude/*` worktree — do not edit it or run `git reset/checkout/stash` against it.
- **Branch.** Cut a fresh branch off the base above; never commit onto `pre-release`/`master`.
- **PRs only.** Reach `pre-release` through a PR Claude merges. Update `RELEASE_NOTES.md` and
  bump `APP_VERSION` `.N` in `constants.py`.
- **Git discipline.** No `--no-verify`/`--amend`/force-push. Run the **full** `pytest` suite
  before handoff.
- **Handoff.** "branch X at commit Y — ready to integrate."

## Why

Playtest 2026-06-22: as the game progresses, Agriculture needs an unrealistic number of
plain Farmers and Farming Technicians. The user wants fishing to become its own staffed
production line with dedicated professions, and to convert the existing late-season
specialist *penalty* into an optional *bonus* model.

## Current model (read carefully — this PARTLY exists already)

- `island_traders/models/profession.py`:
  - `Profession` enum already has `FARMER`, `FARMING_TECHNICIAN`, `HORTICULTURALIST`,
    `VETERINARIAN`, `MECHANIC`, `CHEF`. **No `MARINE_BIOLOGIST` or
    `FISH_PROCESSING_TECHNICIAN` yet.**
  - `PROFESSION_BAND`, `ROLE_PROFESSIONS["Farmer"]`, `PROFESSION_LABEL`, the
    `MANAGER/TECHNICIAN` band tables under "Farmer".
- `island_traders/engine/production.py`:
  - `_farmer_specialist_multiplier` (line ~58): **currently a penalty** — in Autumn/Winter,
    Produce without a Horticulturalist and Meat without a Veterinarian take a **0.75**
    multiplier. This must change to the optional-bonus model below.
  - `produce()` / `_seasonal_yield` / capacity via `effects` (`farmer.fishing_boat` gives
    `+4 Fish capacity`, `constants_capacity.py:82`).
  - `_seasonal_labour_requirements` / `_labour_productivity_factor` — staffing math.
- `island_traders/constants.py`:
  - `STARTING_WORKERS_BY_PROFESSION["Farmer"] = [("Farmer",1),("Horticulturalist",1),("Veterinarian",1)]`
    (line ~422) — must add the fishing seed workforce.
  - `SKILLED_PROFESSIONS["Farmer"]`, `LABOUR_REQUIREMENTS["Farmer"]`, `SEASONAL_WORKFORCE`.

## Spec

### 1. New professions

Add to `Profession` enum + all the tables that every other profession appears in
(`PROFESSION_BAND`, `ROLE_PROFESSIONS["Farmer"]`, `PROFESSION_LABEL`, the Farmer band map,
`SKILLED_PROFESSIONS["Farmer"]`, and any `STARTING_*` / training tables):

- `MARINE_BIOLOGIST = "Marine Biologist"` — **Manager band** (managerial fishing role).
- `FISH_PROCESSING_TECHNICIAN = "Fish Processing Technician"` — **Technician band**.

### 2. Fishing production rules (Fish output)

- **Marine Biologist gate:** producing Fish **requires** at least one active Marine
  Biologist on the island; **without one, Fish yield drops by 50%** (×0.5). (Not a hard
  block — a 50% penalty, matching the user's wording.)
- **Fish Processing Technician staffing:** **2 Fish Processing Technicians per fishing boat**
  (`farmer.fishing_boat`). A boat that is under-staffed produces proportionally less (use
  the existing labour-productivity degradation pattern, not a hard zero).
- **Boats scale yield:** each `farmer.fishing_boat` contributes its `+4 Fish` capacity as
  today; **two boats double fish output** (already implied by capacity stacking) **and
  require 2 Fish Processing Technicians each** (4 total). Confirm capacity stacks linearly
  with boat count via `effective_capital_inventory()`.

> **Open question — confirm with the user.** The brief text says "Two fishing boats … will
> require an additional Fish Processing Technician." Literally "2 per boat" ⇒ 2 boats need
> 4. Implement **2 per boat** (so 2 boats ⇒ 4) and flag this in the PR for confirmation.

### 3. Farming specialist model — penalty → optional bonus

Replace `_farmer_specialist_multiplier`'s late-season **penalty** with **optional bonuses**
that apply year-round (no longer Autumn/Winter only):

- **Horticulturalist (optional):** +35% to **Grain and Produce** output when at least one is
  active (×1.35 on those outputs). Not required.
- **Veterinarian (optional):** +50% to **Meat** output when at least one is active (×1.50).
  Not required.

Remove the 0.75 penalties. Grain/Produce/Meat are produced by plain **Farmers and Farming
Technicians**; the specialists only *boost*. Keep the bonus multipliers as named constants
in `constants.py` so balance can tune them.

### 4. Starting workforce

`STARTING_WORKERS_BY_PROFESSION["Farmer"]` — Agriculture starts with:
- 1 Marine Biologist
- 2 Fish Processing Technicians

Decide with balance whether the existing 1 Horticulturalist + 1 Veterinarian seed stays
(they are now optional bonuses). Default: **keep them** so the starting island isn't
weaker than today. Update `STARTING_TOTAL_WORKERS["Farmer"]` / band splits accordingly so
totals stay consistent.

### 5. Demand framing

Plain Farmers and Farming Technicians now drive **Grain, Produce, and Meat** (the bulk
labour); fishing is staffed by Marine Biologist + Fish Processing Technicians. This should
reduce the runaway Farmer/Farming-Technician headcount the user observed — verify the
seasonal labour math (`_seasonal_labour_requirements`, `LABOUR_REQUIREMENTS["Farmer"]`,
`SEASONAL_WORKFORCE["Farmer"]`) reflects fishing labour moving to the new technicians
rather than piling onto generic Farmers.

## Tests

- New professions present in every table a profession must appear in (no `KeyError` from a
  missing band/label/role mapping). Add a guard test that iterates `ROLE_PROFESSIONS` and
  asserts each profession has a band + label.
- Fish yield ×0.5 without a Marine Biologist; full yield with one.
- Under-staffed boats (fewer than 2 Fish Processing Technicians/boat) produce
  proportionally less; correctly staffed boats produce full; 2 boats ≈ double 1 boat.
- Horticulturalist gives +35% Grain & Produce; Veterinarian +50% Meat; **no penalty** when
  absent (regression against the old 0.75 behaviour).
- Starting Farmer workforce includes 1 Marine Biologist + 2 Fish Processing Technicians.
- Training pipeline can train the two new professions (they appear in the trainable sets).
- Balance tests (`tests/test_models/test_economy_balance.py`) still within tolerance — tune
  bonus magnitudes / costs if a role drifts out of band.
- Full `pytest` suite green (baseline: **799 passing** on `94bf44c`).

## Open questions for the user (note in PR if unresolved)

1. Fish Processing Technicians per boat: **2 per boat** assumed (2 boats ⇒ 4). Confirm vs
   "one additional per second boat."
2. Keep the starting Horticulturalist + Veterinarian now that they're optional bonuses?
   (Default: keep.)
3. Marine Biologist as a hard *requirement* for any Fish at all vs the **50% penalty**
   chosen here. (Default: 50% penalty, per the brief wording.)
