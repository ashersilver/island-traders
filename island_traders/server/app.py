"""
Island Traders — WebSocket game server.

Provides:
  - REST endpoints for lobby management (create/join/list games)
  - WebSocket endpoint for real-time game play
  - Static file serving for the dashboard

Run directly:
    python -m island_traders.server.app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations
import asyncio
import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..engine.game import Game, GameConfig, PlayerSpec, GameSummary
from ..models.resource import ResourceType
from ..constants import SEASONS, CURRENCY_SYMBOL
from .ws_adapter import WebSocketIOAdapter

try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import HTMLResponse, JSONResponse
except ImportError:
    FastAPI = WebSocket = WebSocketDisconnect = None
    StaticFiles = HTMLResponse = JSONResponse = None

logger = logging.getLogger("island_traders.server")

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class LobbyPlayer:
    player_id: str          # UUID
    name: str
    role_name: str | None = None
    is_human: bool = True
    connected: bool = False

@dataclass
class GameRoom:
    room_id: str
    name: str
    max_players: int = 7
    num_years: int = 3
    status: str = "waiting"  # waiting | running | finished
    players: list[LobbyPlayer] = field(default_factory=list)
    creator_id: str = ""
    game: Game | None = None
    game_thread: threading.Thread | None = None
    io_adapter: WebSocketIOAdapter | None = None
    summary: GameSummary | None = None

    def to_dict(self) -> dict:
        return {
            "room_id": self.room_id,
            "name": self.name,
            "max_players": self.max_players,
            "num_years": self.num_years,
            "status": self.status,
            "player_count": len(self.players),
            "players": [
                {"player_id": p.player_id, "name": p.name,
                 "role_name": p.role_name, "connected": p.connected}
                for p in self.players
            ],
        }


# ---------------------------------------------------------------------------
# Game manager — holds all rooms and active games
# ---------------------------------------------------------------------------

class GameManager:
    def __init__(self):
        self.rooms: dict[str, GameRoom] = {}
        self._ws_connections: dict[str, dict[str, Any]] = {}  # room_id -> {player_id: ws}
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def create_room(self, name: str, max_players: int = 7,
                    num_years: int = 3, creator_name: str = "Host") -> GameRoom:
        room_id = str(uuid.uuid4())[:8]
        creator_id = str(uuid.uuid4())[:8]
        room = GameRoom(
            room_id=room_id, name=name,
            max_players=max_players, num_years=num_years,
            creator_id=creator_id,
        )
        room.players.append(LobbyPlayer(player_id=creator_id, name=creator_name))
        self.rooms[room_id] = room
        self._ws_connections[room_id] = {}
        return room

    def join_room(self, room_id: str, player_name: str,
                  role_name: str | None = None) -> tuple[GameRoom, LobbyPlayer] | None:
        room = self.rooms.get(room_id)
        if not room or room.status != "waiting":
            return None
        if len(room.players) >= room.max_players:
            return None
        player_id = str(uuid.uuid4())[:8]
        lp = LobbyPlayer(player_id=player_id, name=player_name, role_name=role_name)
        room.players.append(lp)
        return room, lp

    def add_ai_player(self, room_id: str, name: str,
                      role_name: str | None = None) -> LobbyPlayer | None:
        room = self.rooms.get(room_id)
        if not room or room.status != "waiting":
            return None
        if len(room.players) >= room.max_players:
            return None
        player_id = str(uuid.uuid4())[:8]
        lp = LobbyPlayer(player_id=player_id, name=name,
                          role_name=role_name, is_human=False)
        room.players.append(lp)
        return lp

    def start_game(self, room_id: str) -> bool:
        room = self.rooms.get(room_id)
        if not room or room.status != "waiting":
            return False
        if len(room.players) < 2:
            return False

        available_roles = ["Farmer", "Miner", "Transporter", "Educator",
                           "Banker", "Manufacturer", "Doctor"]
        used_roles: set[str] = set()

        specs = []
        for lp in room.players:
            role = lp.role_name
            if not role or role in used_roles:
                for r in available_roles:
                    if r not in used_roles:
                        role = r
                        break
            used_roles.add(role)
            lp.role_name = role
            specs.append(PlayerSpec(
                name=lp.name, role_names=[role], is_human=lp.is_human
            ))

        config = GameConfig(player_specs=specs, num_years=room.num_years)

        # Build send functions that bridge thread → asyncio
        player_send_fns: dict[int, object] = {}
        for idx, lp in enumerate(room.players):
            player_idx = idx
            def make_send(lp_id=lp.player_id, p_idx=player_idx):
                def send(msg):
                    self._thread_safe_send(room_id, lp_id, msg)
                return send
            player_send_fns[idx] = make_send()

        def broadcast(msg):
            self._thread_safe_broadcast(room_id, msg)

        io = WebSocketIOAdapter(
            game_id=room_id,
            broadcast_fn=broadcast,
            player_send_fns=player_send_fns,
        )

        game = Game(config, io, save_path=f"/tmp/island_traders_{room_id}.json")
        game.setup()
        room.game = game
        room.io_adapter = io
        room.status = "running"

        def run_game():
            try:
                summary = game.run()
                room.summary = summary
                room.status = "finished"
                broadcast({
                    "type": "game_over",
                    "winner": summary.winner.name,
                    "rankings": [
                        {"name": p.name, "roles": p.role_names(),
                         "wealth": round(w, 1)}
                        for p, w in summary.final_rankings
                    ],
                })
            except Exception as e:
                logger.exception("Game %s crashed", room_id)
                room.status = "finished"
                broadcast({"type": "error", "message": str(e)})

        thread = threading.Thread(target=run_game, daemon=True, name=f"game-{room_id}")
        room.game_thread = thread
        thread.start()
        return True

    def get_game_state(self, room_id: str, player_id: str | None = None) -> dict | None:
        room = self.rooms.get(room_id)
        if not room or not room.game:
            return None
        game = room.game
        prices = game.market.current_prices()

        players_data = []
        for p in game.players:
            pd = {
                "player_id": p.player_id,
                "name": p.name,
                "roles": p.role_names(),
                "dollops": round(p.dollops, 1),
                "wealth": round(p.total_wealth(prices), 1),
                "workforce_count": p.workforce.count,
                "workforce_active": len(p.workforce.active_workers),
                "workforce_efficiency": round(p.workforce.average_efficiency * 100),
                "production_capacity": round(p.production_capacity * 100),
                "population": p.population,
                "policies": [
                    pol.describe() for pol in p.insurance_policies if pol.active
                ],
            }
            # Full inventory only for requesting player or spectators
            lobby_player = next(
                (lp for lp in room.players if lp.player_id == player_id),
                None
            )
            if lobby_player and not lobby_player.is_human:
                # AI — show nothing
                pass
            else:
                pd["inventory"] = {
                    r.value: p.inventory.get(r)
                    for r in ResourceType if p.inventory.get(r) > 0
                }
            players_data.append(pd)

        market_data = {
            r.value: {
                "price": round(game.market.current_price(r), 2),
                "supply": game.market.supply.get(r, 0),
            }
            for r in ResourceType
        }

        return {
            "type": "game_state",
            "room_id": room_id,
            "status": room.status,
            "players": players_data,
            "market": market_data,
            "price_history": [
                {"year": s.year, "season": s.season,
                 "prices": {r.value: round(p, 2) for r, p in s.prices.items()}}
                for s in game.market.price_history[-8:]  # last 2 years
            ],
        }

    # ---- Thread-safe WebSocket sending ----

    def _thread_safe_send(self, room_id: str, lobby_player_id: str, msg: dict) -> None:
        ws = self._ws_connections.get(room_id, {}).get(lobby_player_id)
        if ws and self._loop:
            asyncio.run_coroutine_threadsafe(
                self._async_send(ws, msg), self._loop
            )

    def _thread_safe_broadcast(self, room_id: str, msg: dict) -> None:
        connections = self._ws_connections.get(room_id, {})
        if self._loop:
            for ws in connections.values():
                asyncio.run_coroutine_threadsafe(
                    self._async_send(ws, msg), self._loop
                )

    @staticmethod
    async def _async_send(ws, msg: dict) -> None:
        try:
            await ws.send_text(json.dumps(msg))
        except Exception:
            pass

    def register_ws(self, room_id: str, lobby_player_id: str, ws) -> None:
        if room_id not in self._ws_connections:
            self._ws_connections[room_id] = {}
        self._ws_connections[room_id][lobby_player_id] = ws

    def unregister_ws(self, room_id: str, lobby_player_id: str) -> None:
        conns = self._ws_connections.get(room_id, {})
        conns.pop(lobby_player_id, None)

    def handle_player_response(self, room_id: str, lobby_player_id: str, value) -> None:
        room = self.rooms.get(room_id)
        if room and room.io_adapter:
            room.io_adapter.receive_response(value)


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    if FastAPI is None:
        raise ImportError(
            "FastAPI and uvicorn are required for the game server. "
            "Install with: pip install fastapi uvicorn[standard] websockets"
        )

    app = FastAPI(title="Island Traders", version="0.1.0")
    manager = GameManager()

    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.on_event("startup")
    async def startup():
        manager.set_event_loop(asyncio.get_event_loop())

    # ---- REST: Lobby ----

    @app.get("/")
    async def index():
        html_path = static_dir / "index.html"
        if html_path.exists():
            return HTMLResponse(html_path.read_text())
        return HTMLResponse("<h1>Island Traders Server</h1><p>Dashboard at /static/index.html</p>")

    @app.post("/api/rooms")
    async def create_room(body: dict = {}):
        room = manager.create_room(
            name=body.get("name", "Game Room"),
            max_players=body.get("max_players", 7),
            num_years=body.get("num_years", 3),
            creator_name=body.get("creator_name", "Host"),
        )
        return JSONResponse(room.to_dict())

    @app.get("/api/rooms")
    async def list_rooms():
        return JSONResponse([r.to_dict() for r in manager.rooms.values()])

    @app.get("/api/rooms/{room_id}")
    async def get_room(room_id: str):
        room = manager.rooms.get(room_id)
        if not room:
            return JSONResponse({"error": "Room not found"}, status_code=404)
        return JSONResponse(room.to_dict())

    @app.post("/api/rooms/{room_id}/join")
    async def join_room(room_id: str, body: dict = {}):
        result = manager.join_room(
            room_id, body.get("name", "Player"),
            role_name=body.get("role_name"),
        )
        if not result:
            return JSONResponse({"error": "Cannot join room"}, status_code=400)
        room, lp = result
        return JSONResponse({
            "room": room.to_dict(),
            "player_id": lp.player_id,
        })

    @app.post("/api/rooms/{room_id}/ai")
    async def add_ai(room_id: str, body: dict = {}):
        lp = manager.add_ai_player(
            room_id, body.get("name", "AI Bot"),
            role_name=body.get("role_name"),
        )
        if not lp:
            return JSONResponse({"error": "Cannot add AI"}, status_code=400)
        return JSONResponse({"player_id": lp.player_id, "name": lp.name})

    @app.post("/api/rooms/{room_id}/start")
    async def start_game(room_id: str):
        ok = manager.start_game(room_id)
        if not ok:
            return JSONResponse({"error": "Cannot start game"}, status_code=400)
        return JSONResponse({"status": "running"})

    @app.get("/api/rooms/{room_id}/state")
    async def get_state(room_id: str, player_id: str = ""):
        state = manager.get_game_state(room_id, player_id)
        if not state:
            return JSONResponse({"error": "No game state"}, status_code=404)
        return JSONResponse(state)

    # ---- WebSocket: Game play ----

    @app.websocket("/ws/{room_id}/{player_id}")
    async def websocket_endpoint(websocket: WebSocket, room_id: str, player_id: str):
        await websocket.accept()

        room = manager.rooms.get(room_id)
        if not room:
            await websocket.close(code=4004, reason="Room not found")
            return

        lp = next((p for p in room.players if p.player_id == player_id), None)
        if not lp:
            await websocket.close(code=4004, reason="Player not in room")
            return
        lp.connected = True
        manager.register_ws(room_id, player_id, websocket)

        try:
            # Send current state on connect
            state = manager.get_game_state(room_id, player_id)
            if state:
                await websocket.send_text(json.dumps(state))

            while True:
                raw = await websocket.receive_text()
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                msg_type = msg.get("type", "")
                if msg_type == "response":
                    manager.handle_player_response(room_id, player_id, msg.get("value"))
                elif msg_type == "get_state":
                    state = manager.get_game_state(room_id, player_id)
                    if state:
                        await websocket.send_text(json.dumps(state))
                elif msg_type == "chat":
                    manager._thread_safe_broadcast(room_id, {
                        "type": "chat",
                        "from": lp.name,
                        "text": msg.get("text", ""),
                    })

        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.exception("WebSocket error for %s/%s", room_id, player_id)
        finally:
            lp.connected = False
            manager.unregister_ws(room_id, player_id)

    return app


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Island Traders Game Server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    try:
        import uvicorn
    except ImportError:
        print("uvicorn is required. Install with: pip install uvicorn[standard]")
        raise SystemExit(1)

    app = create_app()
    uvicorn.run(app, host=args.host, port=args.port, ws="wsproto")


if __name__ == "__main__":
    main()
