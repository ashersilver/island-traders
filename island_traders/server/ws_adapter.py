"""
WebSocket IO adapter — bridges the synchronous game engine to async WebSocket clients.

The game engine calls IOAdapter methods synchronously (print, choose_action, confirm, etc.).
This adapter translates each call into a WebSocket message sent to the active player's client
and blocks (via an asyncio Event) until the client responds.

The game loop runs in a background thread; each IO call posts a message to the WebSocket
send queue and waits on a response future.
"""
from __future__ import annotations
import asyncio
import json
import threading
from ..cli.prompts import IOAdapter
from ..models.resource import ResourceType
from ..engine.turn import TurnAction


class WebSocketIOAdapter(IOAdapter):
    """
    Replaces the CLI IOAdapter for online play.

    Communication protocol:
    - Server → Client: JSON messages with "type" field
    - Client → Server: JSON messages with "type": "response" + payload

    Message types sent:
        print        — display text to all connected clients
        choose_action — present action menu to active player, await choice
        choose_resource — present resource picker, await choice
        choose_quantity — present numeric input, await int
        choose_player — present player picker, await choice
        confirm      — present yes/no, await bool
        choose_profession — present profession picker, await choice
        ask_dollop_amount — present amount input, await float
        game_state   — full game state snapshot (broadcast)
    """

    def __init__(self, game_id: str, broadcast_fn, player_send_fns: dict[int, object]):
        self._game_id = game_id
        self._broadcast = broadcast_fn
        self._player_send_fns = player_send_fns
        self._response_event = threading.Event()
        self._response_value = None
        self._active_player_id: int | None = None
        self._lock = threading.Lock()
        self._log: list[str] = []

    def set_active_player(self, player_id: int) -> None:
        self._active_player_id = player_id

    def _send_to_active(self, msg: dict) -> None:
        pid = self._active_player_id
        send_fn = self._player_send_fns.get(pid)
        if send_fn:
            send_fn(msg)

    def _send_and_wait(self, msg: dict) -> object:
        with self._lock:
            self._response_event.clear()
            self._response_value = None
        self._send_to_active(msg)
        self._response_event.wait(timeout=300)
        return self._response_value

    def receive_response(self, value: object) -> None:
        with self._lock:
            self._response_value = value
            self._response_event.set()

    def print(self, text: str) -> None:
        self._log.append(text)
        self._broadcast({"type": "print", "text": text})

    def choose_action(self, player, available: list[TurnAction]) -> TurnAction:
        self.set_active_player(player.player_id)
        options = [{"value": a.value, "label": a.value.replace("_", " ").title()} for a in available]
        resp = self._send_and_wait({
            "type": "choose_action",
            "player_id": player.player_id,
            "player_name": player.name,
            "options": options,
        })
        if resp is None:
            return TurnAction.END_TURN
        try:
            return TurnAction(resp)
        except ValueError:
            return TurnAction.END_TURN

    def choose_resource(self, prompt: str, available: list[ResourceType]) -> ResourceType:
        options = [{"value": r.value, "label": r.value} for r in available]
        resp = self._send_and_wait({
            "type": "choose_resource",
            "prompt": prompt,
            "options": options,
        })
        if resp is None:
            return available[0]
        try:
            return ResourceType(resp)
        except ValueError:
            return available[0]

    def choose_quantity(self, prompt: str, min_qty: int, max_qty: int) -> int:
        resp = self._send_and_wait({
            "type": "choose_quantity",
            "prompt": prompt,
            "min": min_qty,
            "max": max_qty,
        })
        if resp is None:
            return min_qty
        try:
            val = int(resp)
            return max(min_qty, min(val, max_qty))
        except (ValueError, TypeError):
            return min_qty

    def choose_player(self, prompt: str, players: list) -> object:
        options = [{"id": p.player_id, "name": p.name, "roles": p.role_names()} for p in players]
        resp = self._send_and_wait({
            "type": "choose_player",
            "prompt": prompt,
            "options": options,
        })
        if resp is None:
            return players[0]
        try:
            pid = int(resp)
            return next((p for p in players if p.player_id == pid), players[0])
        except (ValueError, TypeError):
            return players[0]

    def confirm(self, prompt: str) -> bool:
        resp = self._send_and_wait({
            "type": "confirm",
            "prompt": prompt,
        })
        if resp is None:
            return True
        return str(resp).lower() in ("true", "y", "yes", "1")

    def choose_profession(self, prompt: str, available: list[str]) -> str:
        options = [{"value": p, "label": p} for p in available]
        resp = self._send_and_wait({
            "type": "choose_profession",
            "prompt": prompt,
            "options": options,
        })
        if resp and resp in available:
            return resp
        return available[0] if available else ""

    def ask_dollop_amount(self, prompt: str, max_dollops: float) -> float:
        resp = self._send_and_wait({
            "type": "ask_dollop_amount",
            "prompt": prompt,
            "max": max_dollops,
        })
        if resp is None:
            return 0.0
        try:
            val = float(resp)
            return max(-max_dollops, min(val, max_dollops))
        except (ValueError, TypeError):
            return 0.0
