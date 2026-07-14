import pytest
from island_traders.engine.production import InsufficientInputsError, ProductionEngine
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
    assert farmer.capital_count("farmer.tractor") == 1
    assert farmer.inventory.get(ResourceType.FARM_MACHINERY) == 0
    assert farmer.inventory.get(ResourceType.OIL) == 0


def test_farmer_cannot_produce_without_inputs(farmer, normal_event):
    engine = ProductionEngine()
    with pytest.raises(InsufficientInputsError):
        engine.produce(farmer, normal_event)


def test_farmer_production_no_longer_requires_farm_machinery_stock(farmer, normal_event):
    farmer.receive_resources(ResourceType.OIL, 1)

    produced = ProductionEngine().produce(farmer, normal_event, season_name="Spring")

    assert produced[ResourceType.GRAIN] > 0
    assert produced[ResourceType.PRODUCE] > 0
    assert produced[ResourceType.FISH] > 0
    assert farmer.inventory.get(ResourceType.FARM_MACHINERY) == 0
    assert farmer.capital_count("farmer.tractor") == 0


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
    assert farmer.capital_count("farmer.tractor") == 1
    assert farmer.inventory.get(ResourceType.FARM_MACHINERY) == 0
    assert farmer.inventory.get(ResourceType.OIL) == 1


def test_banker_produces_finance_commodity(banker, normal_event):
    """2026-06-02 rebalance: Banker reinstated as a Finance producer (modest
    output so it isn't structurally unwinnable in sim while AI lending is
    improved).  Banking ALSO earns from loan interest."""
    engine = ProductionEngine()
    produced = engine.produce(banker, normal_event)
    assert ResourceType.FINANCE in produced
    assert produced[ResourceType.FINANCE] > 0


def test_educator_expertise_runs_with_lab_step_inputs(normal_event):
    """Generic Education now pays lab consumables only once it reaches the
    10-unit step; Patents remain separately Reagents-gated."""
    from island_traders.models.player import Player
    from island_traders.models.role import ROLES

    educator = Player(10, "Professor", [ROLES["Educator"]], 100.0, is_human=False)
    educator.receive_resources(ResourceType.REAGENTS, 1)
    educator.receive_resources(ResourceType.OIL, 1)
    produced = ProductionEngine().produce(educator, normal_event)

    assert ResourceType.EXPERTISE in produced
    assert ResourceType.PATENTS not in produced
    assert educator.inventory.get(ResourceType.REAGENTS) == 0
    assert educator.inventory.get(ResourceType.OIL) == 0


def test_doctor_produces_reagents_from_oil_and_ore(normal_event):
    from island_traders.models.player import Player
    from island_traders.models.role import ROLES

    doctor = Player(11, "Doctor", [ROLES["Doctor"]], 100.0, is_human=False)
    doctor.receive_resources(ResourceType.EXPERTISE, 1)
    # Medical Sciences now makes its own Reagents from Oil + Ore (2026-06-02).
    doctor.receive_resources(ResourceType.OIL, 1)
    doctor.receive_resources(ResourceType.ORE, 1)
    produced = ProductionEngine().produce(doctor, normal_event)

    assert ResourceType.MEDICAL_SUPPLIES in produced
    assert ResourceType.REAGENTS in produced   # produced in-house now


def test_miner_produces_larger_ore_and_oil_quantities(normal_event):
    from island_traders.models.player import Player
    from island_traders.models.role import ROLES

    miner = Player(12, "Miner", [ROLES["Miner"]], 100.0, is_human=False)
    miner.receive_resources(ResourceType.ORE, 2)
    miner.receive_resources(ResourceType.OIL, 2)
    miner.receive_resources(ResourceType.FREIGHT, 1)
    miner.receive_resources(ResourceType.MINING_EQUIPMENT, 1)

    produced = ProductionEngine().produce(miner, normal_event, season_name="Spring")

    assert produced[ResourceType.ORE] == 40
    assert produced[ResourceType.METAL] == 20
    assert produced[ResourceType.OIL] == 45
    assert miner.inventory.get(ResourceType.ORE) == 40
    assert miner.inventory.get(ResourceType.OIL) == 45
    assert miner.capital_count("miner.excavator") == 1


def test_miner_skips_metal_without_starting_ore_for_smelting(normal_event):
    from island_traders.models.player import Player
    from island_traders.models.role import ROLES

    miner = Player(13, "Miner", [ROLES["Miner"]], 100.0, is_human=False)
    miner.receive_resources(ResourceType.OIL, 2)
    miner.receive_resources(ResourceType.FREIGHT, 1)

    produced = ProductionEngine().produce(miner, normal_event, season_name="Spring")

    assert produced[ResourceType.ORE] == 40
    assert ResourceType.METAL not in produced
    assert produced[ResourceType.OIL] == 45


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
    board_scale_qty = max(1, round(line["qty"] / PRODUCER_PRODUCTIVITY_MULTIPLIER))
    engine = ProductionEngine()

    assert engine._freight_surcharge("MiningEquipment", line["qty"]) == (
        line["freight_per_unit"] * board_scale_qty
    )


def test_manufacturer_goods_and_transport_equipment_are_production_options(manufacturer, normal_event):
    manufacturer.add_capital("manufacturer.assembly_line")
    manufacturer.add_capital("manufacturer.shipyard")
    manufacturer.workforce.add_workers(1, training_level=1, profession=Profession.ENGINEER.value)
    manufacturer.workforce.add_workers(2, training_level=1, profession=Profession.ASSEMBLY_WORKER.value)
    manufacturer.receive_resources(ResourceType.METAL, 20)
    manufacturer.receive_resources(ResourceType.OIL, 20)
    manufacturer.receive_resources(ResourceType.FREIGHT, 20)

    options = ProductionEngine().production_options(
        manufacturer,
        normal_event,
        season_name="Spring",
    )
    by_line = {option["product_line"]: option for option in options}

    assert by_line["Goods"]["output"] == ResourceType.GOODS
    assert by_line["Goods"]["max_qty"] > 0
    assert by_line["TransportEquipment"]["output"] == ResourceType.TRANSPORT_EQUIPMENT
    assert by_line["TransportEquipment"]["max_qty"] > 0


def test_manufacturer_durable_output_cap_and_own_capacity_bonus(manufacturer, normal_event):
    manufacturer.add_capital("manufacturer.assembly_line")
    manufacturer.add_capital("manufacturer.precision_workshop")
    manufacturer.add_capital("manufacturer.shipyard")
    manufacturer.workforce.add_workers(1, training_level=1, profession=Profession.ENGINEER.value)
    manufacturer.workforce.add_workers(6, training_level=1, profession=Profession.ASSEMBLY_WORKER.value)
    manufacturer.receive_resources(ResourceType.METAL, 100)
    manufacturer.receive_resources(ResourceType.OIL, 100)
    manufacturer.receive_resources(ResourceType.FREIGHT, 100)
    manufacturer.dollops = 1000.0

    engine = ProductionEngine()
    assert engine.manufacturer_durable_allowance(manufacturer) == 10
    manufacturer.manufacturer_durable_output_used = 8

    options = engine.production_options(manufacturer, normal_event, season_name="Spring")
    by_line = {option["product_line"]: option for option in options}

    assert by_line["TransportEquipment"]["max_qty"] == 2


def test_manufacturer_build_cost_limits_and_debits_output(manufacturer, normal_event):
    manufacturer.add_capital("manufacturer.assembly_line")
    manufacturer.workforce.add_workers(1, training_level=1, profession=Profession.ENGINEER.value)
    manufacturer.workforce.add_workers(2, training_level=1, profession=Profession.ASSEMBLY_WORKER.value)
    manufacturer.receive_resources(ResourceType.METAL, 100)
    manufacturer.receive_resources(ResourceType.OIL, 100)
    manufacturer.receive_resources(ResourceType.FREIGHT, 100)
    manufacturer.dollops = 7.0

    engine = ProductionEngine()
    options = engine.production_options(manufacturer, normal_event, season_name="Spring")
    farm = next(option for option in options if option["product_line"] == "FarmMachinery")
    assert farm["max_qty"] == 2

    produced = engine.produce_product(
        manufacturer,
        normal_event,
        "Spring",
        "Manufacturer",
        ResourceType.FARM_MACHINERY,
        qty=2,
        product_line="FarmMachinery",
    )

    assert produced == {ResourceType.FARM_MACHINERY: 2}
    assert manufacturer.dollops == 1.0
    assert manufacturer.manufacturer_durable_output_used == 2


def test_manufacturer_build_cost_hides_line_when_cash_short(manufacturer, normal_event):
    manufacturer.add_capital("manufacturer.assembly_line")
    manufacturer.workforce.add_workers(1, training_level=1, profession=Profession.ENGINEER.value)
    manufacturer.workforce.add_workers(2, training_level=1, profession=Profession.ASSEMBLY_WORKER.value)
    manufacturer.receive_resources(ResourceType.METAL, 100)
    manufacturer.receive_resources(ResourceType.OIL, 100)
    manufacturer.receive_resources(ResourceType.FREIGHT, 100)
    manufacturer.dollops = 2.0

    options = ProductionEngine().production_options(
        manufacturer, normal_event, season_name="Spring"
    )
    assert all(option["product_line"] != "FarmMachinery" for option in options)


def test_production_options_show_per_product_current_max(normal_event):
    from island_traders.models.player import Player
    from island_traders.models.role import ROLES

    farmer = Player(20, "Selective Farmer", [ROLES["Farmer"]], 100.0, is_human=True)
    farmer.add_capital("farmer.tractor")
    farmer.add_capital("farmer.fishing_boat")
    farmer.workforce.add_workers(1, training_level=1, profession=Profession.FARMER.value)
    farmer.workforce.add_workers(1, training_level=1, profession=Profession.MARINE_BIOLOGIST.value)
    farmer.workforce.add_workers(
        2, training_level=1, profession=Profession.FISH_PROCESSING_TECHNICIAN.value
    )
    farmer.workforce.add_workers(1, training_level=1, profession=Profession.FARMING_TECHNICIAN.value)
    farmer.workforce.add_workers(8, training_level=0, profession=Profession.UNSKILLED.value)
    farmer.receive_resources(ResourceType.OIL, 10)
    farmer.receive_resources(ResourceType.FARM_MACHINERY, 1)

    options = ProductionEngine().production_options(farmer, normal_event, season_name="Spring")
    by_output = {option["output"]: option for option in options}

    assert by_output[ResourceType.GRAIN]["max_qty"] == 24
    assert by_output[ResourceType.FISH]["max_qty"] == 24


def test_fish_yield_halves_without_marine_biologist(normal_event):
    from island_traders.models.player import Player
    from island_traders.models.role import ROLES

    staffed = Player(201, "Biology Boat", [ROLES["Farmer"]], 100.0, is_human=True)
    staffed.add_capital("farmer.fishing_boat")
    staffed.workforce.add_workers(1, training_level=1, profession=Profession.FARMER.value)
    staffed.workforce.add_workers(1, training_level=1, profession=Profession.MARINE_BIOLOGIST.value)
    staffed.workforce.add_workers(
        2, training_level=1, profession=Profession.FISH_PROCESSING_TECHNICIAN.value
    )
    staffed.workforce.add_workers(8, profession=Profession.UNSKILLED.value)
    staffed.receive_resources(ResourceType.OIL, 10)

    no_biologist = Player(202, "Guesswork Boat", [ROLES["Farmer"]], 100.0, is_human=True)
    no_biologist.add_capital("farmer.fishing_boat")
    no_biologist.workforce.add_workers(1, training_level=1, profession=Profession.FARMER.value)
    no_biologist.workforce.add_workers(
        2, training_level=1, profession=Profession.FISH_PROCESSING_TECHNICIAN.value
    )
    no_biologist.workforce.add_workers(8, profession=Profession.UNSKILLED.value)
    no_biologist.receive_resources(ResourceType.OIL, 10)

    engine = ProductionEngine()
    staffed_fish = next(
        option for option in engine.production_options(staffed, normal_event, "Spring")
        if option["output"] == ResourceType.FISH
    )
    no_biologist_fish = next(
        option for option in engine.production_options(no_biologist, normal_event, "Spring")
        if option["output"] == ResourceType.FISH
    )

    assert staffed_fish["max_qty"] == 24
    assert no_biologist_fish["max_qty"] == 12


def test_fish_processing_technicians_staff_two_per_boat(normal_event):
    from island_traders.models.player import Player
    from island_traders.models.role import ROLES

    engine = ProductionEngine()

    def fish_option(boats: int, techs: int) -> int:
        farmer = Player(203 + boats + techs, "Fleet", [ROLES["Farmer"]], 100.0, is_human=True)
        farmer.add_capital("farmer.fishing_boat", boats)
        farmer.workforce.add_workers(1, training_level=1, profession=Profession.FARMER.value)
        farmer.workforce.add_workers(
            1, training_level=1, profession=Profession.MARINE_BIOLOGIST.value
        )
        farmer.workforce.add_workers(
            techs,
            training_level=1,
            profession=Profession.FISH_PROCESSING_TECHNICIAN.value,
        )
        farmer.workforce.add_workers(12, profession=Profession.UNSKILLED.value)
        farmer.receive_resources(ResourceType.OIL, 10)
        return next(
            option for option in engine.production_options(farmer, normal_event, "Spring")
            if option["output"] == ResourceType.FISH
        )["max_qty"]

    assert fish_option(1, 1) == 12
    assert fish_option(1, 2) == 24
    assert fish_option(2, 2) == 24
    assert fish_option(2, 4) == 48


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


def test_farmer_specialists_are_year_round_optional_bonuses(normal_event):
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
    bare.receive_resources(ResourceType.GRAIN, 240)

    staffed = Player(214, "Staffed Farm", [ROLES["Farmer"]], 100.0, is_human=True)
    staffed.receive_resources(ResourceType.FARM_MACHINERY, 1)
    staffed.receive_resources(ResourceType.OIL, 1)
    staffed.add_capital("farmer.livestock_barn")
    staffed.workforce.add_workers(1, training_level=1, profession=Profession.FARMER.value)
    staffed.workforce.add_workers(1, training_level=1, profession=Profession.FARMING_TECHNICIAN.value)
    staffed.workforce.add_workers(1, training_level=1, profession=Profession.HORTICULTURALIST.value)
    staffed.workforce.add_workers(1, training_level=1, profession=Profession.VETERINARIAN.value)
    staffed.workforce.add_workers(8, profession=Profession.UNSKILLED.value)
    staffed.receive_resources(ResourceType.GRAIN, 240)

    engine = ProductionEngine()
    bare_preview = engine.production_preview(bare, normal_event, "Spring")
    staffed_preview = engine.production_preview(staffed, normal_event, "Spring")
    bare_meat = next(
        option for option in engine.production_options(bare, normal_event, "Spring")
        if option["output"] == ResourceType.MEAT
    )
    staffed_meat = next(
        option for option in engine.production_options(staffed, normal_event, "Spring")
        if option["output"] == ResourceType.MEAT
    )

    assert bare_preview["outputs"][ResourceType.GRAIN] == 24
    assert bare_preview["outputs"][ResourceType.PRODUCE] == 24
    assert staffed_preview["outputs"][ResourceType.GRAIN] == 32
    assert staffed_preview["outputs"][ResourceType.PRODUCE] == 32
    assert bare_meat["max_qty"] == 40
    assert staffed_meat["max_qty"] == 60


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
