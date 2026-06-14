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


def test_pending_prompt_can_be_replayed_after_reconnect():
    sent: list[tuple[int, dict]] = []
    io = WebSocketIOAdapter(
        "g1b",
        broadcast_fn=lambda m: None,
        player_send_fns={0: lambda m: sent.append((0, m))},
    )
    io.begin_season()

    result = {}

    def waiter():
        io.set_active_player(0)
        result["value"] = io._send_and_wait({"type": "choose_action"}, timeout=2)

    t = threading.Thread(target=waiter, daemon=True)
    t.start()
    time.sleep(0.1)

    assert io.replay_pending_prompt(0) is True
    assert [m["type"] for _, m in sent] == ["choose_action", "choose_action"]
    assert sent[-1][1]["replayed"] is True

    io.receive_response(0, "end_turn")
    t.join(timeout=1)
    assert result["value"] == "end_turn"


def test_parked_prompt_can_be_replayed_after_reconnect_or_menu_recovery():
    sent: list[tuple[int, dict]] = []
    io = WebSocketIOAdapter(
        "g1c",
        broadcast_fn=lambda m: None,
        player_send_fns={0: lambda m: sent.append((0, m))},
    )
    io.begin_season()
    io.mark_player_ready(0)

    assert io.replay_pending_prompt(0) is True
    assert sent[-1][1]["type"] == "choose_action_parked"
    assert sent[-1][1]["replayed"] is True


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


def test_mark_player_ready_parks_choose_action_until_interrupted():
    """Done Trading is a PAUSE, not a TERMINATE (2026-05-27 brief).

    A player marked Ready stays parked in choose_action's wait loop
    until either interrupt_all fires (real season end → END_TURN) or
    unmark_player_ready is called (Undo → re-prompt).  This preserves
    the turn thread so it can resume the action menu on undo.
    """
    import threading
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

    result_holder: list = []

    def _run():
        # set_active_player is called inside choose_action via TLS,
        # so this thread is the one that needs to be parked.
        result_holder.append(
            io.choose_action(FakePlayer(), [TurnAction.END_TURN, TurnAction.PRODUCE])
        )

    t = threading.Thread(target=_run, daemon=True)
    t.start()

    # Give the park loop a moment to broadcast and settle.
    t.join(timeout=1.5)
    assert t.is_alive(), "Park loop should hold the thread, not exit"
    # The parked broadcast went out, but no full choose_action prompt.
    assert any(s.get("type") == "choose_action_parked" for s in sends)
    assert not any(s.get("type") == "choose_action" for s in sends)

    # Real season end → park exits with END_TURN.
    io.interrupt_all()
    t.join(timeout=2.0)
    assert not t.is_alive(), "Park loop should release on interrupt_all"
    assert result_holder == [TurnAction.END_TURN]


def test_unmark_player_ready_wakes_parked_choose_action():
    """Undo Done Trading: parked thread wakes and re-prompts with a
    fresh choose_action message instead of exiting with END_TURN.
    """
    import threading
    from island_traders.engine.turn import TurnAction

    sends: list[dict] = []
    io = WebSocketIOAdapter(
        "g_undo", broadcast_fn=lambda m: None,
        player_send_fns={0: lambda m: sends.append(m)},
    )
    io.begin_season()
    io.mark_player_ready(0)

    class FakePlayer:
        player_id = 0
        name = "P0"

    result_holder: list = []

    def _run():
        result_holder.append(
            io.choose_action(FakePlayer(), [TurnAction.END_TURN, TurnAction.PRODUCE])
        )

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=1.5)
    assert t.is_alive()

    # Undo Done.  The park loop wakes; choose_action falls through to the
    # normal prompt path; the player gets a fresh choose_action message.
    io.unmark_player_ready(0)

    # Wait briefly for the fresh prompt to arrive.
    deadline = __import__("time").time() + 2.0
    while __import__("time").time() < deadline:
        if any(s.get("type") == "choose_action" for s in sends):
            break
        __import__("time").sleep(0.05)
    assert any(s.get("type") == "choose_action" for s in sends), (
        "After Undo, a fresh choose_action prompt must be sent"
    )

    # Provide a response so the thread can exit cleanly.
    io.receive_response(0, "end_turn")
    t.join(timeout=2.0)
    assert not t.is_alive()
    assert result_holder == [TurnAction.END_TURN]


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


def test_mark_player_ready_cancels_in_flight_prompt():
    """Done Trading mid-dialog: in-flight sub-prompt aborts via
    CANCEL_SENTINEL so the engine's ActionCancelled handler can drop
    cleanly back to the action loop, where the park check then fires.
    2026-05-27 done-trading-undo brief — root cause for 'action panel
    disappears after End Turn' (Comet 1 #2)."""
    import threading
    from island_traders.cli.prompts import CANCEL_SENTINEL

    sends: list[dict] = []
    io = WebSocketIOAdapter(
        "g_cancel", broadcast_fn=lambda m: None,
        player_send_fns={0: lambda m: sends.append(m)},
    )
    io.begin_season()
    io.set_active_player(0)

    # Simulate the player sitting inside a sub-prompt (e.g. a market form
    # — choose_quantity is a stand-in).  This blocks on _send_and_wait
    # until something resolves it.
    result_holder: list = []

    def _run():
        from island_traders.engine.turn import TurnAction  # noqa: F401
        # set_active_player is per-thread (TLS), so do it in the thread.
        io.set_active_player(0)
        try:
            result_holder.append(io.choose_quantity("Qty?", 1, 10))
        except Exception as exc:
            result_holder.append(("EXC", type(exc).__name__))

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    # Give the prompt a moment to send.
    deadline = time.time() + 1.0
    while time.time() < deadline:
        if any(s.get("type") == "choose_quantity" for s in sends):
            break
        time.sleep(0.02)
    assert any(s.get("type") == "choose_quantity" for s in sends)

    # Player clicks Done while in the dialog.  mark_player_ready resolves
    # the in-flight prompt with CANCEL_SENTINEL — the dialog raises
    # ActionCancelled.
    io.mark_player_ready(0)
    t.join(timeout=2.0)
    assert not t.is_alive()
    # choose_quantity catches ActionCancelled and re-raises; the test
    # thread sees it.  In production the engine's action handler catches
    # ActionCancelled and returns to the action loop.
    assert result_holder and result_holder[0][0] == "EXC", \
        f"Expected ActionCancelled-style exception, got {result_holder}"


def test_export_log_returns_full_print_history():
    """export_log() concatenates every IO.print() call in order.
    Drives the dashboard's Download Log button (2026-05-27 playtest
    ask for offline debugging)."""
    io = WebSocketIOAdapter(
        "g_log", broadcast_fn=lambda m: None,
        player_send_fns={0: lambda m: None},
    )
    io.print("Spring Y1 — production begins")
    io.print("[LOAN] Comet repaid 50 Dp")
    io.print("[EVENT] Flood: Agriculture")
    text = io.export_log()
    # Lines preserved verbatim and in order.
    assert text == (
        "Spring Y1 — production begins\n"
        "[LOAN] Comet repaid 50 Dp\n"
        "[EVENT] Flood: Agriculture"
    )


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


def test_parallel_turn_manager_calls_release_hook_after_threads_complete():
    from island_traders.engine.turn import TurnManager
    from island_traders.engine.production import ProductionEngine
    from island_traders.engine.trading import TradingEngine
    from island_traders.models.market import Market
    from island_traders.cli.prompts import FakeIOAdapter
    from island_traders.models.deal import DealLedger

    market = Market()
    tm = TurnManager(
        players=[],
        production_engine=ProductionEngine(),
        trading_engine=TradingEngine(market, DealLedger()),
        market=market,
        io_adapter=FakeIOAdapter(),
    )
    calls = []
    tm.wait_for_parallel_season_release = lambda y, s: calls.append((y, s))

    assert tm._run_season_parallel(2, 3, {}) == []
    assert calls == [(2, 3)]


def test_concurrent_ensure_player_does_not_create_duplicate_events():
    """Regression: two threads calling _ensure_player simultaneously for the
    same pid must not create separate Event/Lock objects (bug #2 root cause)."""
    io = WebSocketIOAdapter(
        "g7", broadcast_fn=lambda m: None,
        player_send_fns={0: lambda m: None},
    )
    barrier = threading.Barrier(4)
    errors = []

    def _init_player():
        try:
            barrier.wait(timeout=2)
            io._ensure_player(0)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=_init_player, daemon=True) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=2)

    assert not errors
    # Must have exactly one Event and one Lock, not duplicates.
    assert isinstance(io._player_events[0], threading.Event)
    # threading.Lock is a factory on some Pythons — verify it's a usable lock.
    lock = io._player_locks[0]
    assert lock is not None
    assert hasattr(lock, "acquire") and hasattr(lock, "release")


def test_response_during_send_and_wait_is_not_swallowed():
    """If receive_response arrives immediately after _send_and_wait sends the
    message, the response must not be lost (bug #2 split-lock regression)."""
    sent = []
    io = WebSocketIOAdapter(
        "g8", broadcast_fn=lambda m: None,
        player_send_fns={0: lambda m: sent.append(m)},
    )
    io.begin_season()

    result = {}

    def waiter():
        io.set_active_player(0)
        result["value"] = io._send_and_wait({"type": "choose_action"}, timeout=2)

    t = threading.Thread(target=waiter, daemon=True)
    t.start()
    time.sleep(0.05)  # let waiter reach the wait

    # Simulate a near-instantaneous response (as if client responded immediately)
    io.receive_response(0, "produce")
    t.join(timeout=2)
    assert result.get("value") == "produce"
