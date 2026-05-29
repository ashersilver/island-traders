"""Server-side test: workforce shortage messages name specific professions.

Playtest 2026-05-15 feedback: the constraint popup said "+2 Technicians"
which doesn't help the player know who to recruit/train.  The payload
should instead say "+2 Flight Crew" (or whatever the primary technician
title is for that island).
"""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from island_traders.server.app import GameManager, GameRoom, LobbyPlayer


def _bootstrap_running_game(mgr, role_names=("Banker", "Transporter")):
    from island_traders.engine.game import Game, GameConfig, PlayerSpec
    from island_traders.cli.prompts import FakeIOAdapter
    room = GameRoom(
        room_id="r1", name="Test", max_players=len(role_names), num_years=1,
        is_public=True, join_code="WFSHRT", creator_id="host",
    )
    for i, role in enumerate(role_names):
        room.players.append(LobbyPlayer(
            player_id=f"p{i}", name=f"Player{i}", role_names=[role]
        ))
    room.status = "running"
    mgr.rooms["r1"] = room
    mgr._ws_connections["r1"] = {}
    mgr._loop = None

    config = GameConfig(
        player_specs=[
            PlayerSpec(name=f"Player{i}", role_names=[role], is_human=True)
            for i, role in enumerate(role_names)
        ],
        num_years=1,
        starting_dollops=100.0,
    )
    game = Game(config, FakeIOAdapter())
    game.setup()
    room.game = game
    for i, p in enumerate(game.players):
        room.lobby_to_engine_id[f"p{i}"] = p.player_id
    return room, game


def test_workforce_shortage_labels_use_profession_titles_not_band_names():
    """When the Transporter has too few Technicians, the constraint payload
    should list the *primary* Technician profession for Transporter
    ("Flight Crew") — NOT the generic band name "Technician"."""
    mgr = GameManager()
    room, game = _bootstrap_running_game(mgr, role_names=("Transporter",))

    transporter = game.players[0]
    # Strip the workforce down so EVERY band is below the labour requirement
    # — this guarantees workforce_short will appear in the capacity payload.
    transporter.workforce.workers = []

    state = mgr.get_game_state(room.room_id, "p0")
    assert state is not None

    transporter_data = next(
        p for p in state["players"] if p["lobby_player_id"] == "p0"
    )
    capacity = transporter_data.get("capacity") or {}
    outputs = capacity.get("outputs") or []
    # Find at least one output with a workforce shortfall reported.
    found_profession_label = False
    saw_generic_band_name = False
    for out in outputs:
        for label in (out.get("workforce_short") or {}).keys():
            if label in ("Manager", "Technician", "Worker"):
                saw_generic_band_name = True
            if label in (
                "Logistics Manager", "Engineer",          # Manager-tier titles
                "Flight Crew", "Seaman",
                "Warehouse Manager", "Mechanic",          # Technician-tier titles
                "Stevedore",                              # Worker-tier title
            ):
                found_profession_label = True

    assert found_profession_label, (
        "Expected workforce_short to use specific Transporter profession names "
        "(Logistics Manager / Flight Crew / Seaman / Warehouse Manager / "
        "Stevedore), got nothing of the sort"
    )
    assert not saw_generic_band_name, (
        "workforce_short should NOT contain generic band names "
        "(Manager / Technician / Worker)"
    )


def test_banker_shortage_uses_banker_specific_titles():
    """Banker-island shortages should name 'Banker' / 'Banking Analyst' /
    'Receptionist', not generic bands."""
    mgr = GameManager()
    room, game = _bootstrap_running_game(mgr, role_names=("Banker",))

    banker = game.players[0]
    banker.workforce.workers = []

    state = mgr.get_game_state(room.room_id, "p0")
    banker_data = next(
        p for p in state["players"] if p["lobby_player_id"] == "p0"
    )
    capacity = banker_data.get("capacity") or {}
    outputs = capacity.get("outputs") or []
    labels_seen = set()
    for out in outputs:
        labels_seen.update((out.get("workforce_short") or {}).keys())

    # Should NOT include band names
    assert "Manager" not in labels_seen
    assert "Technician" not in labels_seen
    # Should include at least one Banker-specific title if there's any
    # workforce shortfall at all.  (The InsurancePolicies recipe needs
    # Managers + Technicians, so with workforce==[] we expect shortfalls.)
    if labels_seen:
        assert labels_seen.issubset({
            "Banker", "Banking Analyst", "Banking Clerk", "Receptionist",
        }), f"unexpected Banker-island shortage labels: {labels_seen}"
