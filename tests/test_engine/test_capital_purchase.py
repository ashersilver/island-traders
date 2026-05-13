from island_traders.cli.prompts import FakeIOAdapter
from island_traders.engine.production import ProductionEngine
from island_traders.engine.trading import TradingEngine
from island_traders.engine.turn import TurnManager, TurnResult
from island_traders.models.deal import DealLedger
from island_traders.models.market import Market
from island_traders.models.player import Player
from island_traders.models.resource import ResourceType
from island_traders.models.role import ROLES


def test_purchase_capital_consumes_manufactured_equipment_and_delivers_item():
    farmer = Player(1, "Farmer", [ROLES["Farmer"]], 200.0, is_human=True)
    manufacturer = Player(2, "ForgeHaven", [ROLES["Manufacturer"]], 50.0, is_human=True)
    manufacturer.receive_resources(ResourceType.FARM_MACHINERY, 1)
    market = Market()
    io = FakeIOAdapter()
    manager = TurnManager(
        [farmer, manufacturer],
        ProductionEngine(),
        TradingEngine(market, DealLedger()),
        market,
        io,
    )

    manager._action_purchase_capital(farmer, TurnResult(farmer.player_id, 0, 0), 0, 0)

    assert farmer.capital_count("farmer.tractor") == 1
    assert manufacturer.inventory.get(ResourceType.FARM_MACHINERY) == 0
    assert farmer.dollops == 140.0
    assert manufacturer.dollops == 110.0


def test_purchase_capital_places_delayed_item_in_transit():
    farmer = Player(1, "Farmer", [ROLES["Farmer"]], 200.0, is_human=True)
    manufacturer = Player(2, "ForgeHaven", [ROLES["Manufacturer"]], 50.0, is_human=True)
    manufacturer.receive_resources(ResourceType.FARM_MACHINERY, 1)
    market = Market()

    class HarvesterIO(FakeIOAdapter):
        def choose_quantity(self, prompt, min_qty, max_qty):
            return 2

    manager = TurnManager(
        [farmer, manufacturer],
        ProductionEngine(),
        TradingEngine(market, DealLedger()),
        market,
        HarvesterIO(),
    )

    manager._action_purchase_capital(farmer, TurnResult(farmer.player_id, 0, 0), 0, 1)

    assert farmer.capital_count("farmer.harvester") == 0
    assert farmer.capital_in_transit == [{"item_id": "farmer.harvester", "arrives_at_tick": 3}]
