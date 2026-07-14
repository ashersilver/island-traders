"""Multi-channel chat: room channel, private group channels, visibility."""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from island_traders.server.app import (
    GameManager, GameRoom, LobbyPlayer, ROOM_CHANNEL_ID, CHAT_TEXT_MAX,
)


def _bootstrap():
    mgr = GameManager()
    room = GameRoom(
        room_id="chatroom", name="Chat", max_players=4, num_years=1,
        is_public=True, join_code="CHT1",
    )
    room.players = [
        LobbyPlayer(player_id="pA", name="Alice", role_names=["Farmer"], is_human=True),
        LobbyPlayer(player_id="pB", name="Bob", role_names=["Banker"], is_human=True),
        LobbyPlayer(player_id="pC", name="Cara", role_names=["Doctor"], is_human=True),
        LobbyPlayer(player_id="pAI", name="Digger", role_names=["Miner"], is_human=False),
    ]
    room.status = "running"
    mgr.rooms[room.room_id] = room
    mgr._ws_connections[room.room_id] = {}
    return mgr, room


def test_room_message_history_and_recipients_exclude_ai():
    mgr, room = _bootstrap()
    mgr.handle_chat(room.room_id, "pA", {"text": "hello room"})
    ch = room.chat_channels[ROOM_CHANNEL_ID]
    assert [m["text"] for m in ch.history] == ["hello room"]
    assert ch.history[-1]["from"] == "Alice"
    # Room channel reaches every human seat; the AI seat is excluded.
    assert set(mgr._chat_recipients(room, ch)) == {"pA", "pB", "pC"}


def test_private_channel_isolates_non_members():
    mgr, room = _bootstrap()
    mgr.handle_chat_create_channel(room.room_id, "pA", {"topic": "Plan", "participants": ["Bob"]})
    priv = next(c for c in room.chat_channels.values() if not c.is_room)
    assert priv.participants == {"pA", "pB"}
    assert set(mgr._chat_recipients(room, priv)) == {"pA", "pB"}

    # A member can post; a non-member (Cara) cannot.
    mgr.handle_chat(room.room_id, "pA", {"channel_id": priv.channel_id, "text": "psst"})
    mgr.handle_chat(room.room_id, "pC", {"channel_id": priv.channel_id, "text": "let me in"})
    assert [m["text"] for m in priv.history] == ["psst"]


def test_visibility_room_plus_own_private_channels():
    mgr, room = _bootstrap()
    mgr.handle_chat_create_channel(room.room_id, "pA", {"topic": "Plan", "participants": ["Bob"]})
    priv_id = next(c.channel_id for c in room.chat_channels.values() if not c.is_room)

    def ids(viewer):
        return {c["channel_id"] for c in mgr._chat_visible_channels(room, viewer)}

    assert ids("pA") == {ROOM_CHANNEL_ID, priv_id}   # member sees both
    assert ids("pB") == {ROOM_CHANNEL_ID, priv_id}
    assert ids("pC") == {ROOM_CHANNEL_ID}            # non-member sees only room


def test_spectator_of_ai_sees_ai_private_channel():
    # A spectator polls game_state with the watched seat's id, so visibility for
    # the AI's id must include channels that AI participates in.
    mgr, room = _bootstrap()
    mgr.handle_chat_create_channel(room.room_id, "pB", {"topic": "Deal", "participants": ["Digger"]})
    priv_id = next(c.channel_id for c in room.chat_channels.values() if not c.is_room)
    seen = {c["channel_id"] for c in mgr._chat_visible_channels(room, "pAI")}
    assert seen == {ROOM_CHANNEL_ID, priv_id}


def test_mentions_parsed_and_text_capped():
    mgr, room = _bootstrap()
    mgr.handle_chat(room.room_id, "pA", {"text": "hey @Bob and @Nobody"})
    last = room.chat_channels[ROOM_CHANNEL_ID].history[-1]
    assert last["mentions"] == ["Bob"]            # only real player names

    mgr.handle_chat(room.room_id, "pA", {"text": "x" * (CHAT_TEXT_MAX + 50)})
    assert len(room.chat_channels[ROOM_CHANNEL_ID].history[-1]["text"]) == CHAT_TEXT_MAX

    before = len(room.chat_channels[ROOM_CHANNEL_ID].history)
    mgr.handle_chat(room.room_id, "pA", {"text": "   "})   # empty after strip
    assert len(room.chat_channels[ROOM_CHANNEL_ID].history) == before


def test_create_channel_needs_a_second_member():
    mgr, room = _bootstrap()
    mgr.handle_chat_create_channel(room.room_id, "pA", {"topic": "Solo", "participants": []})
    assert not any(not c.is_room for c in room.chat_channels.values())
