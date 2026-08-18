"""Terminal room client for GPT/Codex/Perplexity-style players.

This is intentionally provider-agnostic: it joins a server room as a normal
human player and bridges the server's WebSocket prompts to stdin/stdout. Any
LLM terminal session can run it, read the structured prompt, and type the
chosen response.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from dataclasses import dataclass
from typing import Any
from urllib import error, request
from urllib.parse import urlencode, urlparse, urlunparse


DEFAULT_SERVER = "http://127.0.0.1:8001"


@dataclass(frozen=True)
class JoinedPlayer:
    room_id: str
    player_id: str
    room_name: str
    join_code: str


def normalise_http_base(server: str) -> str:
    """Return a usable HTTP base URL, defaulting bare hosts to http://."""
    server = server.strip().rstrip("/")
    if not server:
        return DEFAULT_SERVER
    if "://" not in server:
        server = f"http://{server}"
    parsed = urlparse(server)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("server must use http:// or https://")
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", "", ""))


def websocket_url(http_base: str, room_id: str, player_id: str) -> str:
    parsed = urlparse(normalise_http_base(http_base))
    scheme = "wss" if parsed.scheme == "https" else "ws"
    path = f"{parsed.path.rstrip('/')}/ws/{room_id}/{player_id}"
    return urlunparse((scheme, parsed.netloc, path, "", "", ""))


def _api_url(http_base: str, path: str, query: dict[str, str] | None = None) -> str:
    parsed = urlparse(normalise_http_base(http_base))
    query_str = urlencode(query or {})
    return urlunparse(
        (parsed.scheme, parsed.netloc, f"{parsed.path.rstrip('/')}{path}", "", query_str, "")
    )


def _post_json(http_base: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
    data = json.dumps(body).encode("utf-8")
    req = request.Request(
        _api_url(http_base, path),
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"server returned HTTP {exc.code}: {detail}") from exc


def _get_json(http_base: str, path: str, query: dict[str, str] | None = None) -> dict[str, Any]:
    try:
        with request.urlopen(_api_url(http_base, path, query), timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"server returned HTTP {exc.code}: {detail}") from exc


def join_room_by_code(http_base: str, code: str, name: str) -> JoinedPlayer:
    payload = _post_json(
        http_base,
        "/api/rooms/join-by-code",
        {"code": code.strip().upper(), "name": name},
    )
    if "error" in payload:
        raise RuntimeError(str(payload["error"]))
    room = payload["room"]
    return JoinedPlayer(
        room_id=room["room_id"],
        player_id=payload["player_id"],
        room_name=room.get("name", "Island Traders"),
        join_code=room.get("join_code", code.strip().upper()),
    )


def _compact_player_line(player: dict[str, Any]) -> str:
    roles = player.get("roles") or player.get("role_names") or []
    role_text = ", ".join(roles) if isinstance(roles, list) else str(roles)
    treasury = player.get("treasury", player.get("dollops", "?"))
    return f"{player.get('name', '?')} [{role_text or 'no role'}] treasury={treasury}"


def render_game_state(msg: dict[str, Any], player_id: str) -> str:
    """Return a concise, LLM-readable state summary."""
    lines = [
        "",
        "=== GAME STATE ===",
        f"Year: {msg.get('year', '?')}  Season: {msg.get('season', '?')}",
    ]
    players = msg.get("players") or []
    me = next((p for p in players if str(p.get("lobby_player_id")) == str(player_id)), None)
    if me:
        lines.append(f"You: {_compact_player_line(me)}")
        inventory = me.get("inventory") or {}
        held = {k: v for k, v in inventory.items() if v}
        lines.append(f"Inventory: {json.dumps(held, sort_keys=True)}")
        hints = me.get("decision_hints") or me.get("needs") or []
        if hints:
            lines.append(f"Hints/needs: {json.dumps(hints, sort_keys=True)[:1200]}")
    else:
        lines.append("You are not assigned to an engine player yet.")
    lines.append("==================")
    return "\n".join(lines)


def _option_value(options: list[dict[str, Any]], raw: str) -> Any:
    raw = raw.strip()
    # An LLM often echoes a whole menu line like "3. Produce Food -> produce::..."
    # instead of a bare "3". Recover the choice from, in order of trust:
    #   1. an explicit "-> value" suffix, matched against option values,
    #   2. a leading option number,
    #   3. an exact value or label match.
    if "->" in raw:
        tail = raw.rsplit("->", 1)[1].strip()
        for opt in options:
            if tail == str(opt.get("value", opt.get("id"))):
                return opt.get("value", opt.get("id"))
    lead = re.match(r"\s*(\d+)", raw)
    if lead:
        idx = int(lead.group(1)) - 1
        if 0 <= idx < len(options):
            return options[idx].get("value", options[idx].get("id"))
    for opt in options:
        value = opt.get("value", opt.get("id"))
        if raw == str(value) or raw.lower() == str(opt.get("label", "")).lower():
            return value
    return raw


def _print_options(options: list[dict[str, Any]]) -> None:
    for idx, opt in enumerate(options, 1):
        value = opt.get("value", opt.get("id"))
        label = opt.get("label", opt.get("name", value))
        extra = opt.get("roles")
        suffix = f" ({extra})" if extra else ""
        print(f"  {idx}. {label}{suffix}  -> {value}")


async def _ainput(prompt: str) -> str:
    return await asyncio.to_thread(input, prompt)


async def _send(ws, payload: dict[str, Any]) -> None:
    await ws.send(json.dumps(payload))


async def _prompt_for_response(ws, msg: dict[str, Any]) -> None:
    msg_type = msg.get("type")
    if msg.get("request_summary"):
        print("\nRequest summary:")
        print(json.dumps(msg["request_summary"], indent=2, sort_keys=True))

    if msg_type in {"choose_action", "choose_resource", "choose_profession", "choose_option"}:
        title = msg.get("prompt") or f"{msg.get('player_name', 'Player')} — choose action"
        print(f"\n{title}")
        options = msg.get("options") or []
        _print_options(options)
        raw = await _ainput("Enter option number or value > ")
        await _send(ws, {"type": "response", "value": _option_value(options, raw)})
        return

    if msg_type == "choose_player":
        print(f"\n{msg.get('prompt', 'Choose player')}")
        options = msg.get("options") or []
        _print_options(options)
        raw = await _ainput("Enter player number or id > ")
        await _send(ws, {"type": "response", "value": _option_value(options, raw)})
        return

    if msg_type == "choose_quantity":
        print(f"\n{msg.get('prompt', 'Choose quantity')} [{msg.get('min')}–{msg.get('max')}]")
        raw = await _ainput("Quantity > ")
        await _send(ws, {"type": "response", "value": raw.strip()})
        return

    if msg_type == "confirm":
        print(f"\n{msg.get('prompt', 'Confirm?')}")
        raw = await _ainput("yes/no > ")
        await _send(ws, {"type": "response", "value": raw.strip().lower() in {"y", "yes", "true", "1"}})
        return

    if msg_type == "ask_dollop_amount":
        prefill = msg.get("prefill", 0)
        print(f"\n{msg.get('prompt', 'Amount?')}  max={msg.get('max')}  suggested={prefill}")
        raw = await _ainput("Dollops > ")
        await _send(ws, {"type": "response", "value": raw.strip()})
        return

    if msg_type == "ask_text":
        default = msg.get("default", "")
        print(f"\n{msg.get('prompt', 'Text?')}")
        raw = await _ainput(f"Text [{default}] > ")
        await _send(ws, {"type": "response", "value": raw.strip() or default})
        return

    if msg_type == "market_buy_bulk":
        print("\nMarket buy/bid prompt")
        print(json.dumps({"budget": msg.get("budget"), "market": msg.get("market")}, indent=2, sort_keys=True))
        print('Enter JSON, e.g. {"buy":{"Food":2},"bids":{"Oil":{"quantity":1,"price":12}}}')
        raw = await _ainput("JSON or blank to cancel > ")
        value: Any = None
        if raw.strip():
            try:
                value = json.loads(raw)
            except json.JSONDecodeError:
                value = raw.strip()
        await _send(ws, {"type": "response", "value": value})


async def _handle_auction_start(ws, msg: dict[str, Any]) -> None:
    print(f"\n=== AUCTION START === budget={msg.get('budget')} timer={msg.get('timer_seconds')}s")
    for role in msg.get("roles", []):
        print(f"  {role.get('name')}: {role.get('island')}")
    print("Commands: bid <Role> <Amount>, withdraw <Role>, blank/skip to wait.")
    while True:
        raw = (await _ainput("auction> ")).strip()
        if not raw or raw.lower() == "skip":
            return
        parts = raw.split()
        if len(parts) >= 3 and parts[0].lower() == "bid":
            role = " ".join(parts[1:-1])
            await _send(ws, {"type": "bid", "role_name": role, "amount": parts[-1]})
            return
        if len(parts) >= 2 and parts[0].lower() == "withdraw":
            await _send(ws, {"type": "withdraw_bid", "role_name": " ".join(parts[1:])})
            return
        print("Expected: bid <Role> <Amount> or withdraw <Role>")


async def _handle_investing_start(ws, msg: dict[str, Any]) -> None:
    print(f"\n=== INVESTING PHASE === budget={msg.get('budget')} timer={msg.get('timer_seconds')}s")
    mandatory = set(msg.get("mandatory") or [])
    selections = set(msg.get("selections") or mandatory)
    for item in msg.get("catalogue", []):
        mark = "*" if item.get("item_id") in selections else " "
        print(
            f"{mark} {item.get('item_id')} — {item.get('name')} "
            f"{item.get('cost')} Dp ({item.get('description', '')})"
        )
    print("Enter comma-separated item ids. Blank keeps current/mandatory selections.")
    raw = await _ainput("investments> ")
    chosen = [part.strip() for part in raw.split(",") if part.strip()] if raw.strip() else list(selections)
    await _send(ws, {"type": "investment_submit", "item_ids": chosen, "ready": True})


async def _handle_ready_prompt(ws, msg: dict[str, Any]) -> None:
    print(f"\n{msg.get('type')}: {json.dumps(msg, sort_keys=True)}")
    raw = await _ainput("Send ready? [y/N] > ")
    if raw.strip().lower() in {"y", "yes"}:
        await _send(ws, {"type": "ready", "ready": True})


async def run_client(server: str, code: str, name: str) -> None:
    try:
        import websockets
    except ImportError as exc:
        raise RuntimeError(
            'websockets is required. Install server extras with: pip install -e ".[server]"'
        ) from exc

    http_base = normalise_http_base(server)
    joined = join_room_by_code(http_base, code, name)
    print(
        f"Joined room {joined.room_name!r} ({joined.join_code}) as "
        f"{name!r}, player_id={joined.player_id}"
    )
    ws_url = websocket_url(http_base, joined.room_id, joined.player_id)
    print(f"Connecting {ws_url}")

    # The library default ping_timeout (20s) is too tight for a slow local-LLM
    # driver -- a single Ollama call occasionally spikes well past that (e.g.
    # two agents alternating against the same GPU can force a model reload),
    # which closes the connection mid-game with "keepalive ping timeout" even
    # though the client is still making progress.
    async with websockets.connect(ws_url, ping_interval=20, ping_timeout=90) as ws:
        await _send(ws, {"type": "get_state"})
        async for raw in ws:
            msg = json.loads(raw)
            msg_type = msg.get("type", "")
            if msg_type == "print":
                print(msg.get("text", ""))
            elif msg_type == "game_state":
                print(render_game_state(msg, joined.player_id))
            elif msg_type == "auction_start":
                await _handle_auction_start(ws, msg)
            elif msg_type == "auction_update":
                print(f"Auction update: {json.dumps(msg.get('auction', {}), sort_keys=True)[:1600]}")
            elif msg_type == "investing_start":
                await _handle_investing_start(ws, msg)
            elif msg_type in {
                "choose_action",
                "choose_resource",
                "choose_profession",
                "choose_option",
                "choose_player",
                "choose_quantity",
                "confirm",
                "ask_dollop_amount",
                "ask_text",
                "market_buy_bulk",
            }:
                await _prompt_for_response(ws, msg)
            elif msg_type == "choose_action_parked":
                print("\nYou are marked done for this season.")
                raw = await _ainput("Type 'undo' to resume, blank to stay done > ")
                if raw.strip().lower() == "undo":
                    await _send(ws, {"type": "ready", "ready": False})
            elif msg_type == "pre_season_start":
                await _handle_ready_prompt(ws, msg)
            elif msg_type == "ready_update":
                # Status broadcast (who is ready + countdown ticks), not a
                # decision point. Print it, but never re-prompt — otherwise an
                # automated player is asked to "ready" on every tick.
                print(f"ready_update: {json.dumps(msg, sort_keys=True)[:400]}")
            elif msg_type == "game_over":
                print("\n=== GAME OVER ===")
                print(json.dumps(msg, indent=2, sort_keys=True))
                return
            elif msg_type.endswith("_ack"):
                if msg.get("error"):
                    print(f"{msg_type}: {msg.get('error')}")
            elif msg_type in {"room_update", "auction_result", "investing_phase", "investing_resolved", "season_start", "season_resolved"}:
                print(f"\n{msg_type}: {json.dumps(msg, sort_keys=True)[:1600]}")
            elif msg_type == "error":
                print(f"ERROR: {msg.get('message')}", file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Join an Island Traders room by code as a terminal-controlled player."
    )
    parser.add_argument("code", help="Room join code, e.g. ABC123")
    parser.add_argument("--name", default="LLM Player", help="Player name to join/rejoin with")
    parser.add_argument("--server", default=DEFAULT_SERVER, help=f"Server base URL (default: {DEFAULT_SERVER})")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        asyncio.run(run_client(args.server, args.code, args.name))
    except KeyboardInterrupt:
        print("\nDisconnected.")


if __name__ == "__main__":
    main()
