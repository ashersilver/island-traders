"""
WebSocket IO adapter — bridges the synchronous game engine to async WebSocket clients.

Concurrent per-player design:
  Each human player runs their own turn on its own thread. Per-player threads
  call IOAdapter methods to prompt the user; each call routes to that player's
  own threading.Event so prompts to different players don't interfere.

  The "active player" is tracked in thread-local state, set when each player's
  turn begins. Action handlers that prompt without passing a player_id reuse
  the TLS active player.

  `interrupt_all(reason)` is used by the season timer to force-unblock every
  pending prompt with a sentinel response (None), causing each player's turn
  loop to exit cleanly via the action handlers' None-fallbacks and an
  END_TURN return from any pending choose_action.
"""
from __future__ import annotations
import logging
import threading
from ..cli.prompts import IOAdapter, ActionCancelled, CANCEL_SENTINEL, action_label
from ..models.resource import ResourceType
from ..models.profession import Profession, PROFESSION_LABEL
from ..engine.turn import TurnAction

logger = logging.getLogger("island_traders.ws_adapter")


ACTION_GROUPS: dict[TurnAction, str] = {
    TurnAction.PRODUCE: "Production",
    TurnAction.APPLY_PATENT: "Production",
    TurnAction.MARKET_BUY: "Trade",
    TurnAction.MARKET_SELL: "Trade",
    TurnAction.PROPOSE_DEAL: "Trade",
    TurnAction.REQUEST_TRAINING: "People",
    TurnAction.REVIEW_TRAINING: "People",
    TurnAction.ARRANGE_TRANSPORT: "People",
    TurnAction.RECRUIT_WORKERS: "People",
    TurnAction.PURCHASE_CAPITAL: "Capital",
    TurnAction.INVEST: "Capital",
    TurnAction.TAKE_LOAN: "Finance",
    TurnAction.OFFER_LOAN: "Finance",
    TurnAction.ROLLOVER_LOAN: "Finance",
    TurnAction.VIEW_LOANS: "Finance",
    TurnAction.BUY_INSURANCE: "Finance",
    TurnAction.SELL_INSURANCE: "Finance",
    TurnAction.MANAGE_INSURANCE: "Finance",
    TurnAction.VIEW_MARKET: "Info",
    TurnAction.VIEW_PLAYERS: "Info",
    TurnAction.INVENTORY: "Info",
    TurnAction.END_TURN: "Info",
}


def _player_has_role(player, role_name: str) -> bool:
    return any(getattr(role, "name", None) == role_name for role in getattr(player, "roles", []))


def action_option_payload(action: TurnAction, player) -> dict:
    """Structured action option metadata for dashboard clients."""
    enabled = True
    disabled_reason = ""

    if action == TurnAction.OFFER_LOAN and not _player_has_role(player, "Banker"):
        enabled = False
        disabled_reason = "Only Banking can offer loans."
    elif action == TurnAction.SELL_INSURANCE and not _player_has_role(player, "Banker"):
        enabled = False
        disabled_reason = "Only Banking can sell insurance."
    elif action == TurnAction.ARRANGE_TRANSPORT and not _player_has_role(player, "Transporter"):
        enabled = False
        disabled_reason = "Only Transportation can arrange training transport."
    elif action == TurnAction.APPLY_PATENT and player.inventory.get(ResourceType.PATENTS) <= 0:
        enabled = False
        disabled_reason = "No Patents available to apply."

    return {
        "value": action.value,
        "label": action_label(action),
        "group": ACTION_GROUPS.get(action, "Info"),
        "enabled": enabled,
        "disabled_reason": disabled_reason,
        "recommended": False,
    }


class WebSocketIOAdapter(IOAdapter):
    """Per-player, thread-safe IO adapter for online play.

    Communication protocol (server → client):
        print, choose_action, choose_resource, choose_quantity, choose_player,
        confirm, choose_profession, ask_dollop_amount, market_buy_bulk,
        game_state, season_start, season_timer, season_resolved, ready_update.

    Client → server: {type:"response", value:<...>} routed via receive_response.
    """

    def __init__(self, game_id: str, broadcast_fn, player_send_fns: dict[int, object]):
        self._game_id = game_id
        self._broadcast = broadcast_fn
        # player_idx (engine Player.player_id, an int) → send fn
        self._player_send_fns = player_send_fns

        # Global init lock — protects _ensure_player from concurrent creation
        # of Event/Lock objects for the same player_id.
        self._init_lock = threading.Lock()

        # Per-player synchronisation primitives
        self._player_events: dict[int, threading.Event] = {}
        self._player_responses: dict[int, object] = {}
        self._player_locks: dict[int, threading.Lock] = {}
        self._player_pending_msgs: dict[int, dict] = {}
        # Per-player "ready/end turn" flag — when set, the next choose_action
        # for that player returns END_TURN immediately (used by the Ready
        # button to short-circuit any further prompts even if the user is
        # currently mid-action).
        self._player_ready_flags: set[int] = set()

        # Thread-local "active player" — set by choose_action() at the start
        # of each player's prompt-chain so subsequent choose_resource/quantity/
        # confirm/etc. calls inside that thread route to the right player.
        self._tls = threading.local()

        # Season-level interrupt flag — when set, _send_and_wait returns None
        # immediately rather than blocking. Cleared at the start of each season.
        self._interrupted = False

        self._log: list[str] = []
        self.on_action_complete = None

    # ---- per-player primitives ----

    def _ensure_player(self, pid: int) -> None:
        # Fast path: already initialised (no lock needed).
        if pid in self._player_events:
            return
        # Slow path: hold the init lock so two threads don't both create
        # Event/Lock objects for the same pid (race that caused bug #2).
        with self._init_lock:
            if pid not in self._player_events:
                self._player_events[pid] = threading.Event()
                self._player_responses[pid] = None
                self._player_locks[pid] = threading.Lock()

    def _active_pid(self) -> int | None:
        return getattr(self._tls, "active_player_id", None)

    def set_active_player(self, player_id: int) -> None:
        """Set the active player for THIS thread (TLS)."""
        self._tls.active_player_id = player_id
        self._ensure_player(player_id)

    # ---- season-level interrupt ----

    def begin_season(self) -> None:
        """Reset interrupt + ready flags at the start of a new season."""
        self._interrupted = False
        self._player_ready_flags.clear()

    def mark_player_ready(self, player_id: int) -> None:
        """Mark a player as Ready; their next choose_action returns END_TURN."""
        self._player_ready_flags.add(player_id)
        # Also unblock anything they're currently waiting on with a sentinel
        # so the in-flight prompt completes quickly.
        self.receive_response(player_id, "end_turn")

    def unmark_player_ready(self, player_id: int) -> None:
        """Clear a player's Ready flag (e.g. they un-click Ready)."""
        self._player_ready_flags.discard(player_id)

    def interrupt_all(self) -> None:
        """Unblock every pending player prompt with a None response.

        Called when the season timer fires. Each waiting thread will see
        None and fall through to default/empty behaviour (and choose_action
        returns END_TURN, which exits the action loop).
        """
        self._interrupted = True
        for pid, ev in list(self._player_events.items()):
            with self._player_locks[pid]:
                self._player_responses[pid] = None
                self._player_pending_msgs.pop(pid, None)
                ev.set()

    # ---- core send/wait ----

    def _send_to(self, pid: int, msg: dict) -> None:
        send_fn = self._player_send_fns.get(pid)
        if send_fn:
            send_fn(msg)

    def _send_and_wait(self, msg: dict, timeout: float = 300) -> object:
        pid = self._active_pid()
        if pid is None:
            # No active player on this thread — fall back to defaults.
            logger.warning("_send_and_wait called with no active player (TLS)")
            return None
        self._ensure_player(pid)

        if self._interrupted:
            return None

        msg.setdefault("player_id", pid)

        # Single lock acquisition: clear event, store pending msg, THEN send.
        # Previously this was two separate `with` blocks, leaving a gap where
        # interrupt_all() or receive_response() could fire between event.clear()
        # and the message being stored — causing the response to be swallowed
        # and the player's action menu to vanish (bug #2).
        with self._player_locks[pid]:
            self._player_events[pid].clear()
            self._player_responses[pid] = None
            self._player_pending_msgs[pid] = dict(msg)

        self._send_to(pid, msg)

        signalled = self._player_events[pid].wait(timeout=timeout)
        with self._player_locks[pid]:
            value = self._player_responses[pid]
            self._player_responses[pid] = None
            self._player_pending_msgs.pop(pid, None)

        if not signalled:
            logger.warning(
                "Player %d: _send_and_wait timed out after %.0fs for %s",
                pid, timeout, msg.get("type", "?"),
            )

        if self.on_action_complete and msg.get("type") != "choose_action":
            try:
                self.on_action_complete()
            except Exception:
                pass
        return value

    def receive_response(self, player_id: int, value: object) -> None:
        """Route an incoming WS response to the right player's event."""
        if player_id is None:
            return
        self._ensure_player(player_id)
        with self._player_locks[player_id]:
            self._player_responses[player_id] = value
            self._player_pending_msgs.pop(player_id, None)
            self._player_events[player_id].set()

    def replay_pending_prompt(self, player_id: int) -> bool:
        """Re-send the current unresolved prompt after a client reconnects."""
        self._ensure_player(player_id)
        with self._player_locks[player_id]:
            msg = self._player_pending_msgs.get(player_id)
            if not msg:
                return False
            replay = dict(msg)
            replay["replayed"] = True
        self._send_to(player_id, replay)
        return True

    # ---- IOAdapter interface ----

    def print(self, text: str) -> None:
        self._log.append(text)
        self._broadcast({"type": "print", "text": text})

    def choose_action(self, player, available: list[TurnAction]) -> TurnAction:
        # Set TLS active player for this thread so subsequent prompts in this
        # action chain route correctly.
        self.set_active_player(player.player_id)
        # Honour the Ready flag — short-circuit straight to END_TURN.
        if player.player_id in self._player_ready_flags:
            logger.debug("Player %d (%s): Ready flag set, returning END_TURN",
                         player.player_id, player.name)
            return TurnAction.END_TURN
        if self._interrupted:
            logger.debug("Player %d (%s): season interrupted, returning END_TURN",
                         player.player_id, player.name)
            return TurnAction.END_TURN
        options = [action_option_payload(a, player) for a in available]
        resp = self._send_and_wait({
            "type": "choose_action",
            "player_id": player.player_id,
            "player_name": player.name,
            "options": options,
        })
        if resp is None:
            logger.warning("Player %d (%s): choose_action got None response — "
                           "ending turn (interrupted=%s, ready=%s)",
                           player.player_id, player.name,
                           self._interrupted,
                           player.player_id in self._player_ready_flags)
            return TurnAction.END_TURN
        try:
            return TurnAction(resp)
        except ValueError:
            logger.warning("Player %d (%s): invalid action '%s', ending turn",
                           player.player_id, player.name, resp)
            return TurnAction.END_TURN

    @staticmethod
    def _check_cancel(resp) -> None:
        """Raise ActionCancelled if the response is the explicit Cancel sentinel.

        A plain `None` is treated as "no answer" (timeout / interrupt) by each
        prompt method's existing fallback — only an explicit cancel from the
        user maps to this exception.
        """
        if resp == CANCEL_SENTINEL:
            raise ActionCancelled()

    def choose_resource(self, prompt: str, available: list[ResourceType]) -> ResourceType:
        options = [{"value": r.value, "label": r.value} for r in available]
        resp = self._send_and_wait({
            "type": "choose_resource",
            "prompt": prompt,
            "options": options,
        })
        self._check_cancel(resp)
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
        self._check_cancel(resp)
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
        self._check_cancel(resp)
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
        self._check_cancel(resp)
        if resp is None:
            return False
        return str(resp).lower() in ("true", "y", "yes", "1")

    def choose_profession(self, prompt: str, available: list[str]) -> str:
        def _label(profession: str) -> str:
            try:
                return PROFESSION_LABEL.get(Profession(profession), profession)
            except ValueError:
                return profession

        options = [{"value": p, "label": _label(p)} for p in available]
        resp = self._send_and_wait({
            "type": "choose_profession",
            "prompt": prompt,
            "options": options,
        })
        self._check_cancel(resp)
        if resp and resp in available:
            return resp
        return available[0] if available else ""

    def choose_option(self, prompt: str, options: list[dict]) -> object:
        """Present named choices (buttons), return the chosen option's value.

        `options` is `[{"value": <json-serialisable>, "label": str}, ...]`.
        The client renders these as buttons (reusing the option picker) and
        sends back the value as a string; we match on str(value).
        """
        resp = self._send_and_wait({
            "type": "choose_option",
            "prompt": prompt,
            "options": [
                {"value": o["value"], "label": o["label"]} for o in options
            ],
        })
        self._check_cancel(resp)
        if resp is None:
            return options[0]["value"] if options else None
        for o in options:
            if str(o["value"]) == str(resp):
                return o["value"]
        return options[0]["value"] if options else None

    def ask_dollop_amount(self, prompt: str, max_dollops: float,
                          prefill: float = 0.0) -> float:
        resp = self._send_and_wait({
            "type": "ask_dollop_amount",
            "prompt": prompt,
            "max": max_dollops,
            "prefill": round(prefill, 2) if prefill else 0,
        })
        self._check_cancel(resp)
        if resp is None:
            return 0.0
        try:
            val = float(resp)
            return max(-max_dollops, min(val, max_dollops))
        except (ValueError, TypeError):
            return 0.0

    def ask_text(self, prompt: str, default: str = "") -> str:
        resp = self._send_and_wait({
            "type": "ask_text",
            "prompt": prompt,
            "default": default,
        })
        self._check_cancel(resp)
        if resp is None:
            return default
        return str(resp).strip() or default

    def market_buy_bulk(self, player, market_summary: dict) -> dict[str, int] | None:
        # Ensure the TLS active_player is set even when called outside the
        # standard choose_action → action chain (paranoia for direct calls).
        self.set_active_player(player.player_id)
        resp = self._send_and_wait({
            "type": "market_buy_bulk",
            "player_name": player.name,
            "player_id": player.player_id,
            "budget": round(player.dollops, 1),
            "market": market_summary,
        })
        self._check_cancel(resp)
        if resp is None:
            return None
        def _normalise(parsed):
            if not isinstance(parsed, dict):
                return None
            if "buy" in parsed or "bids" in parsed:
                buys = {k: int(v) for k, v in (parsed.get("buy") or {}).items() if int(v) > 0}
                bids = {}
                for k, v in (parsed.get("bids") or {}).items():
                    if not isinstance(v, dict):
                        continue
                    qty = int(v.get("quantity", 0))
                    price = float(v.get("price", 0))
                    if qty > 0 and price > 0:
                        bids[k] = {"quantity": qty, "price": price}
                return {"buy": buys, "bids": bids}
            return {k: int(v) for k, v in parsed.items() if int(v) > 0}

        if isinstance(resp, dict):
            return _normalise(resp)
        if isinstance(resp, str):
            import json as _json
            try:
                return _normalise(_json.loads(resp))
            except Exception:
                return None
        return None
