from __future__ import annotations

from island_traders.cli.prompts import FakeIOAdapter
from island_traders.constants import KITCHEN_FOOD_PER_SEASON, KITCHEN_ITEM_ID, UNIVERSITY_CAPACITY
from island_traders.constants_capacity import CAPITAL_CATALOGUE
from island_traders.engine.production import ProductionEngine
from island_traders.engine.trading import TradingEngine
from island_traders.engine.turn import TurnManager, TurnResult
from island_traders.models.capacity import find_item, items_for_role
from island_traders.models.deal import DealLedger
from island_traders.models.market import Market
from island_traders.models.player import Player
from island_traders.models.profession import PROFESSION_BAND, ROLE_PROFESSIONS, Profession, WorkerBand
from island_traders.models.resource import ResourceType
from island_traders.models.role import ROLES
from island_traders.models.training import away_seasons


def _player(role: str = "Farmer", dollops: float = 500.0) -> Player:
    return Player(0, role, [ROLES[role]], dollops, is_human=True)


def _stock_kitchen_inputs(player: Player, *, fish: int = 6, meat: int = 0) -> None:
    player.receive_resources(ResourceType.GRAIN, 12)
    player.receive_resources(ResourceType.PRODUCE, 6)
    player.receive_resources(ResourceType.FISH, fish)
    player.receive_resources(ResourceType.MEAT, meat)


def test_kitchen_is_universal_cash_only_capital_item():
    kitchen = find_item(CAPITAL_CATALOGUE, KITCHEN_ITEM_ID)

    assert kitchen is not None
    assert kitchen.role == "Any"
    assert kitchen.cost == 80.0
    assert kitchen.delivery_seasons == 0
    assert kitchen.service_life_seasons == 12
    assert kitchen.effects["cash_only"] is True
    assert kitchen.lease_terms is None
    for role_name in ROLES:
        assert kitchen in items_for_role(CAPITAL_CATALOGUE, role_name)


def test_chef_is_trainable_technician_for_every_island():
    assert PROFESSION_BAND[Profession.CHEF] == WorkerBand.TECHNICIAN
    assert away_seasons(Profession.CHEF.value) == 1
    assert UNIVERSITY_CAPACITY[Profession.CHEF.value] == 7
    for role_name in ROLES:
        assert Profession.CHEF in ROLE_PROFESSIONS[role_name]


def test_staffed_kitchen_converts_raw_ingredients_to_food():
    player = _player()
    player.add_capital(KITCHEN_ITEM_ID)
    player.workforce.add_workers(1, training_level=1, profession=Profession.CHEF.value)
    _stock_kitchen_inputs(player, fish=8)

    messages = ProductionEngine().run_kitchens(player)

    assert messages == [f"Kitchen 1: produced {KITCHEN_FOOD_PER_SEASON} Food."]
    assert player.inventory.get(ResourceType.FOOD) == 6
    assert player.inventory.get(ResourceType.GRAIN) == 0
    assert player.inventory.get(ResourceType.PRODUCE) == 0
    assert player.inventory.get(ResourceType.FISH) == 2
    assert player.inventory.get(ResourceType.MEAT) == 0


def test_kitchen_without_chef_idles_without_consuming_inputs():
    player = _player()
    player.add_capital(KITCHEN_ITEM_ID)
    _stock_kitchen_inputs(player, fish=6)

    messages = ProductionEngine().run_kitchens(player)

    assert messages == ["Kitchen idle: 1 kitchen(s), no active Chef."]
    assert player.inventory.get(ResourceType.FOOD) == 0
    assert player.inventory.get(ResourceType.GRAIN) == 12
    assert player.inventory.get(ResourceType.PRODUCE) == 6
    assert player.inventory.get(ResourceType.FISH) == 6


def test_kitchen_missing_ingredient_idles_without_partial_consumption():
    player = _player()
    player.add_capital(KITCHEN_ITEM_ID)
    player.workforce.add_workers(1, training_level=1, profession=Profession.CHEF.value)
    player.receive_resources(ResourceType.GRAIN, 12)
    player.receive_resources(ResourceType.PRODUCE, 5)
    player.receive_resources(ResourceType.FISH, 6)

    messages = ProductionEngine().run_kitchens(player)

    assert messages == ["Kitchen 1 idle: short on Produce."]
    assert player.inventory.get(ResourceType.FOOD) == 0
    assert player.inventory.get(ResourceType.GRAIN) == 12
    assert player.inventory.get(ResourceType.PRODUCE) == 5
    assert player.inventory.get(ResourceType.FISH) == 6


def test_kitchen_tie_breaks_protein_to_fish():
    player = _player()
    player.add_capital(KITCHEN_ITEM_ID)
    player.workforce.add_workers(1, training_level=1, profession=Profession.CHEF.value)
    _stock_kitchen_inputs(player, fish=6, meat=6)

    ProductionEngine().run_kitchens(player)

    assert player.inventory.get(ResourceType.FOOD) == 6
    assert player.inventory.get(ResourceType.FISH) == 0
    assert player.inventory.get(ResourceType.MEAT) == 6


def test_multiple_kitchens_use_one_chef_per_active_kitchen():
    player = _player()
    player.add_capital(KITCHEN_ITEM_ID, count=2)
    player.workforce.add_workers(1, training_level=1, profession=Profession.CHEF.value)
    player.receive_resources(ResourceType.GRAIN, 24)
    player.receive_resources(ResourceType.PRODUCE, 12)
    player.receive_resources(ResourceType.MEAT, 12)

    messages = ProductionEngine().run_kitchens(player)

    assert messages == [
        "Kitchen idle: 1 kitchen(s) need Chef staffing.",
        f"Kitchen 1: produced {KITCHEN_FOOD_PER_SEASON} Food.",
    ]
    assert player.inventory.get(ResourceType.FOOD) == 6
    assert player.inventory.get(ResourceType.GRAIN) == 12
    assert player.inventory.get(ResourceType.PRODUCE) == 6
    assert player.inventory.get(ResourceType.MEAT) == 6


class KitchenPurchaseIO(FakeIOAdapter):
    def choose_quantity(self, prompt, min_qty, max_qty):
        return max_qty

    def confirm(self, prompt, **kwargs):
        return True


def test_purchase_capital_can_buy_cash_only_kitchen_without_manufacturer():
    player = _player(dollops=100.0)
    market = Market()
    manager = TurnManager(
        players=[player],
        production_engine=ProductionEngine(),
        trading_engine=TradingEngine(market, DealLedger()),
        market=market,
        io_adapter=KitchenPurchaseIO(),
    )
    result = TurnResult(player.player_id, season=0, year=0)

    manager._action_purchase_capital(player, result, year=0, season_index=0)

    assert player.dollops == 20.0
    assert player.capital_inventory[KITCHEN_ITEM_ID] == 1
    assert result.actions_taken == [f"purchase_capital:{KITCHEN_ITEM_ID}:cash"]
