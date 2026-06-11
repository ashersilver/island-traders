# Codex Task — Kitchen tiers: Industrial (20, no chef) + Manufacturing (10, chef) (2026-06-02)

**Owner:** Codex
**Origin:** [Lab Supplies + Kitchen brief §C](../lab-supplies-and-kitchens-2026-06-02.md),
2026-06-02 playtest. Decisions there are **locked**; numbers are tunable in the
later calibration pass.

## Goal

Replace today's single kitchen (`common.kitchen`: 6 Food/season, Chef-gated)
with **two tiers**:

| Kitchen | Food/season | Chef? | Recipe (per Food) | Cost | Availability |
|---|---|---|---|---|---|
| **Industrial Kitchen** (`common.industrial_kitchen`, NEW) | 20 | **No** | 1 Grain + 0.5 Produce + 0.5 Protein | 150 Dp | opening-investment catalogue + buyable |
| **Manufacturing Kitchen** (`common.kitchen`, existing) | **10** (was 6) | **Yes** | 2 Grain + 1 Produce + 1 Protein (unchanged) | unchanged | sold by Manufacturing / market |

"Protein" = Fish or Meat from local inventory (existing `_run_one_kitchen`
behaviour). Fractional per-Food recipe means the Industrial Kitchen's full
20-Food run needs 20 Grain + 10 Produce + 10 Protein/season.

## Branching
- **Base:** `pre-release` (current head; rebase if it moves).
- **Branch:** `codex/kitchen-tiers-2026-06-02`
- **Target:** `pre-release`. **Push and stop** — do not merge. Claude reviews.

## Spec

### Constants (`island_traders/constants.py`)
Generalise the single-kitchen constants to **per-item config**. Suggested shape:
```python
# item_id -> kitchen spec
KITCHEN_SPECS: dict[str, dict] = {
    "common.kitchen": {
        "food_per_season": 10,          # was KITCHEN_FOOD_PER_SEASON = 6
        "requires_chef": True,
        "recipe": {"Grain": 2, "Produce": 1, "Protein": 1},  # per Food
    },
    "common.industrial_kitchen": {
        "food_per_season": 20,
        "requires_chef": False,
        "recipe": {"Grain": 1, "Produce": 0.5, "Protein": 0.5},  # per Food
    },
}
```
Keep `KITCHEN_ITEM_ID = "common.kitchen"` if other code references it, but the
engine should iterate `KITCHEN_SPECS`. Fractional recipe amounts: multiply by
`food_per_season` and `ceil`/round to whole ingredient units when deducting
(e.g. 20 Food × 0.5 Produce = 10 Produce). Decide rounding so a full run never
silently under-charges; round ingredient totals **up**.

### Capital catalogue (`island_traders/constants_capacity.py`)
- Add `common.industrial_kitchen` capital item: role-agnostic ("common", like
  the existing kitchen), durable, cost **150**, delivery 1 season,
  `description` noting "20 Food/season, no Chef required".
- Ensure it appears in the **opening investing catalogue** (whatever drives the
  investing-phase item list for "common"/all-role items — mirror how
  `common.kitchen` surfaces there).

### Engine (`island_traders/engine/production.py`)
`run_kitchens` / `_run_one_kitchen` currently assume one kitchen type + a global
Chef gate. Generalise:
- For **each** kitchen item the player owns (`effective_capital_inventory`),
  look up its `KITCHEN_SPECS` entry.
- **Chef gating is per-item**: a `requires_chef` kitchen runs only if a Chef is
  available; chefs are a limited pool — **one Chef staffs one chef-requiring
  kitchen** (preserve today's "kitchen idle: needs Chef staffing" semantics,
  counting only chef-requiring kitchens against the Chef count). `requires_chef
  == False` kitchens (Industrial) run without consuming a Chef.
- Each running kitchen produces its `food_per_season` Food **if** it can pay its
  recipe (scaled by food output); otherwise it's idle with a clear reason
  ("Industrial Kitchen idle: short on Grain").
- Keep returning the per-kitchen log lines (so the UI/log shows what ran / why
  idle).

### Discoverability (small)
Today a kitchen sits silently idle when it can't run. Keep/extend the idle-reason
log lines so the player sees: "needs a Chef" (Manufacturing kitchen) or "short
on <ingredient>". (UI hint wiring is Claude's side; just make the engine emit
clear strings.)

## In scope
- `constants.py` (KITCHEN_SPECS), `constants_capacity.py` (new capital item),
  `engine/production.py` (`run_kitchens`/`_run_one_kitchen`).
- Tests: `tests/test_engine/test_kitchen_tiers_2026_06_02.py`.

## Out of scope (do NOT touch)
- The **Lab Supplies/Reagents rename** and the new **Laboratory Equipment
  capital** (Claude owns that, parallel — see the lab brief).
- `server/` and `index.html` (Claude wires any UI hint).

## Tests
- Industrial Kitchen produces **20 Food/season with no Chef**, consuming 20
  Grain + 10 Produce + 10 Protein (Fish/Meat).
- Manufacturing Kitchen produces **10 Food/season** and is **idle without a
  Chef**; with a Chef it runs.
- Two chef-requiring kitchens + one Chef → only one runs (the other logs "needs
  a Chef"); an Industrial Kitchen alongside still runs (no Chef consumed).
- A kitchen short on an ingredient is idle with a clear reason and produces 0.
- Regression: an island with only `common.kitchen` + a Chef now makes 10 (not 6).

## Seam note
Independent of the lab split (different files: kitchens touch
`production.py`/kitchen constants/catalogue; the lab split touches the resource
enum, recipes, and a different catalogue item). Per the merge-order rule,
whoever merges second re-applies around the other; conflicts unlikely.
