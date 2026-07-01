from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from island_traders.cli.prompts import FakeIOAdapter
from island_traders.engine.game import Game, GameConfig, PlayerSpec
from island_traders.server.app import GameManager, GameRoom, LobbyPlayer


def test_active_humans_uses_engine_roles_when_lobby_role_names_are_stale():
    mgr = GameManager()
    room = GameRoom(
        room_id="active-humans",
        name="Active Humans",
        max_players=2,
        num_years=1,
        is_public=True,
        join_code="AH1",
    )
    room.players = [
        LobbyPlayer(player_id="p0", name="A", role_names=[]),
        LobbyPlayer(player_id="p1", name="B", role_names=["Doctor"]),
    ]
    game = Game(
        GameConfig([
            PlayerSpec("A", ["Farmer"]),
            PlayerSpec("B", ["Doctor"]),
        ]),
        FakeIOAdapter(),
    )
    game.setup()
    room.game = game
    room.lobby_to_engine_id = {"p0": 0, "p1": 1}

    assert mgr._active_human_lobby_ids(room) == {"p0", "p1"}
