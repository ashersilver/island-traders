"""Leaving a waiting room (deregister after joining the wrong game).

Covers GameManager.leave_room: removing a player, host reassignment, room
teardown when the last human leaves, and the guards (wrong status / unknown
room / not-a-member).
"""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from island_traders.server.app import GameManager


def _room_with_two_humans():
    mgr = GameManager()
    room = mgr.create_room("Lobby", creator_name="Host")
    _, guest = mgr.join_room(room.room_id, "Guest")
    return mgr, room, guest


def test_leave_removes_the_player():
    mgr, room, guest = _room_with_two_humans()
    before = len(room.players)
    result = mgr.leave_room(room.room_id, guest.player_id)
    assert result == {"left": True, "room_closed": False}
    assert len(room.players) == before - 1
    assert all(p.player_id != guest.player_id for p in room.players)
    assert room.room_id in mgr.rooms  # room still open (host remains)


def test_host_leaving_reassigns_host_to_next_human():
    mgr, room, guest = _room_with_two_humans()
    host_id = room.creator_id
    result = mgr.leave_room(room.room_id, host_id)
    assert result["left"] is True
    assert room.creator_id == guest.player_id  # host passed to the remaining human


def test_last_human_leaving_closes_the_room():
    mgr = GameManager()
    room = mgr.create_room("Solo", creator_name="Host")
    mgr.add_ai_player(room.room_id, "Atlas AI")  # AI alone can't start a game
    code = room.join_code
    result = mgr.leave_room(room.room_id, room.creator_id)
    assert result == {"left": True, "room_closed": True}
    assert room.room_id not in mgr.rooms
    assert mgr.find_room_by_code(code) is None


def test_cannot_leave_once_the_game_has_started():
    mgr, room, guest = _room_with_two_humans()
    room.status = "auction"
    result = mgr.leave_room(room.room_id, guest.player_id)
    assert "error" in result
    assert guest.player_id in {p.player_id for p in room.players}  # unchanged


def test_leave_unknown_room_and_unknown_player():
    mgr, room, guest = _room_with_two_humans()
    assert mgr.leave_room("nope", guest.player_id) == {"error": "Room not found"}
    assert "error" in mgr.leave_room(room.room_id, "not-a-member")
