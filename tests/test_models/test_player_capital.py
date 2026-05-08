"""Tests for Player.capital_inventory and capital_in_transit lifecycle."""
from __future__ import annotations

from island_traders.models.player import Player
from island_traders.models.role import ROLES


def make_player() -> Player:
    return Player(player_id=1, name="Alice", roles=[ROLES["Farmer"]], dollops=100.0)


def test_capital_inventory_starts_empty():
    p = make_player()
    assert p.capital_inventory == {}
    assert p.capital_in_transit == []
    assert p.active_patents == {}


def test_add_and_remove_capital():
    p = make_player()
    p.add_capital("farmer.tractor")
    assert p.capital_count("farmer.tractor") == 1

    p.add_capital("farmer.tractor", 2)
    assert p.capital_count("farmer.tractor") == 3

    removed = p.remove_capital("farmer.tractor", 1)
    assert removed == 1
    assert p.capital_count("farmer.tractor") == 2

    # Removing more than owned returns the actual count removed and zeroes the entry
    removed = p.remove_capital("farmer.tractor", 100)
    assert removed == 2
    assert p.capital_count("farmer.tractor") == 0
    assert "farmer.tractor" not in p.capital_inventory


def test_in_transit_delivers_when_due():
    p = make_player()
    # Buy a 2-season item at tick 5; it arrives at tick 7
    p.capital_in_transit.append({"item_id": "farmer.harvester", "arrives_at_tick": 7})
    p.capital_in_transit.append({"item_id": "miner.oil_rig", "arrives_at_tick": 9})

    delivered = p.deliver_in_transit(current_tick=6)
    assert delivered == []
    assert len(p.capital_in_transit) == 2

    delivered = p.deliver_in_transit(current_tick=7)
    assert delivered == ["farmer.harvester"]
    assert p.capital_count("farmer.harvester") == 1
    assert len(p.capital_in_transit) == 1

    delivered = p.deliver_in_transit(current_tick=10)
    assert delivered == ["miner.oil_rig"]
    assert p.capital_count("miner.oil_rig") == 1
    assert p.capital_in_transit == []
