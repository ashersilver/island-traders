"""Static supply-chain reachability checks (2026-06-02).

These catch a whole class of "silent bottleneck" bugs at import/test time
instead of in playtest:

  * a resource is *required* as a production input but **no island produces it**
    (would have caught Reagents-with-no-producer);
  * a resource has a capacity recipe (the panel says it's producible) but the
    **active producer never actually makes it** (would have caught Courses,
    which lived in PRODUCTION_RECIPES but was missing from BASE_PRODUCTION and
    so could never be replenished).

The simulation only scores win-rate/wealth, so a broken chain shifts results
silently rather than failing — these tests close that gap cheaply.
"""
from __future__ import annotations

from island_traders.constants import (
    BASE_PRODUCTION,
    PRODUCTION_INPUTS,
    FARMER_SEASONAL_CONVERSION,
    MANUFACTURER_PRODUCT_LINES,
    KITCHEN_SPECS,
)
from island_traders.constants_capacity import CAPITAL_CATALOGUE, PRODUCTION_RECIPES

# "Protein" is a meta-ingredient in kitchen recipes: satisfied by Fish OR Meat.
PROTEIN_SOURCES = {"Fish", "Meat"}

# Outputs that have a capacity recipe but are intentionally NOT made by the
# active production model.  Each entry must be justified — the point of the
# allowlist is to let the test catch *new* unproduced outputs (regressions)
# while documenting the known, accepted exceptions.
KNOWN_NONPRODUCED_RECIPE_OUTPUTS = {
    # Service output: the Banker SELLS insurance via the insurance action; it is
    # not a tradeable commodity produced each season.  Permanent exception.
    "InsurancePolicies",
}


def _active_outputs() -> set[str]:
    """Every resource an island can actually PRODUCE under the active model
    (BASE_PRODUCTION + Farmer seasonal table + Manufacturer lines + kitchens)."""
    produced: set[str] = set()
    for outputs in BASE_PRODUCTION.values():
        produced.update(outputs.keys())
    for season in FARMER_SEASONAL_CONVERSION.values():
        produced.update(season["outputs"].keys())
    for line in MANUFACTURER_PRODUCT_LINES.values():
        produced.add(line["output"])
    # Farmer livestock is an explicit product option gated by Livestock Barn
    # capacity and Grain feedstock, not by the seasonal crop/fishing table.
    produced.add("Meat")
    # Kitchens (any island) convert raw ingredients into Food.
    produced.add("Food")
    return produced


def _required_inputs() -> dict[str, set[str]]:
    """Map each required-input resource -> the set of consumers that need it,
    across every consumption path (production inputs, Farmer/Manufacturer/kitchen
    recipes, and the per-unit capacity recipes)."""
    required: dict[str, set[str]] = {}

    def add(resource: str, consumer: str) -> None:
        required.setdefault(resource, set()).add(consumer)

    for role, inputs in PRODUCTION_INPUTS.items():
        for r in inputs:
            add(r, f"PRODUCTION_INPUTS[{role}]")
    for season, data in FARMER_SEASONAL_CONVERSION.items():
        for r in data["inputs"]:
            add(r, f"Farmer/{season}")
    for line, data in MANUFACTURER_PRODUCT_LINES.items():
        for r in data["inputs"]:
            add(r, f"Manufacturer/{line}")
    for item_id, spec in KITCHEN_SPECS.items():
        for r in spec["recipe"]:
            add(r, f"Kitchen/{item_id}")
    for recipe in PRODUCTION_RECIPES:
        for r in recipe.inputs:
            add(r, f"Recipe[{recipe.role}->{recipe.output}]")
    return required


def test_every_required_input_has_a_producer():
    """No island may depend on an input that nothing in the game produces."""
    produced = _active_outputs()
    required = _required_inputs()
    orphans = {}
    for resource, consumers in required.items():
        if resource == "Protein":
            # Meta-ingredient: satisfied if Fish or Meat is produced.
            if not (PROTEIN_SOURCES & produced):
                orphans[resource] = consumers
            continue
        if resource not in produced:
            orphans[resource] = consumers
    assert not orphans, (
        "These required inputs have NO producer (supply-chain dead end): "
        + "; ".join(f"{r} (needed by {sorted(c)})" for r, c in orphans.items())
    )


def test_every_capacity_recipe_output_is_actually_produced():
    """If a resource has a capacity recipe (so the panel lists it as
    producible), the active producer must really make it — otherwise the panel
    lies and the resource silently depletes (the Courses bug)."""
    produced = _active_outputs()
    missing = sorted({
        recipe.output
        for recipe in PRODUCTION_RECIPES
        if recipe.output not in produced
        and recipe.output not in KNOWN_NONPRODUCED_RECIPE_OUTPUTS
    })
    assert not missing, (
        "These outputs have a capacity recipe but are never produced by the "
        f"active model (BASE_PRODUCTION/Farmer/Manufacturer/kitchen): {missing}"
    )


def test_every_manufacturer_product_line_has_capacity_recipe():
    """Decision Hints read from PRODUCTION_RECIPES, so every live
    Manufacturer product line needs a matching capacity recipe."""
    recipe_outputs = {
        recipe.output
        for recipe in PRODUCTION_RECIPES
        if recipe.role == "Manufacturer"
    }
    missing = sorted(
        line["output"]
        for line in MANUFACTURER_PRODUCT_LINES.values()
        if line["output"] not in recipe_outputs
    )
    assert not missing, (
        "Manufacturer product lines missing capacity recipes: "
        f"{missing}"
    )


def test_every_manufacturer_product_line_has_capital_path():
    """A manufacturer line with a recipe but no capital capacity still shows
    up as blocked forever in Decision Hints."""
    missing = []
    for line in MANUFACTURER_PRODUCT_LINES.values():
        output = line["output"]
        has_path = any(
            item.role == "Manufacturer"
            and (
                item.effects.get("capacity", {}).get(output, 0) > 0
                or output in item.effects.get("unlocks_lines", [])
            )
            for item in CAPITAL_CATALOGUE
        )
        if not has_path:
            missing.append(output)

    assert not missing, (
        "Manufacturer product lines missing capital capacity/unlock path: "
        f"{sorted(missing)}"
    )


def test_protein_sources_exist():
    """Kitchens need a protein; at least one protein resource must be produced."""
    produced = _active_outputs()
    assert PROTEIN_SOURCES & produced, "No protein (Fish/Meat) is produced anywhere"
