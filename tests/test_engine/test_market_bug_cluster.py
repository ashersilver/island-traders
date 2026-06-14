"""Tests for the 2026-05-27 market-bug-cluster brief.

Three reported defects:

1. Bid price display vs commit consistency (Comet #6: "Food showed
   17.18 but the bid was calculated at 40.00/unit").  Root cause was
   client-side: the Place-Bid field prefilled with the resting ask
   price instead of the formula/reference price.  Fixed in the
   dashboard; the engine side here just pins that market_summary
   exposes formula_price distinctly from ask_price so the client has
   the right number to prefill with.

2. Same-price Bid + Ask not crossing (Comet #8: FarmMachinery Ask 9 +
   Bid 9 "never crossed").  The engine matching is actually correct —
   these tests pin same-price crossing in BOTH post orders so the
   behaviour can't regress.  The reported symptom was a stale-board
   display artifact, not an engine bug.

3. Stale "buy food" sustenance hint (Codex Player: hint said buy food
   with no asks on the market, and stayed after a bid was posted).
   Fixed by adding market_has_supply / player_has_pending_bid context
   flags to the sustenance alert payload — tested via the server
   game-state payload.
"""
from __future__ import annotations

import pytest

from island_traders.models.market import Market
from island_traders.models.player import Player
from island_traders.models.resource import ResourceType
from island_traders.models.role import ROLES


def _mkt() -> Market:
    m = Market()
    m.set_season(0, 0)
    return m


# ─────────────────────────────────────────────────────────────────────────
# Bug #2 — same-price crossing (engine is correct; pin it)
# ─────────────────────────────────────────────────────────────────────────


def test_same_price_bid_then_ask_crosses():
    """Bid posted first, then a same-price Ask arrives — they cross."""
    m = _mkt()
    buyer = Player(1, "Farmer", [ROLES["Farmer"]], 1000.0, is_human=True)
    seller = Player(2, "Manufacturer", [ROLES["Manufacturer"]], 0.0, is_human=True)
    seller.receive_resources(ResourceType.FARM_MACHINERY, 6)

    bid = m.post_bid(buyer, ResourceType.FARM_MACHINERY, 9.0, 6)
    assert bid.remaining == 6  # nothing to cross yet
    ask = m.post_offer(seller, ResourceType.FARM_MACHINERY, 9.0, 6)

    assert ask.remaining == 0, "Same-price ask should fully cross the resting bid"
    assert bid.remaining == 0
    assert buyer.inventory.get(ResourceType.FARM_MACHINERY) == 0
    assert buyer.capital_count("farmer.tractor") == 6
    assert seller.dollops == pytest.approx(54.0)  # 6 × 9


def test_same_price_ask_then_bid_crosses():
    """Ask posted first, then a same-price Bid arrives — they cross."""
    m = _mkt()
    buyer = Player(1, "Farmer", [ROLES["Farmer"]], 1000.0, is_human=True)
    seller = Player(2, "Manufacturer", [ROLES["Manufacturer"]], 0.0, is_human=True)
    seller.receive_resources(ResourceType.FARM_MACHINERY, 6)

    ask = m.post_offer(seller, ResourceType.FARM_MACHINERY, 9.0, 6)
    assert ask.remaining == 6
    bid = m.post_bid(buyer, ResourceType.FARM_MACHINERY, 9.0, 6)

    assert ask.remaining == 0
    assert bid.remaining == 0
    assert buyer.inventory.get(ResourceType.FARM_MACHINERY) == 0
    assert buyer.capital_count("farmer.tractor") == 6


def test_bid_below_ask_does_not_cross():
    """A bid below the resting ask must NOT cross (sanity guard)."""
    m = _mkt()
    buyer = Player(1, "Farmer", [ROLES["Farmer"]], 1000.0, is_human=True)
    seller = Player(2, "Manufacturer", [ROLES["Manufacturer"]], 0.0, is_human=True)
    seller.receive_resources(ResourceType.FARM_MACHINERY, 6)

    m.post_offer(seller, ResourceType.FARM_MACHINERY, 9.0, 6)
    bid = m.post_bid(buyer, ResourceType.FARM_MACHINERY, 8.0, 6)
    assert bid.remaining == 6  # 8 < 9, no cross
    assert buyer.inventory.get(ResourceType.FARM_MACHINERY) == 0


# ─────────────────────────────────────────────────────────────────────────
# Bug #1 — market_summary exposes formula_price distinctly from ask
# ─────────────────────────────────────────────────────────────────────────


def test_market_summary_exposes_formula_price_distinct_from_ask():
    """The summary must carry formula_price (fair reference) separately
    from ask_price.  The dashboard prefills the Place-Bid field from
    formula_price, not the ask — so when a resting ask sits far above
    fair value, the bid field shows the reference not the ask (Comet
    #6 fix)."""
    m = _mkt()
    seller = Player(2, "Farmer", [ROLES["Farmer"]], 0.0, is_human=True)
    seller.receive_resources(ResourceType.FOOD, 3)
    # Post an ask far above the formula price.
    m.post_offer(seller, ResourceType.FOOD, 40.0, 3)

    summary = m.market_summary()
    food = summary[ResourceType.FOOD.value]
    assert food["ask_price"] == pytest.approx(40.0)
    # formula_price is the supply/demand reference, well below the 40 ask.
    assert food["formula_price"] is not None
    assert food["formula_price"] < 40.0, (
        f"formula_price ({food['formula_price']}) should reflect fair "
        f"value, distinct from the inflated 40 Dp ask"
    )


# ─────────────────────────────────────────────────────────────────────────
# Bug #3 — sustenance alert context flags
# ─────────────────────────────────────────────────────────────────────────


def _running_room_with_hungry_transporter(mgr, name):
    """Build a minimal running room with one human Transporter who has
    no sustenance on hand (runway 0).  Returns (room, transporter)."""
    from types import SimpleNamespace
    from island_traders.engine.production import ProductionEngine
    from island_traders.models.deal import DealLedger
    from island_traders.models.loan import LoanLedger
    from island_traders.models.training import TrainingRegistry

    room = mgr.create_room(
        name=name, max_players=2, num_years=1, creator_name="Host",
    )
    trans = Player(0, "Trans", [ROLES["Transporter"]], 200.0, is_human=True)
    # Drain any starting sustenance so runway < 2.
    for r in (ResourceType.FOOD, ResourceType.GRAIN, ResourceType.PRODUCE,
              ResourceType.FISH, ResourceType.MEAT):
        have = trans.inventory.get(r)
        if have > 0:
            trans.give_resources(r, have)
    market = _mkt()
    room.game = SimpleNamespace(
        players=[trans],
        market=market,
        ledger=DealLedger(),
        loan_ledger=LoanLedger(),
        training=TrainingRegistry(),
        turn_manager=SimpleNamespace(production=ProductionEngine()),
    )
    room.lobby_to_engine_id = {"h1": 0}
    room.status = "running"
    mgr.rooms[room.room_id] = room
    return room, trans, market


def test_sustenance_alert_flags_no_supply_when_market_empty():
    """When the player is short on meals and NO basket resource has a
    resting ask, the alert reports market_has_supply=False so the
    client suggests producing rather than buying."""
    pytest.importorskip("fastapi")
    from island_traders.server.app import GameManager

    mgr = GameManager()
    room, trans, _market = _running_room_with_hungry_transporter(mgr, "SustTest")

    state = mgr.get_game_state(room.room_id, "h1")
    alerts = state["sustenance_alerts"].get(str(trans.player_id), [])
    assert alerts, "Transporter with no food should raise a sustenance alert"
    alert = alerts[0]
    # No basket asks were posted, so the market has no food supply.
    assert alert["market_has_supply"] is False
    assert alert["player_has_pending_bid"] is False


def test_sustenance_alert_flags_pending_bid_when_player_has_bid():
    """When the hungry player already has a resting basket bid, the
    alert reports player_has_pending_bid=True so the client softens
    the 'buy food now' urgency."""
    pytest.importorskip("fastapi")
    from island_traders.server.app import GameManager

    mgr = GameManager()
    room, trans, market = _running_room_with_hungry_transporter(mgr, "SustTest2")
    # Player posts a Food bid.
    market.post_bid(trans, ResourceType.FOOD, 12.0, 5)

    state = mgr.get_game_state(room.room_id, "h1")
    alerts = state["sustenance_alerts"].get(str(trans.player_id), [])
    assert alerts
    assert alerts[0]["player_has_pending_bid"] is True


def test_sustenance_alert_flags_supply_when_ask_exists():
    """When a basket resource has a resting ask, market_has_supply is
    True so the client keeps the 'buy food' advice."""
    pytest.importorskip("fastapi")
    from island_traders.server.app import GameManager

    mgr = GameManager()
    room, trans, market = _running_room_with_hungry_transporter(mgr, "SustTest3")
    # A seller posts Food for sale.
    seller = Player(1, "Farmer", [ROLES["Farmer"]], 0.0, is_human=False)
    seller.receive_resources(ResourceType.FOOD, 10)
    market.post_offer(seller, ResourceType.FOOD, 12.0, 10)

    state = mgr.get_game_state(room.room_id, "h1")
    alerts = state["sustenance_alerts"].get(str(trans.player_id), [])
    assert alerts
    assert alerts[0]["market_has_supply"] is True
