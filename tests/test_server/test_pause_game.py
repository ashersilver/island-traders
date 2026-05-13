"""Server-side tests for the Pause Game feature (Issue #1).

Covers:
  * Only the host can pause / resume.
  * `paused` flag and broadcast lifecycle.
  * Timer epochs (auction, investing, season action, pre-season) are bumped
    forward by the pause duration on resume — players don't lose time.
  * Asyncio timer tasks are cancelled on pause.
  * Ready submissions during pause do NOT advance the game (no interrupt_all,
    no _pre_season_done.set) — those fire only after resume.
  * `_do_resume` re-checks the Ready quorum: if everyone was Ready during
    pause, the phase closes immediately on resume.
"""
from __future__ import annotations

import time
import pytest

pytest.importorskip("fastapi")

from island_traders.server.app import (
    AuctionState, GameManager, GameRoom, LobbyPlayer,
)


def _make_room(manager: GameManager, *, status: str = "running") -> GameRoom:
    room = GameRoom(
        room_id="pauseroom", name="Test", max_players=7, num_years=1,
        is_public=True, join_code="PAUSE1", creator_id="host",
    )
    room.players.append(LobbyPlayer(player_id="host", name="Host"))
    room.players.append(LobbyPlayer(player_id="p2", name="Player2"))
    room.status = status
    manager.rooms[room.room_id] = room
    manager._ws_connections[room.room_id] = {}
    manager._loop = None
    return room


def test_only_host_can_pause():
    mgr = GameManager()
    room = _make_room(mgr)

    # Non-host attempts to pause → rejected
    res = mgr.request_pause(room.room_id, "p2", True)
    assert "error" in res
    assert room.paused is False

    # Host can pause
    res = mgr.request_pause(room.room_id, "host", True)
    assert res.get("ok") is True
    assert room.paused is True


def test_pause_from_waiting_status_rejected():
    mgr = GameManager()
    room = _make_room(mgr, status="waiting")
    res = mgr.request_pause(room.room_id, "host", True)
    assert "error" in res
    assert room.paused is False


def test_pause_resume_round_trip():
    mgr = GameManager()
    room = _make_room(mgr)
    assert room.paused is False

    assert mgr.request_pause(room.room_id, "host", True).get("ok") is True
    assert room.paused is True
    assert room.paused_at > 0

    assert mgr.request_pause(room.room_id, "host", False).get("ok") is True
    assert room.paused is False
    assert room.paused_at == 0.0


def test_double_pause_is_noop():
    mgr = GameManager()
    room = _make_room(mgr)
    mgr.request_pause(room.room_id, "host", True)
    first_paused_at = room.paused_at
    time.sleep(0.05)
    res = mgr.request_pause(room.room_id, "host", True)
    assert res.get("noop") is True
    # paused_at should not change on noop
    assert room.paused_at == first_paused_at


def test_pause_freezes_auction_timer_end_and_resume_bumps_it_forward():
    mgr = GameManager()
    room = _make_room(mgr, status="auction")
    now = time.time()
    room.auction = AuctionState(timer_end=now + 60)

    original_end = room.auction.timer_end
    mgr.request_pause(room.room_id, "host", True)
    time.sleep(0.15)  # simulate pause duration
    mgr.request_pause(room.room_id, "host", False)

    # Resume should have bumped timer_end forward by ~pause duration
    bumped = room.auction.timer_end - original_end
    assert 0.10 < bumped < 0.50, f"timer_end bumped by {bumped}s, expected ~0.15s"


def test_pause_freezes_season_timer_end_and_resume_bumps_it_forward():
    mgr = GameManager()
    room = _make_room(mgr, status="running")
    room.season_phase = "action"
    room.season_timer_end = time.time() + 120

    original_end = room.season_timer_end
    mgr.request_pause(room.room_id, "host", True)
    time.sleep(0.15)
    mgr.request_pause(room.room_id, "host", False)

    bumped = room.season_timer_end - original_end
    assert 0.10 < bumped < 0.50


def test_pause_freezes_pre_season_end_and_resume_bumps_it_forward():
    mgr = GameManager()
    room = _make_room(mgr, status="running")
    room.season_phase = "pre_season"
    room.pre_season_end = time.time() + 30

    original_end = room.pre_season_end
    mgr.request_pause(room.room_id, "host", True)
    time.sleep(0.15)
    mgr.request_pause(room.room_id, "host", False)

    bumped = room.pre_season_end - original_end
    assert 0.10 < bumped < 0.50


def test_ready_during_pause_does_not_advance_pre_season():
    """submit_ready in pre_season while paused must NOT set _pre_season_done."""
    mgr = GameManager()
    room = _make_room(mgr, status="running")
    room.season_phase = "pre_season"

    # Use a FakeIO adapter that satisfies submit_ready's preconditions
    class FakeIO:
        def begin_season(self): pass
        def interrupt_all(self): self.interrupted = True
        def mark_player_ready(self, pid): pass
        def unmark_player_ready(self, pid): pass

    room.io_adapter = FakeIO()
    room.season_active_humans = {"host", "p2"}
    room.season_ready_set = set()
    room.lobby_to_engine_id = {"host": 0, "p2": 1}

    mgr.request_pause(room.room_id, "host", True)

    # Both submit Ready during pause
    mgr.submit_ready(room.room_id, "host", True)
    mgr.submit_ready(room.room_id, "p2", True)

    # Ready set is recorded but pre_season_done is NOT set yet
    assert room.season_ready_set == {"host", "p2"}
    assert room._pre_season_done.is_set() is False


def test_resume_advances_pre_season_if_quorum_reached_during_pause():
    """If everyone Readied during pause, _do_resume should set _pre_season_done."""
    mgr = GameManager()
    room = _make_room(mgr, status="running")
    room.season_phase = "pre_season"
    room.pre_season_end = time.time() + 30

    class FakeIO:
        def begin_season(self): pass
        def interrupt_all(self): self.interrupted = True
        def mark_player_ready(self, pid): pass
        def unmark_player_ready(self, pid): pass

    room.io_adapter = FakeIO()
    room.season_active_humans = {"host", "p2"}
    room.season_ready_set = set()
    room.lobby_to_engine_id = {"host": 0, "p2": 1}

    mgr.request_pause(room.room_id, "host", True)
    mgr.submit_ready(room.room_id, "host", True)
    mgr.submit_ready(room.room_id, "p2", True)
    assert room._pre_season_done.is_set() is False  # held during pause

    mgr.request_pause(room.room_id, "host", False)

    # Resume should detect the quorum and unblock the pre-season wait
    assert room._pre_season_done.is_set() is True


def test_resume_calls_interrupt_all_if_action_quorum_during_pause():
    """If everyone Readied during pause in action phase, resume must trigger
    interrupt_all() so the season closes immediately."""
    mgr = GameManager()
    room = _make_room(mgr, status="running")
    room.season_phase = "action"

    class FakeIO:
        def __init__(self):
            self.interrupted = False
        def begin_season(self): pass
        def interrupt_all(self): self.interrupted = True
        def mark_player_ready(self, pid): pass
        def unmark_player_ready(self, pid): pass

    fake = FakeIO()
    room.io_adapter = fake
    room.season_active_humans = {"host", "p2"}
    room.season_ready_set = set()
    room.season_human_done = set()
    room.lobby_to_engine_id = {"host": 0, "p2": 1}

    mgr.request_pause(room.room_id, "host", True)
    mgr.submit_ready(room.room_id, "host", True)
    mgr.submit_ready(room.room_id, "p2", True)
    assert fake.interrupted is False  # held during pause

    mgr.request_pause(room.room_id, "host", False)
    assert fake.interrupted is True


def test_pause_cancels_auction_timer_task():
    """The asyncio timer future stored on auction._timer_task must be cancelled."""
    mgr = GameManager()
    room = _make_room(mgr, status="auction")
    room.auction = AuctionState(timer_end=time.time() + 60)

    class FakeFuture:
        def __init__(self):
            self.cancelled = False
        def cancel(self):
            self.cancelled = True
    fake = FakeFuture()
    room.auction._timer_task = fake

    mgr.request_pause(room.room_id, "host", True)
    assert fake.cancelled is True
    assert room.auction._timer_task is None


def test_creator_id_exposed_in_to_dict():
    """Client needs creator_id to decide who shows the Pause button."""
    mgr = GameManager()
    room = _make_room(mgr)
    d = room.to_dict()
    assert d["creator_id"] == "host"
    assert d["paused"] is False
