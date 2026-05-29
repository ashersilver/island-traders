"""Regression coverage for the "auction stuck at timer 0 with no Continue
button" bug reported during playtest 2026-05-24.

Two distinct failure modes, both surfacing the same symptom:

1. **Reconnect-during-resolution race.** ``_resolve_auction`` broadcasts
   the ``auction_result`` message exactly once.  ``room.status`` stays
   ``"auction"`` for ~2 seconds while ``_delayed_investing_start`` /
   ``_delayed_guarantee_start`` await their delay.  If a client
   reconnects during that window — or briefly drops its socket and the
   broadcast arrives at a closed socket — the reconnect handler in the
   WebSocket endpoint puts them back on the auction view with no way to
   advance, because the result overlay only renders from the live
   ``auction_result`` message.

   Fix: save the result payload on ``room.auction.result_payload`` and
   have the reconnect handler replay it when ``auction.phase ==
   "complete"``.

2. **Pause / resume right at expiry.** ``_do_pause`` cancels the active
   ``_auction_timer`` task.  ``_do_resume`` bumps ``auction.timer_end``
   forward by the pause duration and reschedules — but only if the
   bumped ``remaining > 0``.  If the user paused right at or after the
   original expiry (rare but reproducible), the bumped remaining is 0,
   the reschedule branch is skipped, and ``_resolve_auction`` never
   runs.  Same visible symptom.

   Fix: in ``_do_resume``, when ``remaining <= 0`` AND the auction is
   not yet ``"complete"``, call ``_resolve_auction`` directly.
"""
from __future__ import annotations

import time

import pytest

pytest.importorskip("fastapi")

from island_traders.server.app import (
    ALL_ROLES, AuctionState, GameManager, GameRoom, LobbyPlayer, RoleBid,
)


def _make_running_room_with_active_auction(mgr: GameManager) -> GameRoom:
    """Room in auction status with at least one bid so resolution has
    something to assign (otherwise every role goes to spawn-AI which
    works fine, just less expressive in assertions)."""
    room = GameRoom(
        room_id="auc1", name="AuctionRoom", max_players=7, num_years=1,
        is_public=True, join_code="AUC001", creator_id="host",
    )
    room.players.append(LobbyPlayer(player_id="host", name="Host"))
    room.players.append(LobbyPlayer(player_id="p2", name="Player2"))
    room.status = "auction"
    room.auction = AuctionState(
        bids={role: [] for role in ALL_ROLES},
        budget_spent={"host": 0.0, "p2": 0.0},
        timer_end=time.time() + 60.0,
    )
    # Seed a winning bid so the resolution path actually assigns roles.
    room.auction.bids["Banker"].append(RoleBid(
        player_id="host", player_name="Host",
        amount=100.0, timestamp=time.time(),
    ))
    room.auction.budget_spent["host"] = 100.0
    mgr.rooms[room.room_id] = room
    mgr._ws_connections[room.room_id] = {}
    mgr._loop = None  # no event loop — _delayed_investing_start won't fire
    return room


# ---------------------------------------------------------------------------
# Bug 1 — reconnect-during-resolution race
# ---------------------------------------------------------------------------

def test_resolve_auction_saves_result_payload_on_auction_state():
    """Without the saved payload, a reconnect during the post-resolution
    window has nothing to replay."""
    mgr = GameManager()
    room = _make_running_room_with_active_auction(mgr)
    assert room.auction.result_payload is None

    mgr._resolve_auction(room.room_id)

    assert room.auction.phase == "complete"
    assert room.auction.result_payload is not None
    assert room.auction.result_payload["type"] == "auction_result"
    # Banker assignment we seeded should be reflected in the payload.
    assignments = room.auction.result_payload["assignments"]
    assert assignments.get("Banker", {}).get("player_id") == "host"


def test_result_payload_is_carryable_across_reconnect():
    """The saved payload is the same shape as the broadcast — the
    reconnect handler can ``send_text(json.dumps(...))`` it directly."""
    mgr = GameManager()
    room = _make_running_room_with_active_auction(mgr)
    mgr._resolve_auction(room.room_id)

    payload = room.auction.result_payload
    # Required top-level keys the client's showAuctionResult reads.
    assert set(payload).issuperset({"type", "assignments", "ai_roles", "deductions"})
    # Deductions are per-player-id dollop totals.
    assert payload["deductions"]["host"] == 100.0


# ---------------------------------------------------------------------------
# Bug 2 — pause + resume at auction expiry
# ---------------------------------------------------------------------------

def test_resume_calls_resolve_when_auction_already_expired_during_pause():
    """If the pause happened right at or after the original auction
    expiry, the resume math gives ``remaining <= 0`` and the old code
    skipped the reschedule — leaving the auction frozen.  Now resume
    calls ``_resolve_auction`` directly so the next-phase transition
    fires."""
    mgr = GameManager()
    room = _make_running_room_with_active_auction(mgr)
    # Force the auction to look like it expired AT the pause moment:
    # set timer_end to exactly now, then immediately pause, then resume.
    now = time.time()
    room.auction.timer_end = now
    room.paused = True
    room.paused_at = now    # zero pause duration → remaining stays 0

    # Sanity: auction not yet resolved before resume.
    assert room.auction.phase == "bidding"

    mgr._do_resume(room)

    # After resume the resolution should have been called inline.
    assert room.auction.phase == "complete", (
        "Auction must resolve on resume when remaining<=0; otherwise "
        "the room sits at timer 0 with no Continue button."
    )
    assert room.auction.result_payload is not None


def test_resume_does_not_re_resolve_an_already_complete_auction():
    """If the auction already resolved (e.g. the timer fired before
    pause) and we then pause+resume, the resume must NOT re-run
    resolution."""
    mgr = GameManager()
    room = _make_running_room_with_active_auction(mgr)
    mgr._resolve_auction(room.room_id)
    saved_payload = room.auction.result_payload
    assert room.auction.phase == "complete"

    # Pause / resume cycle with the auction already complete.
    now = time.time()
    room.auction.timer_end = now - 1.0   # well past
    room.paused = True
    room.paused_at = now

    mgr._do_resume(room)

    # phase + payload preserved; not re-rolled.
    assert room.auction.phase == "complete"
    assert room.auction.result_payload is saved_payload


def test_resume_still_reschedules_when_time_remains():
    """Sanity: the happy path (pause with real time remaining) still
    bumps the end-epoch and the reschedule branch runs.  Without an
    event loop we can't actually verify the task was scheduled, but we
    can verify the auction was NOT prematurely resolved."""
    mgr = GameManager()
    room = _make_running_room_with_active_auction(mgr)
    now = time.time()
    room.auction.timer_end = now + 30.0    # 30s left at pause
    room.paused = True
    room.paused_at = now

    mgr._do_resume(room)

    # No premature resolution.
    assert room.auction.phase == "bidding"
    assert room.auction.result_payload is None
