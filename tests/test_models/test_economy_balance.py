from island_traders.constants import BASE_PRODUCTION, STARTING_INVENTORY


def test_oil_starting_buffers_reflect_role_demand():
    assert STARTING_INVENTORY["Farmer"]["Oil"] == 2
    assert STARTING_INVENTORY["Miner"]["Oil"] == 4
    assert STARTING_INVENTORY["Transporter"]["Oil"] == 3
    assert STARTING_INVENTORY["Manufacturer"]["Oil"] == 2


def test_miner_has_higher_oil_production_capacity():
    assert BASE_PRODUCTION["Miner"]["Oil"] == 200  # 20 * PRODUCER_PRODUCTIVITY_MULTIPLIER (10)


def test_transporter_uses_fish_not_food_for_provisions():
    assert STARTING_INVENTORY["Transporter"]["Fish"] == 1
    assert "Food" not in STARTING_INVENTORY["Transporter"]
