# Codex Task — AI Manufacturer demand-driven product mix (2026-05-26)

**Owner:** Codex
**Origin:** 2026-05-26 playtest (`0.1.0-dev.2026-05-26`). User report: *"Education never gets to buy Laboratory Equipment because Manufacturing is never able to produce it, and it blocks the production of Courses, Expertise and Patents in the mid-game."*

The recipe is cheap — `LaboratoryEquipment` needs only 1 Metal + 1 Oil and produces 30 units per batch (`MANUFACTURER_PRODUCT_LINES["LaboratoryEquipment"]`). The blocker isn't the recipe; it's that the AI Manufacturer opens on `FarmMachinery` (the default line) and **never switches lines** during the game, regardless of what other islands are buying.

Doctor and Educator both require `LaboratoryEquipment` to operate (`PRODUCTION_INPUTS["Educator"] = {"LaboratoryEquipment": 1}`, `PRODUCTION_INPUTS["Doctor"] = {"Expertise": 1, "LaboratoryEquipment": 1}`). If no human is playing Manufacturer, Education's mid-game production of Courses / Expertise / Patents stalls because no LabEquipment is being made anywhere. Same for Doctor.

## Goal

Make the AI Manufacturer's product-line choice **demand-driven** rather than static. Each season, before producing, the AI re-evaluates which of the five product lines (`FarmMachinery`, `MiningEquipment`, `LaboratoryEquipment`, `MedicalDevices`, `TransportEquipment`) has the strongest unmet demand signal and switches to it if the gap is meaningful.

## Branching

- **Base:** `pre-release` at `ba74a59` or later.
- **Branch name:** `codex/ai-manufacturer-product-mix-2026-05-26`
- **Target for merge:** `pre-release`. **Do not merge yourself.** Push the branch and stop. Claude will review.

## Spec

### Demand signal

For each product line, compute a per-season "demand score":

```python
score(line) = (current_market_price[line] / base_price[line])
            × max(0, demand_units[line] − supply_units[line])
```

Where:
- `current_market_price` is the live `Market.current_price` for that resource.
- `base_price` is `BASE_PRICES[line]`.
- `demand_units` is the sum of per-season inputs other islands need (look at `PRODUCTION_INPUTS` plus `MANUFACTURER_PRODUCT_LINES[*]["inputs"]` to find consumers of each output).
- `supply_units` is what the Manufacturer's *own* inventory currently holds plus what they're producing this season at the candidate line's `qty`.

Pick the line with the highest score. If the top line's score is within 10 % of the currently-selected line's score, **stay** on the current line (sticky to avoid thrashing every season). Otherwise switch.

### Per-line input feasibility

A line can only be chosen if the AI Manufacturer holds enough Metal / Oil to run it for *at least one* season. If the top-scoring line can't be produced this season (insufficient inputs), fall back to the highest-scoring line whose inputs are on hand. If nothing can be produced, log a clear "Manufacturer idle — out of inputs" message and end the production action gracefully (don't crash).

### Required-input procurement

If the AI Manufacturer is choosing `LaboratoryEquipment` but is short on Metal, it should bias its market-buy actions toward Metal first. This is a small extension to whatever priority-buying logic the AI already uses — surface input shortage for the *chosen* line as the top buy target each turn.

### Tests

- `tests/test_engine/test_ai_manufacturer.py`:
  - With high LabEquipment demand and zero supply, the AI picks LaboratoryEquipment within 2 seasons of game start.
  - Sticky behaviour: if FarmMachinery and LabEquipment scores are within 10 %, no switch happens.
  - Out-of-inputs fallback: top-scoring line lacks Metal, AI falls back to second-best feasible line.
  - Idle path: no line can be produced → AI logs the reason and skips production.
- One simulation-level test: run a 1-year sim with 1 human Educator + 1 AI Manufacturer + 5 other AIs; assert that the Educator's mid-game LabEquipment inventory ends positive (i.e. the Manufacturer did sell them something).

## Acceptance criteria

- AI Manufacturer picks a product line each season based on the demand score above.
- Sticky 10 % threshold prevents thrashing.
- Input-feasibility fallback keeps the AI productive when its preferred line is short on inputs.
- Calibration sweep (1000g seed 42 + 4-seed sweep): all 7 roles still in [12 – 18 %] win rate. If Manufacturer or Educator moves more than ±2 pp, retune.
- Full test suite green at the new baseline count (429 + new tests).
- `RELEASE_NOTES.md` Unreleased section gets a new `### codex/ai-manufacturer-product-mix-2026-05-26` block.

## Out of scope

- Patents-as-product-line bonuses (separate feature).
- Multi-line concurrent production (the engine still produces one chosen line per season).
- AI behaviour for other islands (Educator AI approval queue is a separate brief; AI Banker is being addressed by the wholesale-funding brief).
