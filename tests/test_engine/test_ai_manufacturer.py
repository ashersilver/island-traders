from __future__ import annotations

from island_traders.engine.ai import AIStrategy
from island_traders.engine.events import EventResult
from island_traders.engine.production import ProductionEngine
from island_traders.engine.trading import TradingEngine
from island_traders.models.deal import DealLedger
from island_traders.models.market import Market
from island_traders.models.player import Player
from island_traders.models.resource import ResourceType
from island_traders.models.role import ROLES


def _player(pid: int, role: str, dollops: float = 500.0) -> Player:
    return Player(pid, role, [ROLES[role]], dollops, is_human=False)


def _manufacturer(metal: int = 10, oil: int = 10) -> Player:
    player = _player(1, "Manufacturer")
    player.receive_resources(ResourceType.METAL, metal)
    player.receive_resources(ResourceType.OIL, oil)
    player.receive_resources(ResourceType.FREIGHT, 100)
    return player


def test_ai_manufacturer_picks_laboratory_equipment_for_unmet_lab_demand():
    ai = AIStrategy()
    manufacturer = _manufacturer()

    chosen = ai._choose_product_line(manufacturer, Market())

    assert chosen == "LaboratoryEquipment"


def test_ai_manufacturer_sticky_when_scores_within_ten_percent(monkeypatch):
    ai = AIStrategy()
    manufacturer = _manufacturer()
    manufacturer.ai_product_line = "FarmMachinery"

    def demand_units(output):
        if output == ResourceType.LABORATORY_EQUIPMENT:
            return 100
        if output == ResourceType.FARM_MACHINERY:
            return 95
        return 0

    monkeypatch.setattr(ai, "_manufacturer_demand_units", demand_units)

    chosen = ai._choose_product_line(manufacturer, Market())

    assert chosen == "FarmMachinery"


def test_ai_manufacturer_falls_back_to_best_feasible_line(monkeypatch):
    ai = AIStrategy()
    manufacturer = _manufacturer(metal=1, oil=1)

    def demand_units(output):
        if output == ResourceType.MINING_EQUIPMENT:
            return 200
        if output == ResourceType.LABORATORY_EQUIPMENT:
            return 100
        return 0

    monkeypatch.setattr(ai, "_manufacturer_demand_units", demand_units)

    chosen = ai._choose_product_line(manufacturer, Market())

    assert chosen == "LaboratoryEquipment"


def test_ai_manufacturer_idle_path_when_no_line_can_be_produced():
    ai = AIStrategy()
    manufacturer = _manufacturer(metal=0, oil=0)
    market = Market()

    actions = ai.take_turn(
        manufacturer,
        market,
        [manufacturer],
        ProductionEngine(),
        TradingEngine(market, DealLedger()),
        EventResult("Normal"),
        "Spring",
        0,
        0,
    )

    assert any("Manufacturer idle — out of inputs" in action for action in actions)


def test_ai_manufacturer_produces_and_lists_laboratory_equipment():
    ai = AIStrategy(target_production_runs=2)
    manufacturer = _manufacturer()
    market = Market()

    actions = ai.take_turn(
        manufacturer,
        market,
        [
            manufacturer,
            Player(2, "Human Educator", [ROLES["Educator"]], 500.0, is_human=True),
            _player(3, "Doctor"),
        ],
        ProductionEngine(),
        TradingEngine(market, DealLedger()),
        EventResult("Normal"),
        "Spring",
        0,
        0,
    )

    assert any("Laboratory Equipment" in action for action in actions)
    assert market.market_summary()[ResourceType.LABORATORY_EQUIPMENT.value]["ask_quantity"] > 0
