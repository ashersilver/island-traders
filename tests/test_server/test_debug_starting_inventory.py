"""TEST/DEBUG affordance: role-keyed opening-inventory overrides at launch.

See requirements/playtest-defects-and-tuning-2026-06-14.md (startfood affordance):
a debug room can seed e.g. the Farmer with 200 Food so food production doesn't
cloud a balance test. Resource names match ResourceType case-insensitively;
non-debug rooms are unaffected.
"""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from island_traders.server.app import GameManager, GameRoom, LobbyPlayer
from island_traders.models.resource import ResourceType


def _room(mgr: GameManager, room_id: str, debug_inv=None) -> str:
    room = GameRoom(
        room_id=room_id, name="Test", max_players=7, num_years=1,
        is_public=True, join_code=room_id[:6].upper().ljust(6, "Z"),
        starting_capital=1500.0,
        debug_starting_inventory=dict(debug_inv or {}),
    )
    room.players.append(LobbyPlayer(player_id="h1", name="Solo"))
    room.players[0].role_names = ["Farmer"]
    mgr.rooms[room_id] = room
    mgr._loop = None
    return room_id


def _food(mgr: GameManager, rid: str) -> int:
    p = mgr.rooms[rid].game.players[0]
    return p.inventory.get(ResourceType.FOOD)


def test_debug_inventory_seeds_named_role_case_insensitively():
    mgr = GameManager()
    # Control: identical room with no overrides.
    ctrl = _room(mgr, "ctrlroom")
    mgr._launch_game(ctrl, bids={"h1": 400.0}, capital_spend={"h1": 0.0})
    baseline_food = _food(mgr, ctrl)

    # Debug room: 'food' (lower-case) must still resolve to ResourceType.FOOD.
    dbg = _room(mgr, "dbgroom00", debug_inv={"Farmer": {"food": 200}})
    mgr._launch_game(dbg, bids={"h1": 400.0}, capital_spend={"h1": 0.0})

    assert _food(mgr, dbg) == baseline_food + 200


def test_unknown_resource_is_skipped_not_fatal():
    mgr = GameManager()
    rid = _room(mgr, "dbgroom01", debug_inv={"Farmer": {"NotAResource": 50}})
    # Must not raise; launch completes and a game exists.
    mgr._launch_game(rid, bids={"h1": 400.0}, capital_spend={"h1": 0.0})
    assert mgr.rooms[rid].game is not None


def test_override_for_other_role_does_not_touch_this_player():
    mgr = GameManager()
    ctrl = _room(mgr, "ctrlroom2")
    mgr._launch_game(ctrl, bids={"h1": 400.0}, capital_spend={"h1": 0.0})
    baseline_food = _food(mgr, ctrl)

    # Override keyed to Miner; our solo player is a Farmer -> unaffected.
    rid = _room(mgr, "dbgroom02", debug_inv={"Miner": {"Food": 200}})
    mgr._launch_game(rid, bids={"h1": 400.0}, capital_spend={"h1": 0.0})
    assert _food(mgr, rid) == baseline_food
