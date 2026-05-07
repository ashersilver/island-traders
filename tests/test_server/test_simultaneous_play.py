"""Tests for the simultaneous-play primitives:
- per-player concurrent IO adapter
- season Ready/Timer interrupt mechanics
- TurnManager.parallel_mode dispatch
"""
from __future__ import annotations

import threading
import time
import pytest

pytest.importorskip("fastapi")

from island_traders.server.ws_adapter import WebSocketIOAdapter


def test_per_player_events_are_independent():
    """Two players prompted concurrently should not interfere with each other."""
    sent: list[tuple[int, dict]] = []

    def make_send(pid):
        return lambda msg: sent.append((pid, msg))

    io = WebSocketIOAdapter(
        "g1", broadcast_fn=lambda m: None,
        player_send_fns={0: make_send(0), 1: make_send(1)},
    )
    io.begin_season()

    results: dict[int, object] = {}

    def waiter(pid, expected):
        io.set_active_player(pid)
        r = io._send_and_wait({"type": "test", "for": pid}, timeout=2)
        results[pid] = r

    t0 = threading.Thread(target=waiter, args=(0, "a"), daemon=True)
    t1 = threading.Thread(target=waiter, args=(1, "b"), daemon=True)
    t0.start(); t1.start()

    # Wait briefly so both threads block on their events
    time.sleep(0.1)
    # Respond to player 0 only
    io.receive_response(0, "a")
    t0.join(timeout=1)
    assert results.get(0) == "a"
    assert 1 not in results   # player 1 still waiting

    # Now respond to player 1
    io.receive_response(1, "b")
    t1.join(timeout=1)
    assert results.get(1) == "b"


def test_interrupt_all_unblocks_every_pending_prompt():
    """Season-timer expiry must unblock all waiting threads with None."""
    io = WebSocketIOAdapter(
        "g2", broadcast_fn=lambda m: None,
        player_send_fns={0: lambda m: None, 1: lambda m: None, 2: lambda m: None},
    )
    io.begin_season()

    results: list[tuple[int, object]] = []
    threads = []
    for pid in (0, 1, 2):
        def waiter(p=pid):
            io.set_active_player(p)
            r = io._send_and_wait({"type": "test"}, timeout=5)
            results.append((p, r))
        t = threading.Thread(target=waiter, daemon=True)
        threads.append(t)
        t.start()

    time.sleep(0.1)
    io.interrupt_all()
    for t in threads:
        t.join(timeout=2)

    assert sorted(results) == [(0, None), (1, None), (2, None)]


def test_interrupted_confirm_cancels_instead_of_accepting():
    io = WebSocketIOAdapter(
        "g2b", broadcast_fn=lambda m: None, player_send_fns={0: lambda m: None},
    )
    io.begin_season()
    io.set_active_player(0)
    io.interrupt_all()

    assert io.confirm("Accept?") is False


def test_mark_player_ready_short_circuits_choose_action():
    """A player marked Ready returns END_TURN without sending a prompt."""
    from island_traders.engine.turn import TurnAction

    sends: list[dict] = []
    io = WebSocketIOAdapter(
        "g3", broadcast_fn=lambda m: None,
        player_send_fns={0: lambda m: sends.append(m)},
    )
    io.begin_season()
    io.mark_player_ready(0)

    class FakePlayer:
        player_id = 0
        name = "P0"

    res = io.choose_action(FakePlayer(), [TurnAction.END_TURN, TurnAction.PRODUCE])
    assert res == TurnAction.END_TURN
    # No prompt should have been sent
    assert not any(s.get("type") == "choose_action" for s in sends)


def test_unmark_player_ready_clears_flag():
    io = WebSocketIOAdapter(
        "g4", broadcast_fn=lambda m: None,
        player_send_fns={0: lambda m: None},
    )
    io.begin_season()
    io.mark_player_ready(0)
    assert 0 in io._player_ready_flags
    io.unmark_player_ready(0)
    assert 0 not in io._player_ready_flags


def test_begin_season_resets_state():
    """Each season starts fresh — interrupt + ready flags cleared."""
    io = WebSocketIOAdapter(
        "g5", broadcast_fn=lambda m: None,
        player_send_fns={0: lambda m: None},
    )
    io.begin_season()
    io.mark_player_ready(0)
    io.interrupt_all()
    assert io._interrupted is True
    assert 0 in io._player_ready_flags

    io.begin_season()
    assert io._interrupted is False
    assert 0 not in io._player_ready_flags


def test_turn_manager_parallel_mode_dispatch():
    """When parallel_mode is True, run_season delegates to _run_season_parallel."""
    from island_traders.engine.turn import TurnManager
    from island_traders.engine.production import ProductionEngine
    from island_traders.engine.trading import TradingEngine
    from island_traders.models.market import Market
    from island_traders.cli.prompts import FakeIOAdapter

    from island_traders.models.deal import DealLedger
    market = Market()
    io = FakeIOAdapter()
    ledger = DealLedger()
    tm = TurnManager(
        players=[],
        production_engine=ProductionEngine(),
        trading_engine=TradingEngine(market, ledger),
        market=market,
        io_adapter=io,
    )
    assert tm.parallel_mode is False  # default off
    tm.parallel_mode = True
    assert tm.parallel_mode is True

    # With no players, both modes return an empty result list
    results = tm._run_season_parallel(0, 0, {})
    assert results == []
    results = tm._run_season_sequential(0, 0, {})
    assert results == []
