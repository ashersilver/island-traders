from island_traders.constants import (
    BASE_PRICES, BASE_PRODUCTION, STARTING_INVENTORY, PRODUCTION_INPUTS,
    FARMER_SEASONAL_CONVERSION, MANUFACTURER_PRODUCT_LINES,
    OUTPUT_PRODUCTION_INPUTS,
)
from island_traders.constants_capacity import CAPITAL_CATALOGUE


def test_oil_starting_buffers_reflect_role_demand():
    """Oil-consuming islands start with at least 2 seasons of Oil.

    Miner carries a larger Oil buffer (8) per economy-lifecycle Phase A.
    """
    assert STARTING_INVENTORY["Farmer"]["Oil"] == 2
    assert STARTING_INVENTORY["Miner"]["Oil"] == 8
    assert STARTING_INVENTORY["Transporter"]["Oil"] == 4
    assert STARTING_INVENTORY["Manufacturer"]["Oil"] == 2
    assert STARTING_INVENTORY["Miner"]["Metal"] == 2
    assert STARTING_INVENTORY["Manufacturer"]["Metal"] == 4


def test_miner_oil_is_reduced_and_metal_is_available():
    assert BASE_PRODUCTION["Miner"]["Oil"] == 40
    assert BASE_PRODUCTION["Miner"]["Metal"] == 20


def test_equipment_is_durable_capital_not_consumed_inputs():
    for season in FARMER_SEASONAL_CONVERSION.values():
        assert "FarmMachinery" not in season["inputs"]
    assert "MiningEquipment" not in PRODUCTION_INPUTS["Miner"]


def test_tradeable_equipment_prices_match_installed_capital_value():
    catalogue = {item.item_id: item for item in CAPITAL_CATALOGUE}
    assert BASE_PRICES["FarmMachinery"] == catalogue["farmer.tractor"].cost
    assert BASE_PRICES["MiningEquipment"] == catalogue["miner.excavator"].cost


def test_metal_is_smelting_output_from_ore_and_oil():
    assert OUTPUT_PRODUCTION_INPUTS["Miner"]["Metal"] == {"Ore": 2, "Oil": 1}


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
