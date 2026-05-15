"""Server-side tests for the Investing Phase + multi-role auction fix.

These tests instantiate the GameManager directly and exercise the
auction resolution + investing submit flow without going through
WebSockets / FastAPI.
"""
from __future__ import annotations

import time
import pytest

# Skip cleanly if FastAPI / uvicorn aren't available in the test env.
pytest.importorskip("fastapi")

from island_traders.server.app import (
    AuctionState, GameManager, LobbyPlayer, RoleBid,
)


def _make_room(manager: GameManager, num_humans: int = 2) -> str:
    """Create a room with `num_humans` human lobby players."""
    room_id = "testroom"
    # Start by directly populating a fresh room — bypass create_room/api flow.
    from island_traders.server.app import GameRoom
    room = GameRoom(
        room_id=room_id, name="Test", max_players=7, num_years=1,
        is_public=True, join_code="ZZZZZZ",
    )
    for i in range(num_humans):
        room.players.append(LobbyPlayer(
            player_id=f"h{i+1}", name=f"Human{i+1}",
        ))
    room.status = "auction"
    room.auction = AuctionState()
    manager.rooms[room_id] = room
    return room_id


def test_single_player_can_win_multiple_roles():
    """Regression: previously a player could only win one role.  Verify a
    high bidder takes every role they outbid."""
    mgr = GameManager()
    room_id = _make_room(mgr, num_humans=2)
    room = mgr.rooms[room_id]
    now = time.time()

    # Pre-populate bids: h1 outbids h2 on Farmer AND Miner; h2 wins Banker.
    room.auction.bids = {
        "Farmer":      [RoleBid("h1", "Human1", 50.0, now), RoleBid("h2", "Human2", 30.0, now)],
        "Miner":       [RoleBid("h1", "Human1", 40.0, now), RoleBid("h2", "Human2", 20.0, now)],
        "Banker":      [RoleBid("h2", "Human2", 60.0, now)],
        "Transporter": [],
        "Educator":    [],
        "Manufacturer":[],
        "Doctor":      [],
    }

    # Resolve.  We don't want the asyncio loop kick — just call it directly.
    mgr._loop = None
    mgr._resolve_auction(room_id)

    h1 = next(p for p in room.players if p.player_id == "h1")
    h2 = next(p for p in room.players if p.player_id == "h2")
    # h1 won Farmer + Miner (outbid h2 on both)
    assert "Farmer" in h1.role_names
    assert "Miner" in h1.role_names
    # h2 won Banker only
    assert h2.role_names == ["Banker"]


def test_investing_phase_initialises_with_mandatory_minimums():
    mgr = GameManager()
    room_id = _make_room(mgr, num_humans=1)
    room = mgr.rooms[room_id]
    h1 = room.players[0]
    h1.role_names = ["Farmer"]

    mgr._loop = None
    mgr._start_investing(room_id, deductions={"h1": 10.0})

    from island_traders.constants_capacity import MANDATORY_MINIMUM_INVESTMENT
    assert room.status == "investing"
    assert room.investing is not None
    expected = MANDATORY_MINIMUM_INVESTMENT["Farmer"]
    assert room.investing.selections["h1"] == expected
    assert "h1" not in room.investing.submitted   # human not auto-submitted


def test_investing_phase_ai_auto_submits():
    mgr = GameManager()
    room_id = _make_room(mgr, num_humans=1)
    room = mgr.rooms[room_id]
    room.players[0].role_names = ["Farmer"]
    # Add an AI player
    room.players.append(LobbyPlayer(
        player_id="ai1", name="AI1", role_names=["Miner"], is_human=False,
    ))

    mgr._loop = None
    mgr._start_investing(room_id, deductions={})
    assert "ai1" in room.investing.submitted        # AI auto-submitted
    assert "h1" not in room.investing.submitted     # Human still pending


def test_ai_lobby_player_keeps_identity_when_winning_a_role():
    """A named AI that wins a bid should retain their lobby identity rather
    than being replaced by a generic 'Role Island (AI)' placeholder."""
    mgr = GameManager()
    room_id = _make_room(mgr, num_humans=1)
    room = mgr.rooms[room_id]
    # Add a named AI
    room.players.append(LobbyPlayer(
        player_id="ai1", name="Ada Bot", is_human=False,
    ))
    room.auction.budget_spent["ai1"] = 0.0
    now = time.time()
    # Ada Bot bids highest on Banker
    room.auction.bids = {role: [] for role in
                          ["Farmer","Miner","Transporter","Educator",
                           "Banker","Manufacturer","Doctor"]}
    room.auction.bids["Banker"] = [RoleBid("ai1", "Ada Bot", 100.0, now)]

    mgr._loop = None
    mgr._resolve_auction(room_id)

    ada = next(p for p in room.players if p.player_id == "ai1")
    assert ada.role_names == ["Banker"]
    assert ada.name == "Ada Bot"   # identity preserved
    # Should NOT have a duplicate "Banker Island (AI)" placeholder
    bankers = [p for p in room.players if "Banker" in p.role_names]
    assert len(bankers) == 1


def test_ai_without_winning_bid_absorbs_unclaimed_role():
    """Named AI that loses every bid should still be placed at an island
    (absorbing a leftover unclaimed role) instead of being orphaned."""
    mgr = GameManager()
    room_id = _make_room(mgr, num_humans=1)
    room = mgr.rooms[room_id]
    h1 = room.players[0]
    # Add a named AI that doesn't bid (no bids registered)
    room.players.append(LobbyPlayer(
        player_id="ai1", name="Ben Bot", is_human=False,
    ))
    room.auction.budget_spent["ai1"] = 0.0
    now = time.time()
    # Human wins Banker outright; everything else is unclaimed
    room.auction.bids = {role: [] for role in
                          ["Farmer","Miner","Transporter","Educator",
                           "Banker","Manufacturer","Doctor"]}
    room.auction.bids["Banker"] = [RoleBid("h1", "Human1", 50.0, now)]

    mgr._loop = None
    mgr._resolve_auction(room_id)

    # Ben should have absorbed one of the unclaimed roles
    ben = next(p for p in room.players if p.player_id == "ai1")
    assert len(ben.role_names) == 1
    assert ben.role_names[0] != "Banker"   # human got that one


def test_idle_human_absorbs_unclaimed_role_before_ai():
    """Humans who leave the auction without a winning bid should receive an
    unclaimed role before idle AIs, otherwise they can get stuck outside the
    investing/game flow."""
    mgr = GameManager()
    room_id = _make_room(mgr, num_humans=2)
    room = mgr.rooms[room_id]
    room.players.append(LobbyPlayer(
        player_id="ai1", name="Ben Bot", is_human=False,
    ))
    now = time.time()
    room.auction.bids = {role: [] for role in
                          ["Farmer","Miner","Transporter","Educator",
                           "Banker","Manufacturer","Doctor"]}
    room.auction.bids["Banker"] = [RoleBid("h1", "Human1", 50.0, now)]

    mgr._loop = None
    mgr._resolve_auction(room_id)

    h2 = next(p for p in room.players if p.player_id == "h2")
    ai = next(p for p in room.players if p.player_id == "ai1")
    assert h2.role_names == ["Farmer"]
    assert ai.role_names == ["Miner"]


def test_require_all_human_rejects_ai_won_role():
    mgr = GameManager()
    room_id = _make_room(mgr, num_humans=1)
    room = mgr.rooms[room_id]
    room.require_all_human = True
    room.players.append(LobbyPlayer(
        player_id="ai1", name="Ada Bot", is_human=False,
    ))
    now = time.time()
    room.auction.bids = {role: [RoleBid("h1", "Human1", 10.0, now)]
                         for role in ["Farmer","Miner","Transporter","Educator",
                                      "Manufacturer","Doctor"]}
    room.auction.bids["Banker"] = [RoleBid("ai1", "Ada Bot", 100.0, now)]

    mgr._loop = None
    mgr._resolve_auction(room_id)

    assert room.status == "auction"
    assert room.auction.phase == "bidding"
    assert not any("Banker" in p.role_names for p in room.players)


def test_join_room_rejects_after_auction_starts():
    mgr = GameManager()
    room = mgr.create_room("Test", creator_name="Host")
    assert mgr.start_auction(room.room_id)

    assert mgr.join_room(room.room_id, "Late Player") is None


def test_rejoin_room_by_name_allows_existing_player_after_auction_starts():
    mgr = GameManager()
    room = mgr.create_room("Test", creator_name="Host")
    original_id = room.players[0].player_id
    assert mgr.start_auction(room.room_id)

    rejoined = mgr.rejoin_room_by_name(room.room_id, "host")

    assert rejoined is not None
    _, lp = rejoined
    assert lp.player_id == original_id


def test_rejoin_room_by_name_preserves_existing_player_name_without_duplicate():
    mgr = GameManager()
    room = mgr.create_room("Test", creator_name="Ashley")
    original_id = room.players[0].player_id
    room.status = "running"

    rejoined = mgr.rejoin_room_by_name(room.room_id, "ashley")

    assert rejoined is not None
    _, lp = rejoined
    assert lp.player_id == original_id
    assert lp.name == "Ashley"
    assert [p.name for p in room.players] == ["Ashley"]


def test_investing_resolution_waits_only_for_role_holding_humans():
    mgr = GameManager()
    room_id = _make_room(mgr, num_humans=2)
    room = mgr.rooms[room_id]
    room.players[0].role_names = ["Farmer"]
    room.players[1].role_names = []

    mgr._loop = None
    mgr._start_investing(room_id, deductions={})

    result = mgr.submit_investment(
        room_id, "h1",
        item_ids=list(room.investing.selections["h1"]),
        ready=True,
    )

    assert result["ok"] is True
    assert room.status == "running"
    assert room.lobby_to_engine_id == {"h1": 0}


def test_opening_investment_delayed_items_are_available_immediately():
    mgr = GameManager()
    room_id = _make_room(mgr, num_humans=1)
    room = mgr.rooms[room_id]
    room.players[0].role_names = ["Farmer"]

    mgr._loop = None
    mgr._start_investing(room_id, deductions={})
    result = mgr.submit_investment(
        room_id, "h1",
        item_ids=["farmer.harvester"],
        ready=True,
    )

    assert result["ok"] is True
    player = room.game.players[0]
    assert player.capital_count("farmer.harvester") == 1
    assert player.capital_in_transit == []


def test_investing_payload_supports_reconnect():
    mgr = GameManager()
    room_id = _make_room(mgr, num_humans=1)
    room = mgr.rooms[room_id]
    lp = room.players[0]
    lp.role_names = ["Farmer"]

    mgr._loop = None
    mgr._start_investing(room_id, deductions={"h1": 25.0})
    payload = mgr._investing_payload(room, lp)

    assert payload["type"] == "investing_start"
    assert payload["budget"] == room.starting_capital - 25.0
    assert payload["roles"] == ["Farmer"]
    assert payload["catalogue"]
    assert payload["timer_seconds"] > 0


def test_player_capacity_returns_per_output_data():
    """Verify _player_capacity computes equipment / workforce / input caps
    and surfaces capital portfolio + binding constraint."""
    from island_traders.models.player import Player
    from island_traders.models.role import ROLES
    from island_traders.models.profession import Profession
    from island_traders.models.resource import ResourceType

    p = Player(
        player_id=0, name="Test Farmer", roles=[ROLES["Farmer"]],
        dollops=100.0,
    )
    # Capital: 1 Tractor (100 Food cap), 1 Fishing Boat (40 Fish cap)
    p.add_capital("farmer.tractor", 1)
    p.add_capital("farmer.fishing_boat", 1)
    # Workforce: 1 Manager + 1 Technician + 3 Workers
    p.workforce.add_workers(1, training_level=1, profession=Profession.FARMER.value)
    p.workforce.add_workers(1, training_level=1, profession=Profession.MECHANIC.value)
    p.workforce.add_workers(3, profession=Profession.UNSKILLED.value)
    # Inputs: enough Oil for Food and Fish
    p.receive_resources(ResourceType.OIL, 30)
    p.receive_resources(ResourceType.FISH, 5)

    mgr = GameManager()
    cap = mgr._player_capacity(p)

    # Should report both Food and Fish outputs (Farmer recipes)
    output_names = {o["output"] for o in cap["outputs"]}
    assert "Food" in output_names
    assert "Fish" in output_names

    # Capital portfolio includes both items
    owned_ids = {it["item_id"] for it in cap["capital_owned"]}
    assert "farmer.tractor" in owned_ids
    assert "farmer.fishing_boat" in owned_ids

    # Workforce band counts surfaced
    bands = cap["band_counts"]
    assert bands["Manager"] == 1
    assert bands["Technician"] == 1
    assert bands["Worker"] == 3

    food = next(o for o in cap["outputs"] if o["output"] == "Food")
    assert food["binding"] == "workforce"
    assert food["blockers"] == ["workforce"]
    # Shortage labels now use profession-specific titles (2026-05-15 playtest
    # change) rather than generic band names — for the Farmer the primary
    # Technician title is "Farming Technician" and the Worker is "Farmhand".
    assert food["workforce_short"] == {"Farming Technician": 3.0, "Farmhand": 7.0}

    fish = next(o for o in cap["outputs"] if o["output"] == "Fish")
    assert fish["binding"] == "workforce"
    assert fish["inputs_short"] == {}


def test_player_capacity_surfaces_equipment_shortfall_options():
    from island_traders.models.player import Player
    from island_traders.models.role import ROLES
    from island_traders.models.profession import Profession
    from island_traders.models.resource import ResourceType

    p = Player(
        player_id=0, name="Underbuilt Farmer", roles=[ROLES["Farmer"]],
        dollops=100.0,
    )
    p.workforce.add_workers(1, training_level=1, profession=Profession.FARMER.value)
    p.workforce.add_workers(1, training_level=1, profession=Profession.MECHANIC.value)
    p.workforce.add_workers(3, profession=Profession.UNSKILLED.value)
    p.receive_resources(ResourceType.OIL, 30)
    p.receive_resources(ResourceType.FISH, 5)

    cap = GameManager()._player_capacity(p)
    food = next(o for o in cap["outputs"] if o["output"] == "Food")

    assert food["binding"] == "equipment"
    assert food["blockers"] == ["equipment"]
    assert food["equipment_short"]["needed_capacity"] == 25.0
    assert food["equipment_short"]["options"][0]["item_id"] == "farmer.tractor"
    assert food["equipment_short"]["options"][0]["count"] == 1


def test_player_capacity_surfaces_capital_orders_with_arrival_timing():
    from island_traders.models.player import Player
    from island_traders.models.role import ROLES

    p = Player(
        player_id=0, name="Ordering Farmer", roles=[ROLES["Farmer"]],
        dollops=100.0,
    )
    p.capital_in_transit.append({
        "item_id": "farmer.harvester",
        "arrives_at_tick": 2,
    })

    cap = GameManager()._player_capacity(p, current_tick=0)
    order = cap["capital_in_transit"][0]

    assert order["name"] == "Harvester"
    assert order["role"] == "Farmer"
    assert order["arrival_year"] == 1
    assert order["arrival_season"] == "Autumn"
    assert order["seasons_remaining"] == 2


def test_game_state_includes_worker_band_counts_for_each_player():
    from types import SimpleNamespace

    from island_traders.models.deal import DealLedger
    from island_traders.models.loan import LoanLedger
    from island_traders.models.market import Market
    from island_traders.models.player import Player
    from island_traders.models.profession import Profession
    from island_traders.models.role import ROLES
    from island_traders.server.app import GameRoom

    mgr = GameManager()
    room = GameRoom(
        room_id="bands", name="Bands", max_players=2, num_years=1,
        is_public=True, join_code="BANDS1",
    )
    room.status = "running"
    room.players = [
        LobbyPlayer(player_id="h1", name="Banker", role_names=["Banker"]),
        LobbyPlayer(player_id="h2", name="Farmer", role_names=["Farmer"]),
    ]
    player = Player(0, "Banker", [ROLES["Banker"]], 100.0)
    player.workforce.add_workers(1, training_level=1, profession=Profession.BANKER.value)
    player.workforce.add_workers(2, training_level=1, profession=Profession.MECHANIC.value)
    player.workforce.add_workers(3, profession=Profession.UNSKILLED.value)
    room.game = SimpleNamespace(
        players=[player],
        market=Market(),
        ledger=DealLedger(),
        loan_ledger=LoanLedger(),
    )
    room.lobby_to_engine_id = {"h1": 0}
    mgr.rooms[room.room_id] = room

    state = mgr.get_game_state(room.room_id, "h1")

    assert state["funding_rates"] == {"1": 4.5, "2": 5.25, "3": 6.0}
    assert state["players"][0]["workforce_bands"] == {
        "Manager": 1,
        "Technician": 2,
        "Worker": 3,
    }


def test_submit_investment_updates_selections_and_ready_state():
    mgr = GameManager()
    room_id = _make_room(mgr, num_humans=1)
    room = mgr.rooms[room_id]
    room.players[0].role_names = ["Farmer"]

    mgr._loop = None
    mgr._start_investing(room_id, deductions={})

    # Select a different set of items.  Server validates against the role.
    result = mgr.submit_investment(
        room_id, "h1",
        item_ids=["farmer.tractor", "farmer.fishing_boat", "miner.excavator"],   # last one wrong role
        ready=False,
    )
    assert result["ok"] is True
    # Wrong-role item is filtered out
    assert "miner.excavator" not in room.investing.selections["h1"]
    assert "farmer.tractor" in room.investing.selections["h1"]
    assert "h1" not in room.investing.submitted    # ready=False
