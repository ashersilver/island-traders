"""Tests for Issue #22 — market price prefill.

#22.3: buying — new-bid price prefilled with the ask (client-side, see
       index.html; covered indirectly by the WS message carrying prefill).
#22.4: selling — asking-price prompt prefilled with the best bid.

These tests cover the engine/adapter plumbing for the `prefill` parameter
added to `ask_dollop_amount`.
"""
from __future__ import annotations

import threading
import pytest

from island_traders.cli.prompts import IOAdapter, FakeIOAdapter


# ---------------------------------------------------------------------------
# Base terminal adapter honours prefill on empty input
# ---------------------------------------------------------------------------

class ScriptedTerminalIO(IOAdapter):
    def __init__(self, inputs):
        self._inputs = list(inputs)
        self.printed = []

    def print(self, text): self.printed.append(text)
    def input(self, prompt): return self._inputs.pop(0)


def test_base_ask_dollop_empty_input_returns_prefill():
    io = ScriptedTerminalIO([""])           # user just presses enter
    assert io.ask_dollop_amount("price?", 100.0, prefill=7.5) == 7.5


def test_base_ask_dollop_explicit_value_overrides_prefill():
    io = ScriptedTerminalIO(["12"])
    assert io.ask_dollop_amount("price?", 100.0, prefill=7.5) == 12.0


def test_base_ask_dollop_no_prefill_still_works():
    io = ScriptedTerminalIO(["3"])
    assert io.ask_dollop_amount("price?", 100.0) == 3.0


def test_fake_ask_dollop_accepts_prefill_kwarg():
    # Backwards-compat: FakeIOAdapter must accept the new kwarg.
    assert FakeIOAdapter().ask_dollop_amount("p", 10.0, prefill=4.0) == 0.0


# ---------------------------------------------------------------------------
# WebSocket adapter sends prefill in the message
# ---------------------------------------------------------------------------

pytest.importorskip("fastapi")
from island_traders.server.ws_adapter import WebSocketIOAdapter  # noqa: E402


def test_ws_ask_dollop_includes_prefill_in_message():
    sent = []
    io = WebSocketIOAdapter(
        "t", broadcast_fn=lambda m: None,
        player_send_fns={0: lambda m: sent.append(m)},
    )
    io.begin_season()
    io.set_active_player(0)

    def _respond():
        import time as _t
        _t.sleep(0.05)
        io.receive_response(0, "9.25")
    threading.Thread(target=_respond, daemon=True).start()

    val = io.ask_dollop_amount("Asking price?", 500.0, prefill=8.5)
    assert val == 9.25
    msg = next(m for m in sent if m.get("type") == "ask_dollop_amount")
    assert msg["prefill"] == 8.5


def test_ws_ask_dollop_zero_prefill_sends_zero():
    sent = []
    io = WebSocketIOAdapter(
        "t", broadcast_fn=lambda m: None,
        player_send_fns={0: lambda m: sent.append(m)},
    )
    io.begin_season()
    io.set_active_player(0)
    threading.Thread(
        target=lambda: (__import__("time").sleep(0.05), io.receive_response(0, "1")),
        daemon=True,
    ).start()
    io.ask_dollop_amount("p", 10.0)  # no prefill
    msg = next(m for m in sent if m.get("type") == "ask_dollop_amount")
    assert msg["prefill"] == 0


# ---------------------------------------------------------------------------
# Market sell prefills the asking price with the best bid (#22.4)
# ---------------------------------------------------------------------------

def test_market_sell_prefills_asking_price_with_best_bid():
    from island_traders.engine.production import ProductionEngine
    from island_traders.engine.trading import TradingEngine
    from island_traders.engine.turn import TurnManager, TurnResult
    from island_traders.models.deal import DealLedger
    from island_traders.models.market import Market
    from island_traders.models.player import Player
    from island_traders.models.resource import ResourceType
    from island_traders.models.role import ROLES

    captured = {}

    class SellIO(FakeIOAdapter):
        def choose_resource(self, prompt, available):
            return ResourceType.OIL
        def choose_quantity(self, prompt, min_qty, max_qty):
            return 1
        def confirm(self, prompt):
            return False  # decline "sell into bids" so we reach the ask prompt
        def ask_dollop_amount(self, prompt, max_dollops, prefill=0.0):
            captured["prefill"] = prefill
            return 0.0  # 0 → "cancelled, price must be positive" (we just want the prefill)

    seller = Player(player_id=0, name="S", roles=[ROLES["Miner"]],
                    dollops=100.0, is_human=True)
    seller.receive_resources(ResourceType.OIL, 5)

    market = Market()
    buyer = Player(player_id=1, name="B", roles=[ROLES["Manufacturer"]],
                   dollops=500.0, is_human=True)
    # Buyer posts a bid for Oil at 22.0/unit
    market.post_bid(buyer, ResourceType.OIL, 22.0, 3)

    io = SellIO()
    tm = TurnManager(
        players=[seller, buyer],
        production_engine=ProductionEngine(),
        trading_engine=TradingEngine(market, DealLedger()),
        market=market,
        io_adapter=io,
    )
    tm._action_market_sell(seller, TurnResult(0, season=0, year=0))

    assert "prefill" in captured, "ask_dollop_amount should have been called"
    assert captured["prefill"] == 22.0, (
        "asking price should be pre-filled with the best bid price"
    )


def test_market_bid_logs_immediate_exact_price_fill():
    from island_traders.engine.production import ProductionEngine
    from island_traders.engine.trading import TradingEngine
    from island_traders.engine.turn import TurnManager, TurnResult
    from island_traders.models.deal import DealLedger
    from island_traders.models.market import Market
    from island_traders.models.player import Player
    from island_traders.models.resource import ResourceType
    from island_traders.models.role import ROLES

    class BulkBidIO(FakeIOAdapter):
        def market_buy_bulk(self, player, market_summary):
            return {"bids": {"PassengerSeats": {"quantity": 20, "price": 15.0}}}

    seller = Player(0, "Transport", [ROLES["Transporter"]], 100.0, is_human=True)
    seller.receive_resources(ResourceType.PASSENGER_SEATS, 20)
    buyer = Player(1, "Education", [ROLES["Educator"]], 500.0, is_human=True)
    market = Market()
    market.post_offer(seller, ResourceType.PASSENGER_SEATS, 15.0, 20)

    io = BulkBidIO()
    tm = TurnManager(
        players=[seller, buyer],
        production_engine=ProductionEngine(),
        trading_engine=TradingEngine(market, DealLedger()),
        market=market,
        io_adapter=io,
    )
    result = TurnResult(buyer.player_id, season=0, year=0)
    tm._action_market_buy(buyer, result)

    assert buyer.inventory.get(ResourceType.PASSENGER_SEATS) == 20
    assert any("Bought 20x PassengerSeats immediately" in line for line in io.printed)
    assert "buy:20xPassengerSeats" in result.actions_taken
