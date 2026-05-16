"""Tests for the generic `choose_option` named-choice picker (Issue #21).

Production / product-line selection now uses `choose_option` (a set of
named choices) instead of `choose_quantity` (a numeric box).
"""
from __future__ import annotations

import threading
import pytest

from island_traders.cli.prompts import IOAdapter, FakeIOAdapter
from island_traders.cli.signals import CANCEL_SENTINEL, ActionCancelled


# ---------------------------------------------------------------------------
# Base terminal IOAdapter
# ---------------------------------------------------------------------------

class ScriptedTerminalIO(IOAdapter):
    def __init__(self, inputs):
        self._inputs = list(inputs)
        self.printed = []

    def print(self, text): self.printed.append(text)
    def input(self, prompt): return self._inputs.pop(0)


def test_base_choose_option_returns_selected_value():
    io = ScriptedTerminalIO(["2"])
    opts = [
        {"value": "alpha", "label": "Alpha"},
        {"value": "beta", "label": "Beta"},
    ]
    assert io.choose_option("pick", opts) == "beta"


def test_base_choose_option_reprompts_on_invalid():
    io = ScriptedTerminalIO(["9", "x", "1"])
    opts = [{"value": 10, "label": "Ten"}, {"value": 20, "label": "Twenty"}]
    assert io.choose_option("pick", opts) == 10


def test_fake_choose_option_returns_first_value():
    io = FakeIOAdapter()
    opts = [{"value": "first", "label": "F"}, {"value": "second", "label": "S"}]
    assert io.choose_option("pick", opts) == "first"


def test_fake_choose_option_empty_is_none():
    assert FakeIOAdapter().choose_option("pick", []) is None


# ---------------------------------------------------------------------------
# WebSocket adapter
# ---------------------------------------------------------------------------

pytest.importorskip("fastapi")
from island_traders.server.ws_adapter import WebSocketIOAdapter  # noqa: E402


def _ws_io():
    sent = []
    io = WebSocketIOAdapter(
        "t", broadcast_fn=lambda m: None,
        player_send_fns={0: lambda m: sent.append(m)},
    )
    io.begin_season()
    io.set_active_player(0)
    return io, sent


def _respond_after(io, value, delay=0.05, pid=0):
    def _do():
        import time as _t
        _t.sleep(delay)
        io.receive_response(pid, value)
    threading.Thread(target=_do, daemon=True).start()


def test_ws_choose_option_round_trips_value():
    io, sent = _ws_io()
    opts = [{"value": 0, "label": "Food"}, {"value": 1, "label": "Fish"}]
    # Client sends back the value as a string ("1")
    _respond_after(io, "1")
    assert io.choose_option("Choose product", opts) == 1
    # The prompt was actually sent with the labelled options
    msg = next(m for m in sent if m.get("type") == "choose_option")
    assert msg["options"] == [
        {"value": 0, "label": "Food"}, {"value": 1, "label": "Fish"},
    ]


def test_ws_choose_option_timeout_returns_first_value():
    io, _ = _ws_io()
    opts = [{"value": "a", "label": "A"}, {"value": "b", "label": "B"}]
    _respond_after(io, None)  # simulate interrupt/timeout
    assert io.choose_option("pick", opts) == "a"


def test_ws_choose_option_cancel_sentinel_raises():
    io, _ = _ws_io()
    opts = [{"value": "a", "label": "A"}]
    _respond_after(io, CANCEL_SENTINEL)
    with pytest.raises(ActionCancelled):
        io.choose_option("pick", opts)


def test_ws_choose_option_unknown_value_falls_back_to_first():
    io, _ = _ws_io()
    opts = [{"value": "x", "label": "X"}, {"value": "y", "label": "Y"}]
    _respond_after(io, "not-a-real-value")
    assert io.choose_option("pick", opts) == "x"


# ---------------------------------------------------------------------------
# Integration: _action_produce uses named choices
# ---------------------------------------------------------------------------

def test_action_produce_uses_choose_option_with_named_labels():
    """Capture the options passed to choose_option for a Manufacturer and
    assert they carry product names (not bare indices)."""
    from island_traders.engine.production import ProductionEngine
    from island_traders.engine.trading import TradingEngine
    from island_traders.engine.turn import TurnManager, TurnResult
    from island_traders.engine.events import EventResult
    from island_traders.models.deal import DealLedger
    from island_traders.models.market import Market
    from island_traders.models.player import Player
    from island_traders.models.role import ROLES
    from island_traders.models.resource import ResourceType
    from island_traders.models.profession import Profession

    captured = {}

    class CapturingIO(FakeIOAdapter):
        def choose_option(self, prompt, options):
            captured["prompt"] = prompt
            captured["options"] = options
            return options[0]["value"]
        def choose_quantity(self, prompt, min_qty, max_qty):
            return min_qty
        def confirm(self, prompt):
            return False  # don't actually produce; we only care about the picker

    farmer = Player(player_id=0, name="F", roles=[ROLES["Farmer"]],
                    dollops=100.0, is_human=True)
    # Give the Farmer enough capital / workforce / inputs to actually have
    # production options (otherwise _action_produce returns before the picker).
    farmer.add_capital("farmer.tractor")
    farmer.add_capital("farmer.fishing_boat")
    farmer.workforce.add_workers(1, training_level=1, profession=Profession.FARMER.value)
    farmer.workforce.add_workers(1, training_level=1, profession=Profession.FARMING_TECHNICIAN.value)
    farmer.workforce.add_workers(8, training_level=0, profession=Profession.UNSKILLED.value)
    farmer.receive_resources(ResourceType.OIL, 10)
    farmer.receive_resources(ResourceType.FARM_MACHINERY, 10)
    market = Market()
    io = CapturingIO()
    tm = TurnManager(
        players=[farmer],
        production_engine=ProductionEngine(),
        trading_engine=TradingEngine(market, DealLedger()),
        market=market,
        io_adapter=io,
    )
    ev = EventResult(event_name="Normal", yield_modifier=1.0, outage=False)
    tm._action_produce(farmer, ev, TurnResult(0, season=0, year=0), "Spring")

    assert "options" in captured, "produce should call choose_option"
    # Every option must carry a human label, not just a number
    for opt in captured["options"]:
        assert "label" in opt and opt["label"]
        assert any(c.isalpha() for c in opt["label"]), (
            f"label {opt['label']!r} should contain a product name"
        )
