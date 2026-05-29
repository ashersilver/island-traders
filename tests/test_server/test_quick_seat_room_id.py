"""Quick-seat playtest URLs: caller-specified (pinned) room IDs.

See requirements/playtest-quick-seat-urls.md.  Tabs 2-7 hash a shared room
name to a deterministic ``pt-`` room ID, so ``create_room`` must honour a
caller-supplied ID (and do so idempotently) for that prefix only.
"""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from island_traders.server.app import GameManager


def test_create_room_honours_pinned_pt_room_id():
    mgr = GameManager()
    room = mgr.create_room("Trading Hell", creator_name="Host", room_id="pt-abc123")
    assert room.room_id == "pt-abc123"
    assert mgr.rooms["pt-abc123"] is room


def test_create_room_with_pinned_id_is_idempotent():
    mgr = GameManager()
    first = mgr.create_room("Trading Hell", creator_name="Host", room_id="pt-abc123")
    # Re-creating the same pinned room returns the existing instance rather than
    # clobbering it — re-pasting tab 1 must not wipe seated players.
    second = mgr.create_room("Trading Hell", creator_name="Host", room_id="pt-abc123")
    assert first is second
    assert len(mgr.rooms) == 1


def test_create_room_ignores_non_pt_pinned_id():
    mgr = GameManager()
    room = mgr.create_room("Normal", creator_name="Host", room_id="hijack-me")
    # Non-``pt-`` overrides are ignored; a server-generated id is used instead.
    assert room.room_id != "hijack-me"
    assert room.room_id in mgr.rooms


def test_create_room_generates_id_when_none_given():
    mgr = GameManager()
    room = mgr.create_room("Normal", creator_name="Host")
    assert room.room_id
    assert room.room_id in mgr.rooms
