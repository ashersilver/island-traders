import pytest
from island_traders.engine.production import ProductionEngine, InsufficientInputsError
from island_traders.engine.events import EventResult
from island_traders.models.profession import Profession
from island_traders.models.resource import ResourceType


def _give_farmer_inputs(farmer):
    farmer.receive_resources(ResourceType.FARM_MACHINERY, 1)
    farmer.receive_resources(ResourceType.OIL, 1)


def test_farmer_produces_with_inputs(farmer, normal_event):
    _give_farmer_inputs(farmer)
    engine = ProductionEngine()
    produced = engine.produce(farmer, normal_event, season_name="Spring")
    assert ResourceType.GRAIN in produced
    assert ResourceType.PRODUCE in produced
    assert ResourceType.FISH in produced
    assert farmer.inventory.get(ResourceType.FARM_MACHINERY) == 0
    assert farmer.inventory.get(ResourceType.OIL) == 0


def test_farmer_cannot_produce_without_inputs(farmer, normal_event):
    engine = ProductionEngine()
    with pytest.raises(InsufficientInputsError):
        engine.produce(farmer, normal_event)


def test_farmer_seasonal_outputs_differ(farmer, normal_event):
    """Autumn harvest should produce more Grain than Spring planting."""
    engine = ProductionEngine()
    _give_farmer_inputs(farmer)
    spring = engine.produce(farmer, normal_event, season_name="Spring")
    _give_farmer_inputs(farmer)
    autumn = engine.produce(farmer, normal_event, season_name="Autumn")
    assert autumn.get(ResourceType.GRAIN, 0) > spring.get(ResourceType.GRAIN, 0)


def test_outage_blocks_production(farmer, outage_event):
    _give_farmer_inputs(farmer)
    engine = ProductionEngine()
    produced = engine.produce(farmer, outage_event)
    assert produced == {}
    assert farmer.inventory.get(ResourceType.FARM_MACHINERY) == 1
    assert farmer.inventory.get(ResourceType.OIL) == 1


def test_banker_produces_finance_commodity(banker, normal_event):
    """2026-06-02 rebalance: Banker reinstated as a Finance producer (modest
    output so it isn't structurally unwinnable in sim while AI lending is
    improved).  Banking ALSO earns from loan interest."""
    engine = ProductionEngine()
    produced = engine.produce(banker, normal_event)
    assert ResourceType.FINANCE in produced
    assert produced[ResourceType.FINANCE] > 0


def test_educator_needs_reagents_and_finance(normal_event):
    """2026-06-02 rebalance: Educator consumes both Reagents and Finance
    as production inputs (Finance creates demand for Banker output)."""
    from island_traders.models.player import Player
    from island_traders.models.role import ROLES

    educator = Player(10, "Professor", [ROLES["Educator"]], 100.0, is_human=False)
    educator.receive_resources(ResourceType.REAGENTS, 1)
    educator.receive_resources(ResourceType.FINANCE, 1)
    produced = ProductionEngine().produce(educator, normal_event)

    assert ResourceType.EXPERTISE in produced


def test_doctor_produces_reagents_from_oil_and_ore(normal_event):
    from island_traders.models.player import Player
    from island_traders.models.role import ROLES

    doctor = Player(11, "Doctor", [ROLES["Doctor"]], 100.0, is_human=False)
    doctor.receive_resources(ResourceType.EXPERTISE, 1)
    # Medical Sciences now makes its own Reagents from Oil + Ore (2026-06-02).
    doctor.receive_resources(ResourceType.OIL, 1)
    doctor.receive_resources(ResourceType.ORE, 1)
    produced = ProductionEngine().produce(doctor, normal_event)

    assert ResourceType.HEALTH_SERVICES in produced
    assert ResourceType.REAGENTS in produced   # produced in-house now


def test_miner_produces_larger_ore_and_oil_quantities(normal_event):
    from island_traders.models.player import Player
    from island_traders.models.role import ROLES

    miner = Player(12, "Miner", [ROLES["Miner"]], 100.0, is_human=False)
    miner.receive_resources(ResourceType.OIL, 1)
    miner.receive_resources(ResourceType.FREIGHT, 1)
    miner.receive_resources(ResourceType.MINING_EQUIPMENT, 1)

    produced = ProductionEngine().produce(miner, normal_event, season_name="Spring")

    assert produced[ResourceType.ORE] == 40
    assert produced[ResourceType.METAL] == 20
    assert produced[ResourceType.OIL] == 40


def test_banker_production_is_safe(banker, normal_event):
    """produce() on a Banker with no inputs should not raise — the
    InsufficientInputsError path is guarded by checking PRODUCTION_INPUTS.
    2026-06-02: Banker now produces Finance (no inputs required)."""
    engine = ProductionEngine()
    produced = engine.produce(banker, normal_event)
    # Finance production requires no inputs so the call must succeed.
    assert produced is not None


def test_bumper_harvest_increases_yield(farmer, bumper_event):
    _give_farmer_inputs(farmer)
    engine = ProductionEngine()
    # Spring: base Produce=24, yield_modifier=1.8, bonus=2 → int(24*1.8)+2 = 43+2 = 45
    produced = engine.produce(farmer, bumper_event, season_name="Spring")
    assert produced.get(ResourceType.PRODUCE, 0) == 45


def test_production_preview_does_not_mutate(farmer, normal_event):
    _give_farmer_inputs(farmer)
    engine = ProductionEngine()
    before_dollops = farmer.dollops
    before_equip = farmer.inventory.get(ResourceType.REAGENTS)
    before_oil = farmer.inventory.get(ResourceType.OIL)
    engine.production_preview(farmer, normal_event)
    assert farmer.dollops == before_dollops
    assert farmer.inventory.get(ResourceType.REAGENTS) == before_equip
    assert farmer.inventory.get(ResourceType.OIL) == before_oil


def test_can_produce_returns_missing(farmer, normal_event):
    engine = ProductionEngine()
    can, missing = engine.can_produce(farmer, normal_event)
    assert not can
    assert ResourceType.FARM_MACHINERY in missing or ResourceType.OIL in missing


def test_manufacturer_product_lines(manufacturer, normal_event):
    """Each product line should produce a distinct resource."""
    from island_traders.constants import MANUFACTURER_PRODUCT_LINES
    engine = ProductionEngine()
    for line_key, line in MANUFACTURER_PRODUCT_LINES.items():
        # Give inputs
        for r_str, qty in line["inputs"].items():
            manufacturer.receive_resources(ResourceType(r_str), qty)
        produced = engine.produce(manufacturer, normal_event, season_name="Spring", product_line=line_key)
        assert ResourceType(line["output"]) in produced, f"Line {line_key} produced nothing"


def test_manufacturer_product_lines_require_metal_not_ore():
    from island_traders.constants import MANUFACTURER_PRODUCT_LINES

    assert all("Metal" in line["inputs"] for line in MANUFACTURER_PRODUCT_LINES.values())
    assert all("Ore" not in line["inputs"] for line in MANUFACTURER_PRODUCT_LINES.values())


def test_manufacturer_without_line_uses_default(manufacturer, normal_event):
    """If no product_line supplied, defaults to first line (FarmMachinery)."""
    from island_traders.constants import MANUFACTURER_PRODUCT_LINES
    first_line = next(iter(MANUFACTURER_PRODUCT_LINES.values()))
    for r_str, qty in first_line["inputs"].items():
        manufacturer.receive_resources(ResourceType(r_str), qty)
    engine = ProductionEngine()
    produced = engine.produce(manufacturer, normal_event, season_name="Spring")
    assert ResourceType(first_line["output"]) in produced


def test_manufacturer_freight_surcharge_uses_board_scale_quantity():
    """Freight should not balloon when output quantities are simulation-scaled."""
    from island_traders.constants import (
        MANUFACTURER_PRODUCT_LINES,
        PRODUCER_PRODUCTIVITY_MULTIPLIER,
    )

    line = MANUFACTURER_PRODUCT_LINES["MiningEquipment"]
    board_scale_qty = round(line["qty"] / PRODUCER_PRODUCTIVITY_MULTIPLIER)
    engine = ProductionEngine()

    assert engine._freight_surcharge("MiningEquipment", line["qty"]) == (
        line["freight_per_unit"] * board_scale_qty
    )


def test_production_options_show_per_product_current_max(normal_event):
    from island_traders.models.player import Player
    from island_traders.models.role import ROLES

    farmer = Player(20, "Selective Farmer", [ROLES["Farmer"]], 100.0, is_human=True)
    farmer.add_capital("farmer.tractor")
    farmer.add_capital("farmer.fishing_boat")
    farmer.workforce.add_workers(1, training_level=1, profession=Profession.FARMER.value)
    farmer.workforce.add_workers(1, training_level=1, profession=Profession.FARMING_TECHNICIAN.value)
    farmer.workforce.add_workers(8, training_level=0, profession=Profession.UNSKILLED.value)
    farmer.receive_resources(ResourceType.OIL, 10)

    options = ProductionEngine().production_options(farmer, normal_event, season_name="Spring")
    by_output = {option["output"]: option for option in options}

    assert by_output[ResourceType.GRAIN]["max_qty"] == 24
    assert by_output[ResourceType.FISH]["max_qty"] == 24


def test_produce_product_makes_chosen_product_and_quantity_only(normal_event):
    from island_traders.models.player import Player
    from island_traders.models.role import ROLES

    farmer = Player(21, "Selective Farmer", [ROLES["Farmer"]], 100.0, is_human=True)
    farmer.add_capital("farmer.industrial_kitchen")
    farmer.workforce.add_workers(1, training_level=1, profession=Profession.FARMER.value)
    farmer.workforce.add_workers(1, training_level=1, profession=Profession.FARMING_TECHNICIAN.value)
    farmer.workforce.add_workers(8, training_level=0, profession=Profession.UNSKILLED.value)
    farmer.receive_resources(ResourceType.GRAIN, 10)
    farmer.receive_resources(ResourceType.PRODUCE, 10)
    farmer.receive_resources(ResourceType.MEAT, 10)

    produced = ProductionEngine().produce_product(
        farmer,
        normal_event,
        season_name="Spring",
        role_name="Farmer",
        output=ResourceType.FOOD,
        qty=10,
    )

    assert produced == {ResourceType.FOOD: 10}
    assert farmer.inventory.get(ResourceType.FOOD) == 10
    assert farmer.inventory.get(ResourceType.GRAIN) == 0
    assert farmer.inventory.get(ResourceType.PRODUCE) == 0
    assert farmer.inventory.get(ResourceType.MEAT) == 0


def test_packaged_food_requires_kitchen_and_can_use_meat_as_protein(normal_event):
    from island_traders.models.player import Player
    from island_traders.models.role import ROLES

    farmer = Player(211, "Kitchen Farmer", [ROLES["Farmer"]], 100.0, is_human=True)
    farmer.workforce.add_workers(1, training_level=1, profession=Profession.FARMER.value)
    farmer.workforce.add_workers(1, training_level=1, profession=Profession.HORTICULTURALIST.value)
    farmer.workforce.add_workers(8, training_level=0, profession=Profession.UNSKILLED.value)
    farmer.receive_resources(ResourceType.GRAIN, 3)
    farmer.receive_resources(ResourceType.PRODUCE, 3)
    farmer.receive_resources(ResourceType.MEAT, 3)

    assert ResourceType.FOOD not in {
        option["output"]
        for option in ProductionEngine().production_options(farmer, normal_event, "Spring")
    }

    farmer.add_capital("farmer.industrial_kitchen")
    produced = ProductionEngine().produce_product(
        farmer,
        normal_event,
        season_name="Spring",
        role_name="Farmer",
        output=ResourceType.FOOD,
        qty=3,
    )

    assert produced == {ResourceType.FOOD: 3}
    assert farmer.inventory.get(ResourceType.MEAT) == 0


def test_meat_line_consumes_four_grain_per_unit(normal_event):
    from island_traders.models.player import Player
    from island_traders.models.role import ROLES

    farmer = Player(212, "Livestock Farmer", [ROLES["Farmer"]], 100.0, is_human=True)
    farmer.add_capital("farmer.livestock_barn")
    farmer.workforce.add_workers(1, training_level=1, profession=Profession.FARMER.value)
    farmer.workforce.add_workers(1, training_level=1, profession=Profession.VETERINARIAN.value)
    farmer.workforce.add_workers(8, profession=Profession.UNSKILLED.value)
    farmer.receive_resources(ResourceType.GRAIN, 8)

    produced = ProductionEngine().produce_product(
        farmer, normal_event, "Spring", "Farmer", ResourceType.MEAT, 2
    )

    assert produced == {ResourceType.MEAT: 2}
    assert farmer.inventory.get(ResourceType.GRAIN) == 0


def test_late_season_farmer_specialists_protect_produce_and_meat(normal_event):
    from island_traders.models.player import Player
    from island_traders.models.role import ROLES

    bare = Player(213, "Bare Farm", [ROLES["Farmer"]], 100.0, is_human=True)
    bare.receive_resources(ResourceType.FARM_MACHINERY, 1)
    bare.receive_resources(ResourceType.OIL, 1)
    bare.add_capital("farmer.livestock_barn")
    bare.workforce.add_workers(1, training_level=1, profession=Profession.FARMER.value)
    bare.workforce.add_workers(1, training_level=1, profession=Profession.FARMING_TECHNICIAN.value)
    bare.workforce.add_workers(2, training_level=1, profession=Profession.MECHANIC.value)
    bare.workforce.add_workers(8, profession=Profession.UNSKILLED.value)
    bare.receive_resources(ResourceType.GRAIN, 40)

    staffed = Player(214, "Staffed Farm", [ROLES["Farmer"]], 100.0, is_human=True)
    staffed.receive_resources(ResourceType.FARM_MACHINERY, 1)
    staffed.receive_resources(ResourceType.OIL, 1)
    staffed.add_capital("farmer.livestock_barn")
    staffed.workforce.add_workers(1, training_level=1, profession=Profession.FARMER.value)
    staffed.workforce.add_workers(1, training_level=1, profession=Profession.FARMING_TECHNICIAN.value)
    staffed.workforce.add_workers(1, training_level=1, profession=Profession.HORTICULTURALIST.value)
    staffed.workforce.add_workers(1, training_level=1, profession=Profession.VETERINARIAN.value)
    staffed.workforce.add_workers(8, profession=Profession.UNSKILLED.value)
    staffed.receive_resources(ResourceType.GRAIN, 40)

    engine = ProductionEngine()
    bare_preview = engine.production_preview(bare, normal_event, "Autumn")
    staffed_preview = engine.production_preview(staffed, normal_event, "Autumn")
    bare_meat = next(
        option for option in engine.production_options(bare, normal_event, "Autumn")
        if option["output"] == ResourceType.MEAT
    )
    staffed_meat = next(
        option for option in engine.production_options(staffed, normal_event, "Autumn")
        if option["output"] == ResourceType.MEAT
    )

    assert bare_preview["outputs"][ResourceType.PRODUCE] == 54
    assert staffed_preview["outputs"][ResourceType.PRODUCE] == 72
    assert bare_meat["max_qty"] == int(staffed_meat["max_qty"] * 0.75)


def test_enhanced_crusher_smelter_increases_metal_capacity_and_reduces_oil(normal_event):
    from island_traders.models.player import Player
    from island_traders.models.role import ROLES

    miner = Player(22, "Selective Miner", [ROLES["Miner"]], 100.0, is_human=True)
    miner.add_capital("miner.crusher")
    miner.add_capital("miner.enhanced_crusher_smelter")
    miner.workforce.add_workers(1, training_level=1, profession=Profession.MINER.value)
    miner.workforce.add_workers(4, training_level=1, profession=Profession.MINING_TECHNICIAN.value)
    miner.workforce.add_workers(10, training_level=0, profession=Profession.UNSKILLED.value)
    miner.receive_resources(ResourceType.ORE, 20)
    miner.receive_resources(ResourceType.OIL, 20)

    engine = ProductionEngine()
    options = engine.production_options(miner, normal_event, season_name="Spring")
    metal_option = next(option for option in options if option["output"] == ResourceType.METAL)

    assert metal_option["preview_qty"] == 60
    assert metal_option["capacity_limit"] >= 40

    produced = engine.produce_product(
        miner,
        normal_event,
        season_name="Spring",
        role_name="Miner",
        output=ResourceType.METAL,
        qty=40,
    )

    assert produced == {ResourceType.METAL: 40}
    assert miner.inventory.get(ResourceType.ORE) == 16
    assert miner.inventory.get(ResourceType.OIL) == 19
