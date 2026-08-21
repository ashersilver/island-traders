"""Server wiring for per-island dashboard tabs (#252).

`game_state` carries an `islands` breakdown for any player holding more than
one role, and every action option declares which island(s) it belongs to, so
the dashboard can render a tab as if that island were the only one held.
"""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from island_traders.cli.prompts import FakeIOAdapter
from island_traders.engine.game import Game, GameConfig, PlayerSpec
from island_traders.engine.turn import TurnAction
from island_traders.models.resource import ResourceType
from island_traders.server.app import GameManager, GameRoom, LobbyPlayer
from island_traders.server.ws_adapter import action_option_payload


def _bootstrap(mgr, host_roles, other_roles=("Farmer",)):
    room = GameRoom(
        room_id="iso1", name="Isolation", max_players=2, num_years=1,
        is_public=True, join_code="ISO001", creator_id="host",
    )
    room.players.append(
        LobbyPlayer(player_id="host", name="Host", role_names=list(host_roles))
    )
    room.players.append(
        LobbyPlayer(player_id="ai1", name="Robo",
                    role_names=list(other_roles), is_human=False)
    )
    room.status = "running"
    mgr.rooms[room.room_id] = room
    mgr._ws_connections[room.room_id] = {}
    mgr._loop = None

    game = Game(
        GameConfig(
            player_specs=[
                PlayerSpec(name="Host", role_names=list(host_roles), is_human=True),
                PlayerSpec(name="Robo", role_names=list(other_roles), is_human=False),
            ],
            num_years=1,
            starting_dollops=100.0,
        ),
        FakeIOAdapter(),
    )
    game.setup()
    room.game = game
    host, ai = game.players[0], game.players[1]
    room.lobby_to_engine_id = {"host": host.player_id, "ai1": ai.player_id}
    return room, host


def _host_payload(mgr, room):
    state = mgr.get_game_state(room.room_id, "host")
    assert state is not None
    return next(p for p in state["players"] if p["lobby_player_id"] == "host")


def test_multi_role_player_gets_one_entry_per_island():
    mgr = GameManager()
    room, host = _bootstrap(mgr, ["Miner", "Banker"])
    host.inventory = host.inventory.add(ResourceType.ORE, 9)
    ore_held = host.inventory.get(ResourceType.ORE)

    pd = _host_payload(mgr, room)
    assert [i["role"] for i in pd["islands"]] == ["Miner", "Banker"]

    miner = pd["islands"][0]
    banker = pd["islands"][1]
    # Ore is Mining stock, so the Banking tab must not show it.
    assert miner["inventory"].get("Ore", 0) == ore_held
    assert banker["inventory"].get("Ore", 0) == 0
    # Each island reports its own cash, headcount and plant.
    assert miner["treasury"] + banker["treasury"] == pytest.approx(pd["dollops"])
    assert (miner["workforce_count"] + banker["workforce_count"]
            == pd["workforce_count"])


def test_single_role_player_keeps_the_consolidated_view():
    mgr = GameManager()
    room, _host = _bootstrap(mgr, ["Miner"])
    assert _host_payload(mgr, room)["islands"] == []


def test_island_specific_actions_declare_their_island():
    mgr = GameManager()
    _room, host = _bootstrap(mgr, ["Miner", "Banker"])

    offer_loan = action_option_payload(TurnAction.OFFER_LOAN, host)
    assert offer_loan["roles"] == ["Banker"]

    # An action every island can take names none, so it shows on every tab.
    assert action_option_payload(TurnAction.MARKET_BUY, host)["roles"] == []
    assert action_option_payload(TurnAction.RECRUIT_WORKERS, host)["roles"] == []


def test_produce_options_name_the_island_that_makes_the_product():
    from island_traders.engine.events import EventResult
    from island_traders.engine.production import ProductionEngine

    mgr = GameManager()
    _room, host = _bootstrap(mgr, ["Miner", "Banker"])
    options = ProductionEngine().produce_menu_options(
        host, EventResult(event_name="Normal Season"), "Spring"
    )
    assert options, "expected at least one producible product"
    assert all(o["role"] in {"Miner", "Banker"} for o in options)
    assert {o["role"] for o in options} == {
        o["key"].split("|")[0] for o in options
    }
