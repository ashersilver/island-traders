import pytest
from island_traders.engine.production import ProductionEngine, InsufficientInputsError
from island_traders.engine.events import EventResult
from island_traders.models.resource import ResourceType


def _give_farmer_inputs(farmer):
    farmer.receive_resources(ResourceType.CAPITAL_EQUIPMENT, 1)
    farmer.receive_resources(ResourceType.OIL, 1)


def test_farmer_produces_with_inputs(farmer, normal_event):
    _give_farmer_inputs(farmer)
    engine = ProductionEngine()
    produced = engine.produce(farmer, normal_event, season_name="Spring")
    assert ResourceType.FOOD in produced
    assert ResourceType.FISH in produced
    assert farmer.inventory.get(ResourceType.CAPITAL_EQUIPMENT) == 0
    assert farmer.inventory.get(ResourceType.OIL) == 0


def test_farmer_cannot_produce_without_inputs(farmer, normal_event):
    engine = ProductionEngine()
    with pytest.raises(InsufficientInputsError):
        engine.produce(farmer, normal_event)


def test_farmer_seasonal_outputs_differ(farmer, normal_event):
    """Autumn harvest should produce more Food than Spring planting."""
    engine = ProductionEngine()
    _give_farmer_inputs(farmer)
    spring = engine.produce(farmer, normal_event, season_name="Spring")
    _give_farmer_inputs(farmer)
    autumn = engine.produce(farmer, normal_event, season_name="Autumn")
    assert autumn.get(ResourceType.FOOD, 0) > spring.get(ResourceType.FOOD, 0)


def test_outage_blocks_production(farmer, outage_event):
    _give_farmer_inputs(farmer)
    engine = ProductionEngine()
    produced = engine.produce(farmer, outage_event)
    assert produced == {}
    assert farmer.inventory.get(ResourceType.CAPITAL_EQUIPMENT) == 1
    assert farmer.inventory.get(ResourceType.OIL) == 1


def test_banker_needs_knowledge_and_equipment(banker, normal_event):
    banker.receive_resources(ResourceType.KNOWLEDGE, 1)
    banker.receive_resources(ResourceType.CAPITAL_EQUIPMENT, 1)
    engine = ProductionEngine()
    produced = engine.produce(banker, normal_event)
    assert ResourceType.FINANCE in produced
    assert produced[ResourceType.FINANCE] > 0


def test_banker_cannot_produce_without_inputs(banker, normal_event):
    engine = ProductionEngine()
    with pytest.raises(InsufficientInputsError):
        engine.produce(banker, normal_event)


def test_bumper_harvest_increases_yield(farmer, bumper_event):
    _give_farmer_inputs(farmer)
    engine = ProductionEngine()
    # Spring: base Food=2, yield_modifier=1.8, bonus=2 → int(2*1.8)+2 = 3+2 = 5
    produced = engine.produce(farmer, bumper_event, season_name="Spring")
    assert produced.get(ResourceType.FOOD, 0) == 5


def test_production_preview_does_not_mutate(farmer, normal_event):
    _give_farmer_inputs(farmer)
    engine = ProductionEngine()
    before_dollops = farmer.dollops
    before_equip = farmer.inventory.get(ResourceType.CAPITAL_EQUIPMENT)
    before_oil = farmer.inventory.get(ResourceType.OIL)
    engine.production_preview(farmer, normal_event)
    assert farmer.dollops == before_dollops
    assert farmer.inventory.get(ResourceType.CAPITAL_EQUIPMENT) == before_equip
    assert farmer.inventory.get(ResourceType.OIL) == before_oil


def test_can_produce_returns_missing(farmer, normal_event):
    engine = ProductionEngine()
    can, missing = engine.can_produce(farmer, normal_event)
    assert not can
    assert ResourceType.CAPITAL_EQUIPMENT in missing or ResourceType.OIL in missing
