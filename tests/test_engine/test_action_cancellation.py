"""Tests for explicit-Cancel action handling (Bug fix: 'Cancel still trained 1 doctor').

The WS client now sends a distinct `CANCEL_SENTINEL` string when the user
clicks Cancel.  The WebSocketIOAdapter detects the sentinel and raises
`ActionCancelled`, which the engine's main action loop catches.  Previously
a Cancel click sent `null`, which the adapter mapped to a default value
(min_qty, available[0], etc.) — so the action would still execute partially.

These tests exercise the WS adapter prompt methods with the sentinel and
confirm they raise `ActionCancelled`.
"""
from __future__ import annotations

import threading
import pytest

pytest.importorskip("fastapi")

from island_traders.cli.signals import CANCEL_SENTINEL, ActionCancelled
from island_traders.models.resource import ResourceType
from island_traders.server.ws_adapter import WebSocketIOAdapter


def _io():
    """Build a minimal adapter with one player wired up."""
    sent = []
    io = WebSocketIOAdapter(
        "test", broadcast_fn=lambda m: None,
        player_send_fns={0: lambda m: sent.append(m)},
    )
    io.begin_season()
    io.set_active_player(0)
    return io, sent


def _send_cancel_after_delay(io, pid=0, delay=0.05):
    """Wait briefly then deliver the sentinel as the response."""
    def _do():
        import time as _t
        _t.sleep(delay)
        io.receive_response(pid, CANCEL_SENTINEL)
    t = threading.Thread(target=_do, daemon=True)
    t.start()
    return t


def test_choose_quantity_raises_actioncancelled_on_sentinel():
    io, _ = _io()
    _send_cancel_after_delay(io)
    with pytest.raises(ActionCancelled):
        io.choose_quantity("how many?", 1, 5)


def test_choose_quantity_returns_default_on_none_response():
    """Plain None (timeout / interrupt) is NOT a cancel — falls back to min_qty."""
    io, _ = _io()
    # Simulate a timeout-like behaviour: deliver None as the response.
    def _do():
        import time as _t
        _t.sleep(0.05)
        io.receive_response(0, None)
    threading.Thread(target=_do, daemon=True).start()
    assert io.choose_quantity("how many?", 1, 5) == 1


def test_choose_resource_raises_actioncancelled_on_sentinel():
    io, _ = _io()
    _send_cancel_after_delay(io)
    with pytest.raises(ActionCancelled):
        io.choose_resource("which?", [ResourceType.FOOD, ResourceType.FISH])


def test_choose_player_raises_actioncancelled_on_sentinel():
    io, _ = _io()
    _send_cancel_after_delay(io)

    class P:
        player_id = 1; name = "P1"
        def role_names(self): return []

    with pytest.raises(ActionCancelled):
        io.choose_player("which player?", [P()])


def test_confirm_raises_actioncancelled_on_sentinel():
    io, _ = _io()
    _send_cancel_after_delay(io)
    with pytest.raises(ActionCancelled):
        io.confirm("are you sure?")


def test_choose_profession_raises_actioncancelled_on_sentinel():
    io, _ = _io()
    _send_cancel_after_delay(io)
    with pytest.raises(ActionCancelled):
        io.choose_profession("which profession?", ["Banker", "Doctor"])


def test_ask_dollop_amount_raises_actioncancelled_on_sentinel():
    io, _ = _io()
    _send_cancel_after_delay(io)
    with pytest.raises(ActionCancelled):
        io.ask_dollop_amount("how much?", 100.0)


def test_ask_text_raises_actioncancelled_on_sentinel():
    io, _ = _io()
    _send_cancel_after_delay(io)
    with pytest.raises(ActionCancelled):
        io.ask_text("name?", default="anon")


def test_actioncancelled_aborts_full_action_in_engine_loop():
    """End-to-end-ish: simulating Cancel during a training-style prompt chain
    should NOT result in a default action being executed."""
    from island_traders.engine.production import ProductionEngine
    from island_traders.engine.trading import TradingEngine
    from island_traders.engine.turn import TurnManager, TurnResult, TurnAction
    from island_traders.cli.prompts import FakeIOAdapter
    from island_traders.models.deal import DealLedger
    from island_traders.models.market import Market
    from island_traders.models.player import Player
    from island_traders.models.role import ROLES

    class CancellingIO(FakeIOAdapter):
        """Raises ActionCancelled on the very first prompt the engine issues."""
        def choose_quantity(self, prompt, min_qty, max_qty):
            raise ActionCancelled()
        def choose_profession(self, prompt, available):
            raise ActionCancelled()
        def choose_player(self, prompt, players):
            raise ActionCancelled()

    player = Player(player_id=0, name="P", roles=[ROLES["Farmer"]],
                    dollops=100.0, is_human=True)
    educator = Player(player_id=1, name="E", roles=[ROLES["Educator"]],
                      dollops=100.0, is_human=True)
    market = Market()
    io = CancellingIO()
    tm = TurnManager(
        players=[player, educator],
        production_engine=ProductionEngine(),
        trading_engine=TradingEngine(market, DealLedger()),
        market=market,
        io_adapter=io,
    )
    result = TurnResult(player_id=player.player_id, season=0, year=0)

    # If the action handler runs to completion despite a cancel, training
    # would be created.  We assert no training was created.
    try:
        tm._action_request_training(player, result, season_name="Spring", year=0)
    except ActionCancelled:
        pass  # caught here for test; in production the main loop catches it
    assert tm.training.all_requests() == []
    assert "request_training" not in " ".join(result.actions_taken)
