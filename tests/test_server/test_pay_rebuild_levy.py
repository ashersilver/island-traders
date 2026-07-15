"""pay_rebuild_levy (Wave 5.1) — the disaster rebuild levy used to be a
dead end: it blocked capital repairs with a message pointing at a payment
action that did not exist, was never serialised to the client, and could
only drain away via automatic seasonal installments.  The new action lets
the player pay any/all of the outstanding levy from dollops (clamped to
balance) and unblocks repairs the same season it hits zero."""
from __future__ import annotations

import asyncio
import json

import pytest

pytest.importorskip("fastapi")

from island_traders.cli.prompts import FakeIOAdapter
from island_traders.constants import CURRENCY_SYMBOL
from island_traders.constants_capacity import CAPITAL_CATALOGUE
from island_traders.engine.events import EventResult
from island_traders.engine.game import Game, GameConfig, PlayerSpec
from island_traders.models.capacity import find_item
from island_traders.models.resource import ResourceType
from island_traders.server.app import GameManager, GameRoom, LobbyPlayer


class _WS:
    def __init__(self):
        self.sent = []

    async def send_text(self, text):
        self.sent.append(json.loads(text))


def _bootstrap(role_names: list[str]):
    mgr = GameManager()
    room = GameRoom(
        room_id="levy-room", name="Levy Room", max_players=len(role_names),
        num_years=1, is_public=True, join_code="LVY1",
    )
    room.players = [
        LobbyPlayer(player_id=f"p{idx}", name=f"Player{idx}", role_names=[role])
        for idx, role in enumerate(role_names)
    ]
    room.status = "running"
    mgr.rooms[room.room_id] = room
    mgr._ws_connections[room.room_id] = {}
    game = Game(
        GameConfig(
            [PlayerSpec(name=f"Player{idx}", role_names=[role], is_human=True)
             for idx, role in enumerate(role_names)],
            num_years=1, starting_dollops=1000.0,
        ),
        FakeIOAdapter(),
    )
    game.setup()
    room.game = game
    room.lobby_to_engine_id = {
        lobby.player_id: player.player_id
        for lobby, player in zip(room.players, game.players)
    }
    return mgr, room, game.players


def _pay(mgr, room, lobby_id, msg):
    ws = _WS()
    asyncio.run(mgr._handle_pay_rebuild_levy(room.room_id, lobby_id, msg, ws))
    return next(m for m in ws.sent if m.get("type") == "pay_rebuild_levy_ack")


def _book_levy(game, player) -> float:
    """Force a disaster that books a rebuild levy, then run the season-start
    installment collection so the levy becomes repair-blocking (the engine
    only refreshes ``_rebuild_levy_remaining`` there).  The player must own
    capital — the levy is a fraction of capital replacement value."""
    event = EventResult(
        event_name="Hurricane",
        natural_disaster=True,
        severity_enabled=True,
        severity="Major",
        rebuild_levy_fraction=0.10,
    )
    game._process_disaster_capital_impacts(0, 0, {player.player_id: event})
    game._process_rebuild_levy_payments(player)
    return getattr(player, "_rebuild_levy_remaining", 0.0)


def _add_failed_repairable_unit(player, item) -> None:
    player.add_capital(item.item_id, 1, acquired_tick=-4)
    player.capital_units[item.item_id][0].status = "failed"
    player.receive_resources(ResourceType.SPARES, item.capacity_units)
    player.receive_resources(ResourceType.FREIGHT, 5)


def test_pay_levy_unblocks_repair_same_season():
    mgr, room, players = _bootstrap(["Banker", "Farmer"])
    banker = players[0]
    game = room.game
    item = find_item(CAPITAL_CATALOGUE, "banker.underwriting_desk")
    _add_failed_repairable_unit(banker, item)

    remaining = _book_levy(game, banker)
    assert remaining > 0

    # Repairs are blocked, and the reason names the amount and both routes.
    preview = game.capital_repair_preview(banker, item.item_id)
    assert preview["repairable"] is False
    assert f"{CURRENCY_SYMBOL}{remaining:.2f}" in preview["reason"]
    assert "Pay Levy" in preview["reason"]
    assert "installments" in preview["reason"]

    # Pay the whole levy via the new action (no amount = pay everything).
    dollops_before = banker.dollops
    ack = _pay(mgr, room, "p0", {})
    assert ack["ok"] is True
    assert ack["paid"] == remaining
    assert ack["remaining"] == 0
    assert banker.dollops == round(dollops_before - remaining, 2)
    assert banker.rebuild_levy_outstanding() == 0

    # Repairs unblock the same season.
    preview = game.capital_repair_preview(banker, item.item_id)
    assert preview["repairable"] is True


def test_pay_levy_partial_amount_reduces_outstanding():
    mgr, room, players = _bootstrap(["Banker", "Farmer"])
    banker = players[0]
    banker.add_capital("banker.underwriting_desk", 2, acquired_tick=0)
    remaining = _book_levy(room.game, banker)
    assert remaining > 1

    ack = _pay(mgr, room, "p0", {"amount": 1.0})
    assert ack["ok"] is True
    assert ack["paid"] == 1.0
    assert ack["remaining"] == round(remaining - 1.0, 2)
    assert banker.rebuild_levy_outstanding() == round(remaining - 1.0, 2)


def test_pay_levy_clamped_to_treasury_balance():
    mgr, room, players = _bootstrap(["Banker", "Farmer"])
    banker = players[0]
    banker.add_capital("banker.underwriting_desk", 2, acquired_tick=0)
    remaining = _book_levy(room.game, banker)
    assert remaining > 5
    banker.dollops = 5.0

    ack = _pay(mgr, room, "p0", {"amount": remaining})
    assert ack["ok"] is True
    assert ack["paid"] == 5.0
    assert ack["remaining"] == round(remaining - 5.0, 2)
    assert banker.dollops == 0.0


def test_pay_levy_rejected_when_none_outstanding():
    mgr, room, players = _bootstrap(["Banker", "Farmer"])

    ack = _pay(mgr, room, "p0", {})

    assert ack["ok"] is False
    assert "No rebuild levy outstanding" in ack["message"]


def test_game_state_serialises_levy_fields():
    mgr, room, players = _bootstrap(["Banker", "Farmer"])
    banker = players[0]
    banker.add_capital("banker.underwriting_desk", 2, acquired_tick=0)
    remaining = _book_levy(room.game, banker)

    state = mgr.get_game_state(room.room_id, "p0")
    banker_state = next(
        p for p in state["players"] if p["player_id"] == banker.player_id
    )

    assert banker_state["rebuild_levy_remaining"] == remaining
    assert banker_state["rebuild_levy_installments"] == len(
        banker._rebuild_levy_installments
    )
    # Farmer has no levy — fields still present, zeroed.
    farmer_state = next(
        p for p in state["players"] if p["player_id"] == players[1].player_id
    )
    assert farmer_state["rebuild_levy_remaining"] == 0
    assert farmer_state["rebuild_levy_installments"] == 0
