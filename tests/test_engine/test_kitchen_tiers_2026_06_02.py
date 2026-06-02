from __future__ import annotations

from island_traders.constants_capacity import CAPITAL_CATALOGUE
from island_traders.engine.production import ProductionEngine
from island_traders.models.capacity import find_item, items_for_role
from island_traders.models.player import Player
from island_traders.models.profession import Profession
from island_traders.models.resource import ResourceType
from island_traders.models.role import ROLES


INDUSTRIAL_KITCHEN = "common.industrial_kitchen"
MANUFACTURING_KITCHEN = "common.kitchen"


def _player() -> Player:
    return Player(0, "Farmer", [ROLES["Farmer"]], 500.0, is_human=True)


def _stock(
    player: Player,
    *,
    grain: int,
    produce: int,
    fish: int = 0,
    meat: int = 0,
) -> None:
    player.receive_resources(ResourceType.GRAIN, grain)
    player.receive_resources(ResourceType.PRODUCE, produce)
    player.receive_resources(ResourceType.FISH, fish)
    player.receive_resources(ResourceType.MEAT, meat)


def _add_chef(player: Player, count: int = 1) -> None:
    player.workforce.add_workers(
        count, training_level=1, profession=Profession.CHEF.value
    )


def test_industrial_kitchen_is_universal_opening_catalogue_item():
    item = find_item(CAPITAL_CATALOGUE, INDUSTRIAL_KITCHEN)

    assert item is not None
    assert item.role == "Any"
    assert item.cost == 150.0
    assert item.delivery_seasons == 1
    assert item.effects["kitchen_food_per_season"] == 20
    for role_name in ROLES:
        assert item in items_for_role(CAPITAL_CATALOGUE, role_name)


def test_industrial_kitchen_produces_twenty_food_without_chef():
    player = _player()
    player.add_capital(INDUSTRIAL_KITCHEN)
    _stock(player, grain=20, produce=10, fish=10)

    messages = ProductionEngine().run_kitchens(player)

    assert messages == ["Industrial Kitchen 1: produced 20 Food."]
    assert player.inventory.get(ResourceType.FOOD) == 20
    assert player.inventory.get(ResourceType.GRAIN) == 0
    assert player.inventory.get(ResourceType.PRODUCE) == 0
    assert player.inventory.get(ResourceType.FISH) == 0


def test_manufacturing_kitchen_produces_ten_food_only_with_chef():
    player = _player()
    player.add_capital(MANUFACTURING_KITCHEN)
    _stock(player, grain=20, produce=10, fish=10)

    messages = ProductionEngine().run_kitchens(player)

    assert messages == ["Kitchen 1 idle: needs a Chef."]
    assert player.inventory.get(ResourceType.FOOD) == 0
    assert player.inventory.get(ResourceType.GRAIN) == 20
    assert player.inventory.get(ResourceType.PRODUCE) == 10
    assert player.inventory.get(ResourceType.FISH) == 10

    _add_chef(player)
    messages = ProductionEngine().run_kitchens(player)

    assert messages == ["Kitchen 1: produced 10 Food."]
    assert player.inventory.get(ResourceType.FOOD) == 10
    assert player.inventory.get(ResourceType.GRAIN) == 0
    assert player.inventory.get(ResourceType.PRODUCE) == 0
    assert player.inventory.get(ResourceType.FISH) == 0


def test_two_chef_kitchens_with_one_chef_plus_industrial_kitchen():
    player = _player()
    player.add_capital(MANUFACTURING_KITCHEN, count=2)
    player.add_capital(INDUSTRIAL_KITCHEN)
    _add_chef(player)
    _stock(player, grain=60, produce=30, fish=30)

    messages = ProductionEngine().run_kitchens(player)

    assert messages == [
        "Kitchen 1: produced 10 Food.",
        "Kitchen 2 idle: needs a Chef.",
        "Industrial Kitchen 1: produced 20 Food.",
    ]
    assert player.inventory.get(ResourceType.FOOD) == 30
    assert player.inventory.get(ResourceType.GRAIN) == 20
    assert player.inventory.get(ResourceType.PRODUCE) == 10
    assert player.inventory.get(ResourceType.FISH) == 10


def test_kitchen_short_on_ingredient_idles_with_clear_reason():
    player = _player()
    player.add_capital(INDUSTRIAL_KITCHEN)
    _stock(player, grain=19, produce=10, fish=10)

    messages = ProductionEngine().run_kitchens(player)

    assert messages == ["Industrial Kitchen 1 idle: short on Grain."]
    assert player.inventory.get(ResourceType.FOOD) == 0
    assert player.inventory.get(ResourceType.GRAIN) == 19
    assert player.inventory.get(ResourceType.PRODUCE) == 10
    assert player.inventory.get(ResourceType.FISH) == 10


def test_common_kitchen_with_chef_regression_makes_ten_not_six():
    player = _player()
    player.add_capital(MANUFACTURING_KITCHEN)
    _add_chef(player)
    _stock(player, grain=20, produce=10, meat=10)

    ProductionEngine().run_kitchens(player)

    assert player.inventory.get(ResourceType.FOOD) == 10
