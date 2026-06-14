"""Tests for the agent-interactions endpoint (GameManager methods).

External LLM agent processes POST transcript records here so the game server
can store and serve them for the observer UI.  The HTTP routes are FastAPI-
dependent; these unit tests exercise only the GameManager business logic,
which is plain Python and can run without a live server.
"""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from island_traders.server.app import GameManager, GameRoom, LobbyPlayer


def _make_room(mgr: GameManager) -> GameRoom:
    room = GameRoom(
        room_id="agentroom", name="AgentTest", max_players=7, num_years=1,
        is_public=True, join_code="AGT001", creator_id="host",
    )
    room.players.append(LobbyPlayer(player_id="host", name="Host"))
    room.status = "running"
    mgr.rooms[room.room_id] = room
    mgr._ws_connections[room.room_id] = {}
    mgr._loop = None
    return room


def _event(seq: int, kind: str = "ws_receive") -> dict:
    return {
        "run_id": "test-run",
        "seq": seq,
        "timestamp": "2026-06-12T00:00:00.000Z",
        "direction": "server->agent",
        "kind": kind,
        "message_type": "choose_action",
        "payload": {},
    }


# ── post ─────────────────────────────────────────────────────────────────────

def test_post_single_event_accepted():
    mgr = GameManager()
    room = _make_room(mgr)
    result = mgr.post_agent_interactions(room.room_id, [_event(1)])
    assert result == {"accepted": 1, "total": 1}
    assert len(room.agent_interactions) == 1


def test_post_batch_accepted():
    mgr = GameManager()
    room = _make_room(mgr)
    events = [_event(i) for i in range(1, 6)]
    result = mgr.post_agent_interactions(room.room_id, events)
    assert result["accepted"] == 5
    assert result["total"] == 5


def test_post_to_missing_room_returns_error():
    mgr = GameManager()
    result = mgr.post_agent_interactions("nonexistent", [_event(1)])
    assert "error" in result


def test_ring_buffer_trims_oldest():
    mgr = GameManager()
    room = _make_room(mgr)
    cap = GameManager._AGENT_INTERACTIONS_MAX
    first_batch = [_event(i) for i in range(1, cap + 1)]
    mgr.post_agent_interactions(room.room_id, first_batch)
    assert len(room.agent_interactions) == cap

    # Add 10 more — oldest 10 should be evicted
    extra = [_event(cap + i) for i in range(1, 11)]
    mgr.post_agent_interactions(room.room_id, extra)
    assert len(room.agent_interactions) == cap
    # Oldest survivor should be seq=11
    assert room.agent_interactions[0]["seq"] == 11


# ── get ───────────────────────────────────────────────────────────────────────

def test_get_all_events():
    mgr = GameManager()
    room = _make_room(mgr)
    mgr.post_agent_interactions(room.room_id, [_event(i) for i in range(1, 6)])
    result = mgr.get_agent_interactions(room.room_id, limit=0, since_seq=0)
    assert result is not None
    assert result["total"] == 5
    assert len(result["events"]) == 5


def test_get_with_limit():
    mgr = GameManager()
    room = _make_room(mgr)
    mgr.post_agent_interactions(room.room_id, [_event(i) for i in range(1, 11)])
    result = mgr.get_agent_interactions(room.room_id, limit=3, since_seq=0)
    # Returns the last 3 (most recent)
    assert len(result["events"]) == 3
    assert result["total"] == 10


def test_get_since_seq():
    mgr = GameManager()
    room = _make_room(mgr)
    mgr.post_agent_interactions(room.room_id, [_event(i) for i in range(1, 11)])
    result = mgr.get_agent_interactions(room.room_id, limit=0, since_seq=7)
    seqs = [e["seq"] for e in result["events"]]
    assert all(s > 7 for s in seqs)
    assert len(seqs) == 3  # seqs 8, 9, 10


def test_get_missing_room_returns_none():
    mgr = GameManager()
    result = mgr.get_agent_interactions("nonexistent")
    assert result is None


def test_events_accumulate_across_posts():
    mgr = GameManager()
    room = _make_room(mgr)
    mgr.post_agent_interactions(room.room_id, [_event(1), _event(2)])
    mgr.post_agent_interactions(room.room_id, [_event(3)])
    result = mgr.get_agent_interactions(room.room_id, limit=0, since_seq=0)
    assert result["total"] == 3
