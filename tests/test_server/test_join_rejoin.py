"""Quick-seat ?join= URLs must reconnect to an established (running) game.

The /api/rooms/{id}/join endpoint composes join_room with a rejoin-by-name
fallback (mirroring join-by-code). Before the fix, join_room returned None for a
running room and the endpoint 400'd, so a quick-seat join URL stopped working
"once the game was established".
"""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from island_traders.server.app import GameManager


def test_plain_join_fails_once_running_but_rejoin_by_name_reconnects():
    mgr = GameManager()
    room = mgr.create_room("Trading Hole", creator_name="Host")
    _, cargo = mgr.join_room(room.room_id, "Cargo")
    original_id = cargo.player_id

    # Game starts.
    room.status = "running"

    # The plain join path (what /join tried first) now refuses — by design.
    assert mgr.join_room(room.room_id, "Cargo") is None

    # The endpoint's fallback reconnects to the SAME seat by name.
    result = mgr.rejoin_room_by_name(room.room_id, "Cargo")
    assert result is not None
    _, lp = result
    assert lp.player_id == original_id
    assert lp.is_human


def test_rejoin_is_case_insensitive_and_rejects_unknown_name():
    mgr = GameManager()
    room = mgr.create_room("Trading Hole", creator_name="Host")
    _, cargo = mgr.join_room(room.room_id, "Cargo")
    room.status = "running"

    # Same name, different case -> same seat.
    result = mgr.rejoin_room_by_name(room.room_id, "cargo")
    assert result is not None and result[1].player_id == cargo.player_id

    # A name nobody used -> no reconnect (endpoint would 400).
    assert mgr.rejoin_room_by_name(room.room_id, "Ghost") is None
