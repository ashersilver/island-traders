"""TEST/DEBUG affordance: role-keyed starting-workforce overrides at launch.

Scenario seeding (launcher scenarios): a debug room can replace a role's
default STARTING_WORKFORCE / STARTING_WORKERS_BY_PROFESSION breakdown with an
exact, unscaled list of {profession, count, specialty?} entries. Profession
and specialty names match case-insensitively with spaces/underscores ignored;
roles not listed keep the normal default; non-debug rooms are unaffected.
"""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from island_traders.server.app import GameManager, GameRoom, LobbyPlayer


def _room(mgr: GameManager, room_id: str, debug_wf=None, role="Farmer") -> str:
    room = GameRoom(
        room_id=room_id, name="Test", max_players=7, num_years=1,
        is_public=True, join_code=room_id[:6].upper().ljust(6, "Z"),
        starting_capital=1500.0,
        debug_starting_workforce=dict(debug_wf or {}),
    )
    room.players.append(LobbyPlayer(player_id="h1", name="Solo"))
    room.players[0].role_names = [role]
    mgr.rooms[room_id] = room
    mgr._loop = None
    return room_id


def _workers(mgr: GameManager, rid: str):
    return mgr.rooms[rid].game.players[0].workforce.workers


def test_workforce_override_replaces_default_breakdown_exactly():
    mgr = GameManager()
    rid = _room(mgr, "wfroom000", debug_wf={
        "Farmer": [
            {"profession": "farming technician", "count": 3},
            {"profession": "Unskilled", "count": 2},
        ],
    })
    mgr._launch_game(rid, bids={"h1": 400.0}, capital_spend={"h1": 0.0})
    workers = _workers(mgr, rid)
    assert len(workers) == 5
    by_prof: dict[str, int] = {}
    for w in workers:
        by_prof[w.profession] = by_prof.get(w.profession, 0) + 1
    # "farming technician" resolves to the FarmingTechnician profession value.
    assert by_prof == {"FarmingTechnician": 3, "Unskilled": 2}
    levels = {w.profession: w.training_level for w in workers}
    assert levels["FarmingTechnician"] == 1
    assert levels["Unskilled"] == 0


def test_engineer_specialty_is_seeded():
    mgr = GameManager()
    rid = _room(mgr, "wfroom001", debug_wf={
        "Farmer": [
            {"profession": "Engineer", "count": 2, "specialty": "industrial"},
        ],
    })
    mgr._launch_game(rid, bids={"h1": 400.0}, capital_spend={"h1": 0.0})
    workers = _workers(mgr, rid)
    assert len(workers) == 2
    assert all(w.profession == "Engineer" for w in workers)
    assert all(w.engineer_specialty == "Industrial" for w in workers)


def test_unknown_profession_skipped_not_fatal_and_default_untouched():
    mgr = GameManager()
    ctrl = _room(mgr, "wfctrl002")
    mgr._launch_game(ctrl, bids={"h1": 400.0}, capital_spend={"h1": 0.0})
    baseline = len(_workers(mgr, ctrl))

    # Unknown profession entries are dropped; valid ones still seed.
    rid = _room(mgr, "wfroom002", debug_wf={
        "Farmer": [
            {"profession": "NotAProfession", "count": 9},
            {"profession": "Farmer", "count": 1},
        ],
    })
    mgr._launch_game(rid, bids={"h1": 400.0}, capital_spend={"h1": 0.0})
    assert len(_workers(mgr, rid)) == 1

    # Override keyed to another role leaves this player's default intact.
    other = _room(mgr, "wfroom003", debug_wf={
        "Miner": [{"profession": "Miner", "count": 1}],
    })
    mgr._launch_game(other, bids={"h1": 400.0}, capital_spend={"h1": 0.0})
    assert len(_workers(mgr, other)) == baseline
