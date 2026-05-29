"""Regression coverage for the reconnect race that caused bug #2:
"action menu stops displaying for some players" in multiplayer.

Repro:

1. A WebSocket A is registered for ``(room, player)`` — the live socket.
2. A new WebSocket B reconnects for the same ``(room, player)`` (quick
   refresh / network blip / second tab).  ``register_ws`` overwrites the
   table entry: ``_ws_connections[room][player] = B``.
3. A short time later A's network handler detects the disconnect and its
   ``finally`` block fires ``unregister_ws(room, player)``.  In the old
   code this blindly ``pop``'d the entry — removing B from the table even
   though B is still alive and connected.
4. Subsequent ``_thread_safe_send`` calls find no socket for the slot and
   silently drop every message — the action menu never reaches the
   player.

The fix gives ``unregister_ws`` an optional ``ws`` argument that scopes
the removal to a specific socket identity, and protects every read /
write of ``_ws_connections`` with ``GameManager._ws_lock``.
"""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from island_traders.server.app import GameManager


class _FakeWS:
    """Stand-in for the FastAPI WebSocket object — identity is what
    matters; the connection table only ever compares with `is`."""
    def __init__(self, label: str = ""):
        self.label = label

    def __repr__(self) -> str:
        return f"<FakeWS {self.label}>"


def test_register_then_unregister_removes_the_entry():
    """Sanity: the happy path (no reconnect race) still works."""
    mgr = GameManager()
    ws = _FakeWS("only")
    mgr.register_ws("R", "P", ws)
    assert mgr._ws_connections["R"]["P"] is ws

    removed = mgr.unregister_ws("R", "P", ws)
    assert removed is True
    assert "P" not in mgr._ws_connections["R"]


def test_unregister_does_not_remove_newer_replacement():
    """The actual bug #2 fix: an old socket's late ``finally`` cannot
    evict a newer reconnect that has already taken its slot."""
    mgr = GameManager()
    old = _FakeWS("old")
    new = _FakeWS("new")

    mgr.register_ws("R", "P", old)
    # Reconnect: new socket grabs the slot before old's finally fires.
    mgr.register_ws("R", "P", new)
    assert mgr._ws_connections["R"]["P"] is new

    # Now old's finally fires (late) — must be a no-op.
    removed = mgr.unregister_ws("R", "P", old)
    assert removed is False, (
        "Old socket's unregister must not evict the newer reconnect"
    )
    assert mgr._ws_connections["R"]["P"] is new, (
        "New socket should still be the live entry after the old "
        "socket's finally fires"
    )


def test_unregister_without_ws_arg_falls_back_to_force_pop():
    """Legacy / forced-cleanup signature: when no specific socket is
    passed, the slot is cleared regardless of identity.  Preserved for
    callers that don't have a handle on the socket (none in the current
    tree, but the API stays back-compat)."""
    mgr = GameManager()
    mgr.register_ws("R", "P", _FakeWS())
    removed = mgr.unregister_ws("R", "P")  # no ws arg
    assert removed is True
    assert "P" not in mgr._ws_connections["R"]


def test_unregister_returns_false_when_slot_already_empty():
    """Double-disconnect or stray unregister: never raises, returns False."""
    mgr = GameManager()
    mgr.register_ws("R", "P", _FakeWS())
    mgr.unregister_ws("R", "P")  # remove
    assert mgr.unregister_ws("R", "P", _FakeWS()) is False
    assert mgr.unregister_ws("R", "P") is False


def test_thread_safe_send_uses_current_socket_after_reconnect():
    """Verifies the table reads back the latest socket — i.e. that the
    lock-wrapped lookup in ``_thread_safe_send`` sees the right entry
    even when ``register_ws`` ran on a different thread.  We can't
    exercise asyncio.run_coroutine_threadsafe without a running loop, but
    the lookup itself (``_ws_connections[room][player]``) is what would
    have been wrong before the fix."""
    mgr = GameManager()
    old = _FakeWS("old")
    new = _FakeWS("new")
    mgr.register_ws("R", "P", old)
    mgr.register_ws("R", "P", new)
    mgr.unregister_ws("R", "P", old)   # late finally from old socket

    # Look up via the same dict path _thread_safe_send takes.
    with mgr._ws_lock:
        live = mgr._ws_connections.get("R", {}).get("P")
    assert live is new, "Live lookup should return the reconnected socket"
