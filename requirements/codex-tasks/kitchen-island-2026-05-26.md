# Codex Task — Kitchens: islands cook their own Food (2026-05-26)

**Owner:** Codex
**Origin:** 2026-05-26 playtest feedback (`0.1.0-dev.2026-05-26`). Players want a path to self-sufficiency on Food when imports are scarce or expensive. Today only the Farmer produces Food; everyone else depends on imports or the sustenance basket allocator. Add a capital item that lets *any* island convert raw ingredients into Food, gated by a new Chef profession so it's still a real workforce decision (not just "buy the building and you're done").

## Goal

Add a **Kitchen** capital item to the catalogue. When owned and properly staffed, each kitchen produces a fixed amount of Food per season from raw ingredients out of the lessee's inventory. Requires a **Chef** (new Technician-tier profession) to run; without a Chef on roster the kitchen sits idle.

This is purely additive — does not change existing Farmer production, the sustenance basket, or the existing inventory/consumption flow. A kitchen-owner with no raw ingredients on hand simply produces no Food that season (graceful no-op, not an error).

## Spec — decisions locked in 2026-05-26

| Decision | Answer |
|---|---|
| Recipe | **1 Food = 2 Grain + 1 Produce + 1 (Fish OR Meat)**. Single fixed recipe. Chef chooses Fish vs Meat at production time, preferring whichever is more plentiful in the player's inventory (ties → Fish). |
| Chef profession | **New Technician-tier profession `Chef`**, available at *every* island. Default starting workforce has **0 Chefs** on every island — must be trained from Unskilled like any other Technician. Use the existing technical-course training pipeline (Instructor + Expertise + Workshop or new "Kitchen" trainer slot — see below). |
| Capacity & price | **Defer to Codex calibration.** Pick numbers that keep a fully-staffed Kitchen attractive vs imports for islands with surplus raw ingredients, without breaking the Farmer's win-rate ceiling. Sensible starting point: 6–10 Food / season, cost 60–100 Dp, lifespan ~12 seasons (matches existing capital lifecycle Phase C). |
| Lease eligibility | **Cash-only** (no `lease_terms`). Lease can be added later if playtest demand warrants it. |
| Staffing rule | **1 Chef per kitchen per season** to operate at full capacity. Partially-staffed kitchens (e.g. 2 kitchens, 1 Chef) operate one and idle the other. |
| Raw input fallback | Kitchen consumes from the lessee's own `inventory` only — no automatic market buy. If the player is short on (say) Produce, the kitchen produces zero Food that season and no inputs are consumed. Show this as a "Kitchen idle: short on Produce" entry in the season summary. |

## Branching

- **Base:** `pre-release` at `6d3888e` (current head — restore-action-menu fix) or later.
- **Branch name:** `codex/kitchen-island-2026-05-26`
- **Target for merge:** `pre-release`. **Do not merge yourself.** Push the branch and stop. Claude will review.

## Files to touch (suggested)

- `island_traders/constants_capacity.py` (or wherever `CAPITAL_CATALOGUE` lives) — add the new Kitchen `CapitalItem`.
- `island_traders/constants.py` — add `Chef` to `SKILLED_PROFESSIONS`, `LABOUR_REQUIREMENTS`, and any other workforce-graph tables. Make sure `STARTING_WORKERS_BY_PROFESSION` does NOT pre-place any Chefs on any island. Add the recipe as `KITCHEN_RECIPE: dict[str, int] = {"Grain": 2, "Produce": 1, "FishOrMeat": 1}` or similar.
- `island_traders/engine/production.py` (or wherever per-island production runs) — after the normal production pass, run a Kitchen pass for every player that owns ≥1 Kitchen: for each kitchen, check Chef availability, check raw ingredients, consume + emit, log the result.
- `island_traders/models/training.py` — confirm the existing technical-course pipeline can train Chefs without new code (it should — Chef is just another Technician profession). If a new trainer slot (e.g. "Kitchen Instructor" or reuse Instructor) is needed, document the choice in the brief response.
- `tests/test_engine/test_production.py` (or a new `test_kitchen.py`) — add regression tests covering: full-stack production, no-Chef no-op, missing-ingredient no-op, Fish-vs-Meat tie-break, multiple kitchens with partial staffing.

## Acceptance criteria

- A player can purchase a Kitchen in the Investing Phase (and via `PURCHASE_CAPITAL` mid-game) for the calibrated price.
- A player can train an Unskilled worker into a Chef via the existing technical-course pipeline (whatever you settle on as the trainer prerequisite — Instructor + Workshop is the obvious default).
- During production, owned Kitchens with Chef capacity convert raw ingredients into Food per the recipe, log a per-kitchen line in the season summary, and leave the inventory in the expected shape.
- An owned Kitchen with no Chef on roster idles and emits zero Food (logged).
- An owned Kitchen with insufficient raw ingredients idles and emits zero Food (logged with which ingredient ran short).
- The calibration runner (1000g seed 42 + 4-seed sweep) shows no role moves more than ±2 pp out of the [12 – 18 %] band the post-balance work landed in. If the Kitchen visibly disturbs the balance, recalibrate as part of this brief.
- Full test suite green at the new baseline count (429 + new tests).
- `RELEASE_NOTES.md` Unreleased section gets a new `### codex/kitchen-island-2026-05-26` block listing what shipped.

## UI follow-up (Claude will handle separately)

Once the engine ships, Claude will:
- Surface "Kitchen" in the Investing Phase catalogue with the new capacity / Chef-required line.
- Add a "Chefs" column to the workforce display.
- Add a Kitchen capacity reading to the per-island production preview.
