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
        # Purchase flow now uses choose_option with named items (Issue
        # raised 2026-05-27 — index pickers were confusing on the
        # dashboard).  Select the harvester explicitly by item_id.
        def choose_option(self, prompt, options, request_summary=None):
            return "farmer.harvester"

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


def test_purchase_capital_uses_named_option_picker_not_numeric_index():
    """Regression for 2026-05-27 UX defect: the purchase picker must
    present items as named options (item_id-keyed choose_option), not
    as a 'type an index 1..N' choose_quantity prompt.  The dashboard
    renders choose_option as a radio picker with full descriptions on
    each row; choose_quantity renders as a bare number-input field.

    Lease / Invest / product-line pickers already use the named-option
    pattern.  This test pins the same pattern for Purchase Equipment.
    """
    farmer = Player(1, "Farmer", [ROLES["Farmer"]], 200.0, is_human=True)
    manufacturer = Player(2, "ForgeHaven", [ROLES["Manufacturer"]], 50.0, is_human=True)
    manufacturer.receive_resources(ResourceType.FARM_MACHINERY, 1)
    market = Market()

    captured: dict = {}

    class CapturingIO(FakeIOAdapter):
        def choose_option(self, prompt, options, request_summary=None):
            captured["prompt"] = prompt
            captured["options"] = options
            return options[0]["value"]

        def choose_quantity(self, prompt, min_qty, max_qty):
            captured["quantity_called_with"] = prompt
            return min_qty

    manager = TurnManager(
        [farmer, manufacturer],
        ProductionEngine(),
        TradingEngine(market, DealLedger()),
        market,
        CapturingIO(),
    )

    manager._action_purchase_capital(farmer, TurnResult(farmer.player_id, 0, 0), 0, 0)

    # The picker must have been invoked as a named-option picker.
    assert "options" in captured, "Purchase flow did not call choose_option"
    assert captured["prompt"] == "Choose capital item"
    # Each option carries a stable item_id value and a human-readable
    # label including the item's display name.
    assert all("value" in o and "label" in o for o in captured["options"])
    assert any("Tractor" in o["label"] or "tractor" in o["value"] for o in captured["options"])
    # And it must NOT have used choose_quantity for picking the item.
    assert captured.get("quantity_called_with") != "Choose capital item"
