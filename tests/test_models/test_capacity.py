"""Tests for the production capacity data model + catalogue + recipes."""
from __future__ import annotations

from island_traders.constants_capacity import (
    CAPITAL_CATALOGUE, PRODUCTION_RECIPES, MANDATORY_MINIMUM_INVESTMENT,
)
from island_traders.models.capacity import (
    items_for_role, recipes_for_role, recipe_for, find_item,
    equipment_capacity, workforce_capacity, input_capacity, compute_capacity,
)
from island_traders.models.profession import WorkerBand


ROLES = ["Farmer", "Miner", "Transporter", "Educator",
         "Banker", "Manufacturer", "Doctor"]


def test_every_role_has_3_to_5_capital_items():
    for role in ROLES:
        items = items_for_role(CAPITAL_CATALOGUE, role)
        assert 3 <= len(items) <= 6, f"{role} has {len(items)} items (expected 3–5)"


def test_every_role_has_at_least_two_recipes():
    for role in ROLES:
        recipes = recipes_for_role(PRODUCTION_RECIPES, role)
        assert len(recipes) >= 2, f"{role} has only {len(recipes)} recipes; need ≥ 2 outputs"


def test_capital_item_ids_unique():
    ids = [it.item_id for it in CAPITAL_CATALOGUE]
    assert len(ids) == len(set(ids)), "duplicate capital item ids"


def test_recipe_pairs_unique():
    pairs = [(r.role, r.output) for r in PRODUCTION_RECIPES]
    assert len(pairs) == len(set(pairs))


def test_mandatory_minimums_reference_real_items():
    for role, item_ids in MANDATORY_MINIMUM_INVESTMENT.items():
        assert role in ROLES
        for item_id in item_ids:
            assert find_item(CAPITAL_CATALOGUE, item_id) is not None, \
                f"mandatory item {item_id} not in CAPITAL_CATALOGUE"


def test_equipment_capacity_sums_owned_items():
    # Owning 1 Tractor + 1 Fishing Boat → 100 Food, 40 Fish capacity
    owned = {"farmer.tractor": 1, "farmer.fishing_boat": 1}
    assert equipment_capacity(CAPITAL_CATALOGUE, owned, "Food") == 100
    assert equipment_capacity(CAPITAL_CATALOGUE, owned, "Fish") == 40

    # 2 Tractors → 200 Food
    assert equipment_capacity(CAPITAL_CATALOGUE, {"farmer.tractor": 2}, "Food") == 200


def test_workforce_capacity_uses_binding_band():
    food_recipe = recipe_for(PRODUCTION_RECIPES, "Farmer", "Food")
    # Plenty of managers, no technicians → technician is the binding constraint
    available = {WorkerBand.MANAGER: 5, WorkerBand.TECHNICIAN: 1, WorkerBand.WORKER: 5}
    cap = workforce_capacity(food_recipe, available)
    # Technician = 1 / 0.04 = 25 units max
    assert cap == 1 / 0.04


def test_input_capacity_uses_binding_resource():
    food_recipe = recipe_for(PRODUCTION_RECIPES, "Farmer", "Food")
    # 6 Oil supports 30 Food (6/0.2); Fish is no longer a farm input.
    on_hand = {"Oil": 6, "Fish": 1}
    assert input_capacity(food_recipe, on_hand) == 30


def test_compute_capacity_returns_min_of_three():
    food_recipe = recipe_for(PRODUCTION_RECIPES, "Farmer", "Food")
    result = compute_capacity(
        recipe=food_recipe,
        catalogue=CAPITAL_CATALOGUE,
        owned={"farmer.tractor": 1},                 # 100 equipment cap
        workforce={WorkerBand.MANAGER: 20,
                   WorkerBand.TECHNICIAN: 20,
                   WorkerBand.WORKER: 20},           # generous
        on_hand={"Oil": 30, "Fish": 30},             # generous
    )
    assert result.max_producible == 100
    assert result.binding_constraint == "equipment"


def test_compute_capacity_identifies_input_binding():
    food_recipe = recipe_for(PRODUCTION_RECIPES, "Farmer", "Food")
    result = compute_capacity(
        recipe=food_recipe,
        catalogue=CAPITAL_CATALOGUE,
        owned={"farmer.tractor": 10},                # 1000 equipment cap
        workforce={WorkerBand.MANAGER: 50,
                   WorkerBand.TECHNICIAN: 50,
                   WorkerBand.WORKER: 50},
        on_hand={"Oil": 6, "Fish": 30},              # Oil binding (30 Food max)
    )
    assert result.binding_constraint == "inputs"
    assert result.max_producible == 30


def test_manufacturer_opening_equipment_provides_capacity():
    owned = {
        "manufacturer.foundry": 1,
        "manufacturer.assembly_line": 1,
        "manufacturer.precision_workshop": 1,
        "manufacturer.shipyard": 1,
    }

    assert equipment_capacity(CAPITAL_CATALOGUE, owned, "FarmMachinery") > 0
    assert equipment_capacity(CAPITAL_CATALOGUE, owned, "MiningEquipment") > 0
    assert equipment_capacity(CAPITAL_CATALOGUE, owned, "LaboratoryEquipment") > 0
    assert equipment_capacity(CAPITAL_CATALOGUE, owned, "MedicalDevices") > 0
    assert equipment_capacity(CAPITAL_CATALOGUE, owned, "TransportEquipment") > 0


def test_transporter_uses_fish_as_provisions():
    freight_recipe = recipe_for(PRODUCTION_RECIPES, "Transporter", "Freight")
    seats_recipe = recipe_for(PRODUCTION_RECIPES, "Transporter", "PassengerSeats")

    assert "Fish" in freight_recipe.inputs
    assert "Food" not in freight_recipe.inputs
    assert "Fish" in seats_recipe.inputs
    assert "Food" not in seats_recipe.inputs
