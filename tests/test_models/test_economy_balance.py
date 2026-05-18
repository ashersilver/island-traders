from island_traders.constants import (
    BASE_PRODUCTION, STARTING_INVENTORY, PRODUCTION_INPUTS,
    FARMER_SEASONAL_CONVERSION, MANUFACTURER_PRODUCT_LINES,
)


def test_oil_starting_buffers_reflect_role_demand():
    """Oil-consuming islands start with at least 2 seasons of Oil."""
    assert STARTING_INVENTORY["Farmer"]["Oil"] == 2
    assert STARTING_INVENTORY["Miner"]["Oil"] == 4
    assert STARTING_INVENTORY["Transporter"]["Oil"] == 4
    assert STARTING_INVENTORY["Manufacturer"]["Oil"] == 2
    assert STARTING_INVENTORY["Miner"]["Metal"] == 2
    assert STARTING_INVENTORY["Manufacturer"]["Metal"] == 4


def test_miner_oil_is_reduced_and_metal_is_available():
    assert BASE_PRODUCTION["Miner"]["Oil"] == 80
    assert BASE_PRODUCTION["Miner"]["Metal"] == 40


def test_transporter_uses_food_not_fish_for_provisions():
    assert STARTING_INVENTORY["Transporter"]["Food"] == 2
    assert "Fish" not in STARTING_INVENTORY["Transporter"]


def test_every_island_starts_with_at_least_two_seasons_of_inputs():
    """Each island must have enough starting inputs to produce for 2 seasons
    without buying anything, giving players breathing room to establish trade."""
    roles_inputs = {
        "Farmer": FARMER_SEASONAL_CONVERSION["Spring"]["inputs"],
        "Miner": PRODUCTION_INPUTS["Miner"],
        "Transporter": PRODUCTION_INPUTS["Transporter"],
        "Educator": PRODUCTION_INPUTS["Educator"],
        "Banker": PRODUCTION_INPUTS["Banker"],
        "Doctor": PRODUCTION_INPUTS["Doctor"],
        "Manufacturer": MANUFACTURER_PRODUCT_LINES["FarmMachinery"]["inputs"],
    }
    for role, inputs in roles_inputs.items():
        inv = STARTING_INVENTORY[role]
        for resource, qty_per_season in inputs.items():
            have = inv.get(resource, 0)
            assert have >= qty_per_season * 2, (
                f"{role} starts with {have} {resource} but needs "
                f"{qty_per_season * 2} for 2 seasons ({qty_per_season}/season)"
            )
