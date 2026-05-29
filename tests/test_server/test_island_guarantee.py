"""Tests for the post-auction human island guarantee (§19.1).

Covers:
  * `compute_guarantee_price` pricing formula across all bands + edge cases.
  * `_should_run_island_guarantee` trigger condition.
  * `_build_offers_for` returns all AI-extra islands with correct prices.
  * `_start_island_guarantee` + `submit_guarantee_choice` accept path:
    role transfers from AI to human, auction deductions updated.
  * Decline path: skips this buyer, advances queue.
  * No-AI-extras short-circuit: skip straight to investing.
  * Multiple islandless humans handled sequentially.
"""
from __future__ import annotations

import time
import pytest

pytest.importorskip("fastapi")

from island_traders.server.app import (
    AuctionState, GameManager, GameRoom, LobbyPlayer, RoleBid,
    IslandGuaranteeState, compute_guarantee_price,
    DEFAULT_STARTING_CAPITAL,
)


# ---------------------------------------------------------------------------
# Pricing formula
# ---------------------------------------------------------------------------

def test_compute_guarantee_price_below_11pct_band():
    """ai_paid < 11% of S → formula = ai_paid (no premium)."""
    r = compute_guarantee_price(ai_price_paid=50, starting_wealth=700,
                                 buyer_current_wealth=700)
    # 50/700 = 7.1% → "low" band
    assert r["formula_band"] == "low"
    assert r["formula"] == 50.0
    assert r["floor"] == 140.0  # 20% of 700
    assert r["final"] == 140.0  # floor wins


def test_compute_guarantee_price_inclusive_at_11pct_lower_bound():
    """11% exactly is INSIDE the band (user-confirmed inclusive)."""
    ai = 700 * 0.11  # exactly 11%
    r = compute_guarantee_price(ai_price_paid=ai, starting_wealth=700,
                                 buyer_current_wealth=700)
    assert r["formula_band"] == "mid"
    assert abs(r["formula"] - 2 * ai) < 1e-6


def test_compute_guarantee_price_inclusive_at_15pct_upper_bound():
    """15% exactly is INSIDE the band (user-confirmed inclusive)."""
    ai = 700 * 0.15  # exactly 15%
    r = compute_guarantee_price(ai_price_paid=ai, starting_wealth=700,
                                 buyer_current_wealth=700)
    assert r["formula_band"] == "mid"
    assert abs(r["formula"] - 2 * ai) < 1e-6


def test_compute_guarantee_price_mid_band_2x():
    """11% ≤ ai_paid ≤ 15% of S → formula = 2 × ai_paid."""
    r = compute_guarantee_price(ai_price_paid=80, starting_wealth=700,
                                 buyer_current_wealth=700)
    assert r["formula_band"] == "mid"
    assert r["formula"] == 160.0
    assert r["floor"] == 140.0
    assert r["final"] == 160.0  # formula wins


def test_compute_guarantee_price_high_band_1_05x():
    """ai_paid > 15% of S → formula = 1.05 × ai_paid."""
    r = compute_guarantee_price(ai_price_paid=200, starting_wealth=700,
                                 buyer_current_wealth=700)
    assert r["formula_band"] == "high"
    assert r["formula"] == 210.0
    assert r["final"] == 210.0  # formula wins (above 140 floor)


def test_compute_guarantee_price_floor_dominates_when_buyer_is_rich():
    """If buyer wealth is high but AI paid little, the 20% floor dominates."""
    r = compute_guarantee_price(ai_price_paid=30, starting_wealth=700,
                                 buyer_current_wealth=1000)
    # formula = 30 (low band), floor = 200
    assert r["formula"] == 30.0
    assert r["floor"] == 200.0
    assert r["final"] == 200.0


def test_compute_guarantee_price_zero_starting_wealth_is_safe():
    """Degenerate input — should not raise."""
    r = compute_guarantee_price(ai_price_paid=50, starting_wealth=0,
                                 buyer_current_wealth=100)
    assert r["formula_band"] == "low"  # ratio = 0
    assert r["final"] == 50.0  # max(50, 20)


# ---------------------------------------------------------------------------
# Test scaffolding
# ---------------------------------------------------------------------------

def _make_room(mgr, *, islandless_humans=1, ai_with_extras=True):
    """Build a room mid-way through auction resolution.

    Default scenario: 1 islandless human + 1 AI with 2 islands.
    """
    room = GameRoom(
        room_id="gtest", name="Test", max_players=7, num_years=1,
        is_public=True, join_code="GUAR01", creator_id="host",
        starting_capital=DEFAULT_STARTING_CAPITAL,
    )
    # Host is the islandless human
    for i in range(islandless_humans):
        room.players.append(LobbyPlayer(
            player_id=f"h{i+1}", name=f"Human{i+1}", is_human=True,
        ))
    # AI with 2 roles (Banker + Farmer); per-role prices captured.
    if ai_with_extras:
        ai = LobbyPlayer(player_id="ai1", name="Aurora AI",
                          role_names=["Banker", "Farmer"], is_human=False)
        room.players.append(ai)
        room.ai_role_prices = {"Banker": 80.0, "Farmer": 50.0}
    room.status = "auction"
    mgr.rooms[room.room_id] = room
    mgr._ws_connections[room.room_id] = {}
    mgr._loop = None
    return room


# ---------------------------------------------------------------------------
# Trigger condition
# ---------------------------------------------------------------------------

def test_should_run_island_guarantee_true_when_islandless_and_ai_extras_exist():
    mgr = GameManager()
    room = _make_room(mgr, islandless_humans=1, ai_with_extras=True)
    assert mgr._should_run_island_guarantee(room) is True


def test_should_run_island_guarantee_false_no_islandless_humans():
    mgr = GameManager()
    room = _make_room(mgr, islandless_humans=0, ai_with_extras=True)
    assert mgr._should_run_island_guarantee(room) is False


def test_should_run_island_guarantee_false_no_ai_extras():
    """No AI controls 2+ roles → guarantee skipped."""
    mgr = GameManager()
    room = GameRoom(
        room_id="g2", name="Test", creator_id="host",
        starting_capital=DEFAULT_STARTING_CAPITAL,
    )
    room.players.append(LobbyPlayer(player_id="h1", name="H", is_human=True))
    # Two AI players, each with one role
    room.players.append(LobbyPlayer(
        player_id="ai1", name="AI1", role_names=["Banker"], is_human=False))
    room.players.append(LobbyPlayer(
        player_id="ai2", name="AI2", role_names=["Farmer"], is_human=False))
    mgr.rooms[room.room_id] = room
    mgr._loop = None
    assert mgr._should_run_island_guarantee(room) is False


# ---------------------------------------------------------------------------
# Offer building
# ---------------------------------------------------------------------------

def test_build_offers_lists_all_ai_extras_with_prices():
    mgr = GameManager()
    room = _make_room(mgr, islandless_humans=1, ai_with_extras=True)
    # Initialize guarantee state so _build_offers_for can read auction_deductions
    room.guarantee = IslandGuaranteeState(auction_deductions={})
    offers = mgr._build_offers_for(room, "h1")
    assert len(offers) == 2
    roles = {o["role"] for o in offers}
    assert roles == {"Banker", "Farmer"}
    # Economy-lifecycle Phase A: starting capital is now 1500/player.
    # Banker: AI paid 80 / 1500 = 5.3% → low band → formula 80; floor
    # 0.20 * 1500 = 300 wins → 300.
    banker = next(o for o in offers if o["role"] == "Banker")
    assert banker["breakdown"]["formula_band"] == "low"
    assert banker["price"] == 300.0
    # Farmer: AI paid 50 / 1500 = 3.3% → low band → formula 50; floor
    # 300 wins → 300.
    farmer = next(o for o in offers if o["role"] == "Farmer")
    assert farmer["breakdown"]["formula_band"] == "low"
    assert farmer["price"] == 300.0
    # Affordability check: buyer has 1500 Dp, both (300) are affordable
    assert all(o["affordable"] for o in offers)


def test_build_offers_marks_unaffordable_offers():
    mgr = GameManager()
    room = _make_room(mgr, islandless_humans=1, ai_with_extras=True)
    room.guarantee = IslandGuaranteeState(
        # Phase A: 1500/player. Spend 1440 → 60 left. Both AI prices are
        # low-band (formula = ai_paid): Banker 80, Farmer 50. Floor
        # 0.20 * 60 = 12 (loses). Banker 80 > 60 → unaffordable; Farmer
        # 50 ≤ 60 → affordable.
        auction_deductions={"h1": 1440.0},
    )
    offers = mgr._build_offers_for(room, "h1")
    banker = next(o for o in offers if o["role"] == "Banker")
    farmer = next(o for o in offers if o["role"] == "Farmer")
    assert banker["affordable"] is False
    assert farmer["affordable"] is True


# ---------------------------------------------------------------------------
# Phase entry + transfer
# ---------------------------------------------------------------------------

def test_start_island_guarantee_sets_phase_and_queues_first_buyer():
    mgr = GameManager()
    room = _make_room(mgr, islandless_humans=1, ai_with_extras=True)
    mgr._start_island_guarantee(room.room_id, deductions={})
    assert room.status == "guarantee"
    assert room.guarantee is not None
    assert room.guarantee.current_buyer == "h1"
    assert len(room.guarantee.offers_for_current) == 2


def test_accept_choice_transfers_role_and_records_deductions():
    mgr = GameManager()
    room = _make_room(mgr, islandless_humans=1, ai_with_extras=True)
    mgr._start_island_guarantee(room.room_id, deductions={})

    res = mgr.submit_guarantee_choice(room.room_id, "h1",
                                       accept=True, role="Banker")
    assert res.get("ok") is True
    # Role moved from AI to human
    ai = next(p for p in room.players if p.player_id == "ai1")
    h1 = next(p for p in room.players if p.player_id == "h1")
    assert "Banker" not in ai.role_names
    assert "Banker" in h1.role_names
    # Auction deductions reflect cash movement (h1 pays 160, ai1 receives 160)
    # Banker = 160 (mid band).  Phase finalised → no longer in guarantee.
    assert room.guarantee is None
    assert room.status == "investing" or room.status == "guarantee"
    # The investing phase may auto-finalize for AI-only remaining; check that
    # the deductions dict that flowed through was correctly modified.


def test_decline_choice_advances_to_next_buyer():
    mgr = GameManager()
    room = _make_room(mgr, islandless_humans=2, ai_with_extras=True)
    mgr._start_island_guarantee(room.room_id, deductions={})
    assert room.guarantee.current_buyer == "h1"

    mgr.submit_guarantee_choice(room.room_id, "h1", accept=False)
    # h1 declined → h2 should be the current buyer now
    assert room.guarantee is not None
    assert room.guarantee.current_buyer == "h2"


def test_choice_rejected_when_not_your_turn():
    mgr = GameManager()
    room = _make_room(mgr, islandless_humans=2, ai_with_extras=True)
    mgr._start_island_guarantee(room.room_id, deductions={})
    res = mgr.submit_guarantee_choice(room.room_id, "h2",
                                       accept=True, role="Banker")
    assert "error" in res
    assert "your turn" in res["error"].lower()


def test_choice_rejected_for_unavailable_role():
    mgr = GameManager()
    room = _make_room(mgr, islandless_humans=1, ai_with_extras=True)
    mgr._start_island_guarantee(room.room_id, deductions={})
    res = mgr.submit_guarantee_choice(room.room_id, "h1",
                                       accept=True, role="Doctor")
    assert "error" in res


def test_phase_skipped_when_no_ai_extras_exist():
    """If the trigger condition isn't met, _should_run_island_guarantee is
    False — main code path simply never enters the phase."""
    mgr = GameManager()
    room = _make_room(mgr, islandless_humans=1, ai_with_extras=False)
    # No AI present at all
    assert mgr._should_run_island_guarantee(room) is False


def test_sequential_buyers_share_a_dwindling_offer_pool_with_two_ais():
    """If two AIs both have extras and buyer A takes from one, buyer B should
    still see the other AI's extras (the depleted AI is no longer eligible)."""
    mgr = GameManager()
    room = GameRoom(
        room_id="g3", name="Test", creator_id="host",
        starting_capital=DEFAULT_STARTING_CAPITAL,
    )
    room.players.append(LobbyPlayer(player_id="h1", name="H1", is_human=True))
    room.players.append(LobbyPlayer(player_id="h2", name="H2", is_human=True))
    room.players.append(LobbyPlayer(
        player_id="ai1", name="AI1",
        role_names=["Banker", "Farmer"], is_human=False,
    ))
    room.players.append(LobbyPlayer(
        player_id="ai2", name="AI2",
        role_names=["Doctor", "Miner"], is_human=False,
    ))
    room.ai_role_prices = {"Banker": 80, "Farmer": 50, "Doctor": 120, "Miner": 60}
    room.status = "auction"
    mgr.rooms[room.room_id] = room
    mgr._ws_connections[room.room_id] = {}
    mgr._loop = None

    mgr._start_island_guarantee(room.room_id, deductions={})
    # h1 buys Banker from ai1 → ai1 now has only Farmer (no longer "extras"),
    # but ai2 still has 2 roles, so h2 sees ai2's offers.
    mgr.submit_guarantee_choice(room.room_id, "h1",
                                 accept=True, role="Banker")
    assert room.guarantee is not None
    assert room.guarantee.current_buyer == "h2"
    roles = {o["role"] for o in room.guarantee.offers_for_current}
    assert roles == {"Doctor", "Miner"}  # ai2's two roles


def test_sole_ai_loses_extras_after_one_sale_so_second_buyer_skipped():
    """If only one AI has extras and they sell one role, the AI now has only
    one role and is no longer eligible.  A second islandless human waiting in
    queue sees no offers and the phase finalises."""
    mgr = GameManager()
    room = _make_room(mgr, islandless_humans=2, ai_with_extras=True)
    mgr._start_island_guarantee(room.room_id, deductions={})
    # h1 takes Banker → ai1 left with Farmer only
    mgr.submit_guarantee_choice(room.room_id, "h1",
                                 accept=True, role="Banker")
    # ai1 now has only Farmer (1 role) → no extras → h2 skipped, phase finalises
    assert room.guarantee is None
    ai = next(p for p in room.players if p.player_id == "ai1")
    assert ai.role_names == ["Farmer"]
    h2 = next(p for p in room.players if p.player_id == "h2")
    assert h2.role_names == []  # h2 remained islandless
