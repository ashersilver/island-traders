"""Stdio MCP server that exposes an Island Traders room as agent tools.

Why this exists
---------------
The `qwen_agent.py` driver is a *puppet*: it patches the interactive client's
stdin/stdout and injects a one-line LLM answer to whatever menu the game prints.
The model has no loop, no tools, no plan -- pure stimulus/response, menu by menu.

This server inverts that. It holds the WebSocket connection to a game room,
buffers the narrative and the current pending decision, and exposes a small set
of MCP tools. An external agent harness then owns the loop:

    get_game_state()  ->  reason  ->  submit_action(...)  ->  (repeat)

so it can plan multi-step plays ("raise capital -> buy the missing input ->
THEN produce") instead of reacting to one menu at a time. The tool layer also
enforces valid actions structurally, which removes the whole class of
"reply with the -> token, not the number" format bugs the puppet has to police
in its prompt.

Transport
---------
Implements the MCP stdio transport directly (newline-delimited JSON-RPC 2.0),
so it needs no `mcp` SDK -- only `websockets` (already the project's `server`
extra). Run it as the command an MCP client launches, e.g. for Codex:

    [mcp_servers.island_traders]
    command = "python"
    args = ["-m", "island_traders.mcp.game_server"]

then have the agent call `join_game` first, then loop get_game_state /
submit_action.
"""
from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

from island_traders.cli.agent_client import (
    join_room_by_code,
    normalise_http_base,
    render_game_state,
    websocket_url,
    _get_json,
    _option_value,
)

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "island-traders", "version": "0.1.0"}

# Message types the server pushes that represent a DECISION the player must make
# (i.e. the game is blocked waiting for a response over the WebSocket).
_DECISION_TYPES = {
    "choose_action", "choose_resource", "choose_profession", "choose_option",
    "choose_player", "choose_quantity", "confirm", "ask_dollop_amount",
    "ask_text", "market_buy_bulk", "auction_start", "investing_start",
    "pre_season_start",
}


# ── the game bridge: one live room connection ──────────────────────────────

class GameBridge:
    """Owns a single WebSocket connection to a room and tracks the latest
    pending decision plus a rolling narrative buffer."""

    def __init__(self) -> None:
        self.ws = None
        self.joined = None
        self.http_base: str | None = None
        self.room_id: str | None = None
        self._recv_task: asyncio.Task | None = None
        self._narrative: list[str] = []
        self._pending: dict[str, Any] | None = None
        self._game_over: dict[str, Any] | None = None
        # Fires whenever a new decision arrives or the game ends, so submit can
        # block until play advances to the next choice point.
        self._advanced = asyncio.Event()

    @property
    def connected(self) -> bool:
        return self.ws is not None and self._recv_task is not None and not self._recv_task.done()

    async def join(self, server: str, code: str, name: str) -> dict[str, Any]:
        import websockets  # local import: only needed when actually joining

        http_base = normalise_http_base(server)
        self.http_base = http_base
        # Blocking urllib join off the event loop.
        self.joined = await asyncio.to_thread(join_room_by_code, http_base, code, name)
        self.room_id = self.joined.room_id
        ws_url = websocket_url(http_base, self.joined.room_id, self.joined.player_id)
        # Match the driver's relaxed keepalive: a slow agent turn can exceed the
        # 20s library default and drop the connection mid-game.
        self.ws = await websockets.connect(ws_url, ping_interval=20, ping_timeout=90)
        await self._send({"type": "get_state"})
        self._recv_task = asyncio.create_task(self._recv_loop())
        return {
            "room_id": self.joined.room_id,
            "player_id": self.joined.player_id,
            "room_name": self.joined.room_name,
            "join_code": self.joined.join_code,
            "name": name,
        }

    async def reset(self) -> None:
        """Tear down any existing connection and clear all per-game state so
        this process can bind to a fresh room. Used when the previous game has
        ended -- the MCP server process is long-lived and reused across games,
        so join_game must be able to rebind rather than staying stuck on a
        finished room."""
        if self._recv_task and not self._recv_task.done():
            self._recv_task.cancel()
        if self.ws is not None:
            try:
                await self.ws.close()
            except Exception:  # noqa: BLE001
                pass
        self.ws = None
        self.joined = None
        self.room_id = None
        self._recv_task = None
        self._narrative = []
        self._pending = None
        self._game_over = None
        self._advanced = asyncio.Event()

    async def _send(self, payload: dict[str, Any]) -> None:
        await self.ws.send(json.dumps(payload))

    async def _recv_loop(self) -> None:
        try:
            async for raw in self.ws:
                msg = json.loads(raw)
                mtype = msg.get("type", "")
                if mtype == "print":
                    text = msg.get("text", "")
                    if text:
                        self._narrative.append(text)
                elif mtype == "game_state":
                    self._narrative.append(render_game_state(msg, self.joined.player_id))
                elif mtype == "auction_update":
                    self._narrative.append(
                        "Auction update: "
                        + json.dumps(msg.get("auction", {}), sort_keys=True)[:1200]
                    )
                elif mtype == "ready_update":
                    # status broadcast, not a decision -- keep it terse
                    self._narrative.append(
                        "ready_update: " + json.dumps(msg, sort_keys=True)[:300]
                    )
                elif mtype in _DECISION_TYPES:
                    self._pending = msg
                    self._advanced.set()
                elif mtype == "choose_action_parked":
                    self._narrative.append("You are marked done for this season.")
                elif mtype == "game_over":
                    # Record it as a CANDIDATE end, but do NOT tear down the
                    # receive loop: a spurious/early game_over frame (observed
                    # when the room host is removed mid-setup) would otherwise
                    # permanently stop surfacing decisions and wedge a live
                    # game. The room status is the source of truth (checked in
                    # submit()/get_game_state); keep draining so later decisions
                    # still reach the agent if the game is in fact running.
                    self._game_over = msg
                    self._advanced.set()
                elif mtype == "error":
                    self._narrative.append(f"ERROR: {msg.get('message')}")
                elif mtype.endswith("_ack"):
                    if msg.get("error"):
                        self._narrative.append(f"{mtype}: {msg.get('error')}")
                else:
                    # room_update, auction_result, season_resolved, etc.
                    self._narrative.append(
                        f"{mtype}: " + json.dumps(msg, sort_keys=True)[:800]
                    )
        except Exception as exc:  # noqa: BLE001 -- surface any drop to the agent
            self._narrative.append(f"[connection closed: {exc!r}]")
            self._advanced.set()

    def _drain_narrative(self) -> str:
        text = "\n".join(self._narrative)
        self._narrative.clear()
        return text

    def _pending_summary(self) -> dict[str, Any] | None:
        """Render the pending decision as a compact, tool-friendly object with
        the STABLE option tokens the agent should answer with."""
        p = self._pending
        if not p:
            return None
        mtype = p.get("type")
        out: dict[str, Any] = {"decision_type": mtype, "prompt": p.get("prompt")}
        if mtype in {"choose_action", "choose_resource", "choose_profession",
                     "choose_option", "choose_player"}:
            out["options"] = [
                {"value": o.get("value", o.get("id")),
                 "label": o.get("label", o.get("name")),
                 "roles": o.get("roles")}
                for o in (p.get("options") or [])
            ]
            out["how_to_answer"] = "submit_action(value=<one of options[].value>)"
        elif mtype == "choose_quantity":
            out["min"], out["max"] = p.get("min"), p.get("max")
            out["how_to_answer"] = "submit_action(value=<integer in [min,max]>)"
        elif mtype == "ask_dollop_amount":
            out["max"], out["suggested"] = p.get("max"), p.get("prefill")
            out["how_to_answer"] = "submit_action(value=<number up to max>)"
        elif mtype == "confirm":
            out["how_to_answer"] = "submit_action(value='yes' or 'no')"
        elif mtype == "ask_text":
            out["default"] = p.get("default", "")
            out["how_to_answer"] = "submit_action(value=<text>)"
        elif mtype == "market_buy_bulk":
            out["budget"], out["market"] = p.get("budget"), p.get("market")
            out["how_to_answer"] = (
                'submit_action(value=<JSON string, e.g. {"buy":{"Food":2}}>)'
            )
        elif mtype == "auction_start":
            out["budget"] = p.get("budget")
            out["roles"] = p.get("roles")
            out["how_to_answer"] = (
                "submit_action(value='bid <Role> <Amount>' | 'withdraw <Role>' | 'skip')"
            )
        elif mtype == "investing_start":
            out["budget"] = p.get("budget")
            out["catalogue"] = [
                {"item_id": i.get("item_id"), "name": i.get("name"),
                 "cost": i.get("cost"), "description": i.get("description")}
                for i in (p.get("catalogue") or [])
            ]
            out["mandatory"] = p.get("mandatory")
            out["how_to_answer"] = (
                "submit_action(value=<comma-separated item_ids, or '' to keep defaults>)"
            )
        elif mtype == "pre_season_start":
            out["how_to_answer"] = "submit_action(value='ready') to start the season"
        return out

    def state(self) -> dict[str, Any]:
        return {
            "narrative": self._drain_narrative(),
            "pending": self._pending_summary(),
            "game_over": self._game_over,
            "connected": self.connected,
        }

    async def _still_running(self) -> bool:
        """True if the room authoritatively reports the game is NOT finished.
        Used to reject a spurious/stale game_over so it can't wedge live play.
        On any query failure, assume running (do not manufacture an end)."""
        if not self.room_id:
            return False
        try:
            data = await asyncio.to_thread(_get_json, self.http_base, f"/api/rooms/{self.room_id}")
        except Exception:  # noqa: BLE001
            return True
        return data.get("status") != "finished"

    async def _reconcile_over(self) -> None:
        """If a game_over candidate is latched but the room is still running,
        it was spurious -- clear it so the agent can keep playing."""
        if self._game_over and await self._still_running():
            self._game_over = None
            self._narrative.append(
                "[note: a premature game_over was ignored; the game is still running]"
            )

    async def _poll_finished(self) -> None:
        """Authoritatively detect end-of-game via room status.

        For short (e.g. 1-year) games the terminal signal arrives as the room
        flipping to status "finished" after the season-timer/year-end
        resolution, which can lag the WS `game_over` frame past a client's
        patience window. If there is no pending decision and we haven't already
        recorded game_over, confirm termination out-of-band over HTTP so an
        agent gets a definitive end instead of an ambiguous stall. The final
        leaderboard is already in the narrative buffer (the server broadcasts
        it as print text before finishing)."""
        if self._game_over or self._pending or not self.room_id:
            return
        try:
            data = await asyncio.to_thread(_get_json, self.http_base, f"/api/rooms/{self.room_id}")
        except Exception:  # noqa: BLE001 -- a transient poll failure is not terminal
            return
        if data.get("status") == "finished":
            self._game_over = {
                "status": "finished",
                "note": "Room reports finished; the End-of-Year leaderboard is in "
                        "the narrative from get_game_state.",
            }

    async def submit(self, value: Any) -> dict[str, Any]:
        """Answer the current pending decision, then wait until play advances to
        the next decision (or the game ends), and return the fresh state."""
        if self._game_over:
            # Don't trust a latched game_over blindly -- verify against the
            # room. A spurious frame would otherwise refuse every action.
            await self._reconcile_over()
            if self._game_over:
                return {"error": "game is over", "game_over": self._game_over}
        p = self._pending
        if not p:
            return {"error": "no pending decision -- call get_game_state first"}
        envelope = self._build_envelope(p, value)
        if "error" in envelope:
            return envelope
        # consume this decision and wait for the next one
        self._pending = None
        self._advanced.clear()
        await self._send(envelope["payload"])
        # Wait for the receive loop to surface the next decision / game_over.
        # Poll room status periodically during the wait so end-of-game (which
        # may arrive as a status flip rather than a timely WS game_over frame)
        # is detected promptly instead of after a long hang. A quiet timeout
        # still returns whatever narrative accrued (e.g. the season is resolving
        # and the next prompt just hasn't arrived yet).
        loop = asyncio.get_running_loop()
        deadline = loop.time() + 150
        while not self._advanced.is_set():
            remaining = deadline - loop.time()
            if remaining <= 0:
                break
            try:
                await asyncio.wait_for(self._advanced.wait(), timeout=min(10, remaining))
            except asyncio.TimeoutError:
                if not self._pending and not self._game_over:
                    await self._poll_finished()
                    if self._game_over:
                        break
        return self.state()

    def _build_envelope(self, pending: dict[str, Any], value: Any) -> dict[str, Any]:
        """Map an agent-supplied value onto the exact WS response envelope the
        server expects for this decision type (mirrors agent_client.py)."""
        mtype = pending.get("type")
        if mtype in {"choose_action", "choose_resource", "choose_profession",
                     "choose_option", "choose_player"}:
            options = pending.get("options") or []
            return {"payload": {"type": "response",
                                "value": _option_value(options, str(value))}}
        if mtype in {"choose_quantity", "ask_dollop_amount", "ask_text"}:
            return {"payload": {"type": "response", "value": str(value).strip()}}
        if mtype == "confirm":
            truthy = str(value).strip().lower() in {"y", "yes", "true", "1"}
            return {"payload": {"type": "response", "value": truthy}}
        if mtype == "market_buy_bulk":
            parsed: Any = None
            raw = value if isinstance(value, str) else json.dumps(value)
            if raw and str(raw).strip():
                try:
                    parsed = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    parsed = str(raw).strip()
            return {"payload": {"type": "response", "value": parsed}}
        if mtype == "auction_start":
            raw = str(value).strip()
            if not raw or raw.lower() == "skip":
                return {"payload": {"type": "response", "value": "skip"}}
            parts = raw.split()
            if len(parts) >= 3 and parts[0].lower() == "bid":
                return {"payload": {"type": "bid",
                                    "role_name": " ".join(parts[1:-1]),
                                    "amount": parts[-1]}}
            if len(parts) >= 2 and parts[0].lower() == "withdraw":
                return {"payload": {"type": "withdraw_bid",
                                    "role_name": " ".join(parts[1:])}}
            return {"error": "auction: expected 'bid <Role> <Amount>', "
                             "'withdraw <Role>', or 'skip'"}
        if mtype == "investing_start":
            mandatory = list(pending.get("mandatory") or [])
            if isinstance(value, list):
                chosen = value
            else:
                raw = str(value).strip()
                chosen = ([p.strip() for p in raw.split(",") if p.strip()]
                          if raw else mandatory)
            return {"payload": {"type": "investment_submit",
                                "item_ids": chosen, "ready": True}}
        if mtype == "pre_season_start":
            return {"payload": {"type": "ready", "ready": True}}
        return {"error": f"unhandled decision type {mtype!r}"}


# ── MCP tool definitions (JSON schema) ─────────────────────────────────────

TOOLS = [
    {
        "name": "join_game",
        "description": (
            "Join an Island Traders room by its join code and open the live "
            "connection. Call this FIRST, once, before any other tool."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Room join code, e.g. ABC123"},
                "name": {"type": "string", "description": "Player display name"},
                "server": {"type": "string",
                           "description": "Server base URL (default http://127.0.0.1:8001)"},
            },
            "required": ["code"],
        },
    },
    {
        "name": "get_game_state",
        "description": (
            "Return everything that happened since the last call (narrative log) "
            "plus the CURRENT pending decision you must answer -- its type, the "
            "valid options with their stable tokens, and how_to_answer. Poll this "
            "at the top of every turn to observe before you act."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "submit_action",
        "description": (
            "Answer the current pending decision, then wait until play advances "
            "to the next decision (or the game ends) and return the fresh state. "
            "Use the 'value' shown in how_to_answer for the pending decision: an "
            "option token (e.g. 'produce::Farmer|Food|', 'take_loan', 'end_turn'), "
            "a number, 'yes'/'no', an auction 'bid <Role> <Amount>', comma-"
            "separated investment item_ids, or 'ready'."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "value": {"description": "The answer for the pending decision "
                                          "(string, number, or JSON)."},
            },
            "required": ["value"],
        },
    },
]


# ── JSON-RPC / MCP stdio plumbing ──────────────────────────────────────────

def _content(obj: Any) -> dict[str, Any]:
    """Wrap a Python object as an MCP text-content tool result."""
    text = obj if isinstance(obj, str) else json.dumps(obj, indent=2, sort_keys=True)
    return {"content": [{"type": "text", "text": text}], "isError": False}


async def _dispatch_tool(bridge: GameBridge, name: str, args: dict[str, Any]) -> dict[str, Any]:
    if name == "join_game":
        # The MCP server process is long-lived and reused across games. Refuse
        # only if we're in a genuinely ACTIVE game; otherwise (fresh process,
        # finished game, or a stale/latched game_over) tear down and rebind to
        # the requested room so a new game can start without restarting the
        # harness.
        if bridge.connected and not bridge._game_over and await bridge._still_running():
            prev = bridge.joined.join_code if bridge.joined else "?"
            return _content({"error": f"already in an active game (room {prev}); "
                             "finish or leave it before joining another"})
        await bridge.reset()
        info = await bridge.join(
            server=args.get("server") or "http://127.0.0.1:8001",
            code=args["code"],
            name=args.get("name") or "MCP Agent",
        )
        # give the first prompt a moment to arrive
        try:
            await asyncio.wait_for(bridge._advanced.wait(), timeout=15)
        except asyncio.TimeoutError:
            pass
        return _content({"joined": info, "state": bridge.state()})
    if not bridge.connected and name in {"get_game_state", "submit_action"}:
        return _content({"error": "not joined -- call join_game first"})
    if name == "get_game_state":
        if bridge._game_over:
            await bridge._reconcile_over()
        if not bridge._pending and not bridge._game_over:
            await bridge._poll_finished()
        return _content(bridge.state())
    if name == "submit_action":
        return _content(await bridge.submit(args.get("value")))
    return {"content": [{"type": "text", "text": f"unknown tool {name!r}"}], "isError": True}


async def _handle(bridge: GameBridge, msg: dict[str, Any]) -> dict[str, Any] | None:
    """Handle one JSON-RPC request; return a response dict, or None for a
    notification (no reply)."""
    method = msg.get("method")
    mid = msg.get("id")

    def ok(result: Any) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": mid, "result": result}

    def err(code: int, message: str) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}

    if method == "initialize":
        return ok({
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": SERVER_INFO,
        })
    if method in {"notifications/initialized", "initialized"}:
        return None  # notification
    if method == "ping":
        return ok({})
    if method == "tools/list":
        return ok({"tools": TOOLS})
    if method == "tools/call":
        params = msg.get("params") or {}
        name = params.get("name")
        args = params.get("arguments") or {}
        try:
            return ok(await _dispatch_tool(bridge, name, args))
        except Exception as exc:  # noqa: BLE001
            return ok({"content": [{"type": "text", "text": f"tool error: {exc!r}"}],
                       "isError": True})
    if mid is None:
        return None  # unknown notification -- ignore
    return err(-32601, f"method not found: {method}")


async def serve() -> None:
    bridge = GameBridge()
    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader()
    await loop.connect_read_pipe(lambda: asyncio.StreamReaderProtocol(reader), sys.stdin)
    while True:
        line = await reader.readline()
        if not line:
            break
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        response = await _handle(bridge, msg)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


def main() -> None:
    try:
        asyncio.run(serve())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
