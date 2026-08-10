"""Owned storage and the single unprotected-stock spoilage rule."""
from __future__ import annotations

import pytest

from island_traders.cli.prompts import FakeIOAdapter
from island_traders.engine.game import Game, GameConfig, PlayerSpec
from island_traders.models.player import Player
from island_traders.models.resource import ResourceType
from island_traders.models.role import ROLES


def _player(role: str = "Farmer") -> Player:
    return Player(
        player_id=1,
        name=role,
        roles=[ROLES[role]],
        dollops=500.0,
        is_human=False,
    )


def test_protected_stock_never_spoils():
    player = _player()
    player.add_capital("farmer.grain_silo")
    player.receive_resources(ResourceType.GRAIN, 100)

    for tick in range(6):
        assert player.process_spoilage(tick) == {}

    assert player.inventory.get(ResourceType.GRAIN) == 100
    assert player.spoilage_buckets == {}


@pytest.mark.parametrize(
    ("resource", "shelf_life"),
    [
        (ResourceType.GRAIN, 1),
        (ResourceType.FOOD, 2),
        (ResourceType.SPARES, 4),
    ],
)
def test_unprotected_stock_spoils_exactly_on_its_shelf_life(resource, shelf_life):
    player = _player("Manufacturer")
    player.receive_resources(resource, 7)

    assert player.process_spoilage(0) == {}
    for tick in range(1, shelf_life):
        assert player.process_spoilage(tick) == {}
        assert player.inventory.get(resource) == 7

    assert player.process_spoilage(shelf_life) == {resource: 7}
    assert player.inventory.get(resource) == 0


def test_only_stock_above_owned_capacity_ages_and_perishes():
    player = _player()
    player.add_capital("farmer.grain_silo")
    player.receive_resources(ResourceType.GRAIN, 105)

    assert player.process_spoilage(0) == {}
    assert player.spoilage_status(ResourceType.GRAIN, 0) == {
        "protected": 100,
        "at_risk": 5,
        "perishes_in_seasons": 1,
    }
    assert player.process_spoilage(1) == {ResourceType.GRAIN: 5}
    assert player.inventory.get(ResourceType.GRAIN) == 100
    assert player.process_spoilage(5) == {}


def test_failed_or_unmaintained_storage_does_not_protect_stock():
    player = _player()
    player.add_capital("farmer.grain_silo")
    player.capital_units["farmer.grain_silo"][0].status = "failed"
    player.receive_resources(ResourceType.GRAIN, 10)

    assert player.storage_capacity(ResourceType.GRAIN) == 0
    assert player.process_spoilage(0) == {}
    assert player.process_spoilage(1) == {ResourceType.GRAIN: 10}

    player.add_capital("common.food_store")
    player.unmaintained_capital = {"common.food_store": 1}
    assert player.storage_capacity(ResourceType.FOOD) == 0


def test_spoilage_buckets_survive_save_load(tmp_path):
    game = Game(
        GameConfig(player_specs=[PlayerSpec("Farmer", ["Farmer"], is_human=False)]),
        FakeIOAdapter(),
    )
    game.setup()
    player = game.players[0]
    player.receive_resources(ResourceType.GRAIN, 3)
    player.spoilage_buckets = {"Grain": [{"acquired_tick": 2, "qty": 3}]}

    path = tmp_path / "spoilage-save.json"
    game.save(str(path))
    loaded = Game.load(str(path), FakeIOAdapter())

    assert loaded.players[0].spoilage_buckets == {
        "Grain": [{"acquired_tick": 2, "qty": 3}]
    }


def test_spares_clamp_uses_general_storage_capacity():
    player = _player("Manufacturer")
    player.add_capital("manufacturer.small_warehouse")
    player.add_capital("manufacturer.warehouse")

    assert player.storage_capacity(ResourceType.SPARES) == 42
    assert player.spares_capacity() == 42
    assert player.manufacture_spares(50) == 42
    assert player.manufacture_spares(1) == 0
