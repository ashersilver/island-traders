"""
Island Traders — WebSocket game server.

Provides:
  - REST endpoints for lobby management (create/join/list games)
  - Role auction phase before game start
  - WebSocket endpoint for real-time game play
  - Static file serving for the dashboard

Run directly:
    python -m island_traders.server.app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations
import asyncio
import json
import logging
import random
import string
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..engine.game import Game, GameConfig, PlayerSpec, GameSummary
from ..models.resource import ResourceType
from ..constants import (
    SEASONS, CURRENCY_SYMBOL,
    TOTAL_STARTING_DOLLOPS, TOTAL_STARTING_POPULATION,
)
from .ws_adapter import WebSocketIOAdapter

try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import HTMLResponse, JSONResponse
except ImportError:
    FastAPI = WebSocket = WebSocketDisconnect = None
    StaticFiles = HTMLResponse = JSONResponse = None

logger = logging.getLogger("island_traders.server")

ALL_ROLES = ["Farmer", "Miner", "Transporter", "Educator",
             "Banker", "Manufacturer", "Doctor"]

ROLE_INFO = {
    "Farmer":       {"island": "Agriculture, Fisheries & Foods", "produces": "Food, Fish",
                     "needs": "Farm Machinery, Oil", "color": "#27ae60"},
    "Miner":        {"island": "Mining & Oil", "produces": "Ore, Oil",
                     "needs": "Mining Equipment, Freight", "color": "#e67e22"},
    "Transporter":  {"island": "Transportation & Shipping", "produces": "Freight",
                     "needs": "Transport Equipment, Oil", "color": "#3498db"},
    "Educator":     {"island": "Education & Training", "produces": "Knowledge",
                     "needs": "Capital Equipment, Finance", "color": "#9b59b6"},
    "Banker":       {"island": "Banking & Insurance", "produces": "Finance",
                     "needs": "Knowledge, Capital Equipment", "color": "#f1c40f"},
    "Manufacturer": {"island": "Manufacturing (ForgeHaven)", "produces": "Machinery, Equipment",
                     "needs": "Ore, Oil, Freight", "color": "#1abc9c"},
    "Doctor":       {"island": "Healthcare", "produces": "Health Services, Vaccine",
                     "needs": "Knowledge, Medical Devices", "color": "#e74c3c"},
}

AUCTION_DURATION_SECONDS = 60


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

def _short_id() -> str:
    return str(uuid.uuid4())[:8]


def _join_code() -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=6))


@dataclass
class RoleBid:
    player_id: str
    player_name: str
    amount: float
    timestamp: float


@dataclass
class AuctionState:
    bids: dict[str, list[RoleBid]] = field(default_factory=dict)
    assignments: dict[str, str] = field(default_factory=dict)
    budget_spent: dict[str, float] = field(default_factory=dict)
    phase: str = "bidding"
    timer_end: float = 0.0
    _timer_task: Any = field(default=None, repr=False)

    def to_dict(self) -> dict:
        bids_out = {}
        for role, bid_list in self.bids.items():
            bids_out[role] = [
                {"player_id": b.player_id, "player_name": b.player_name,
                 "amount": round(b.amount, 1)}
                for b in bid_list
            ]
        return {
            "bids": bids_out,
            "assignments": self.assignments,
            "phase": self.phase,
            "timer_remaining": max(0, round(self.timer_end - time.time(), 1)),
        }


@dataclass
class LobbyPlayer:
    player_id: str
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
    is_public: bool = True
    join_code: str = ""
    require_all_human: bool = False
    status: str = "waiting"  # waiting | auction | running | finished
    players: list[LobbyPlayer] = field(default_factory=list)
    creator_id: str = ""
    auction: AuctionState | None = None
    game: Game | None = None
    game_thread: threading.Thread | None = None
    io_adapter: WebSocketIOAdapter | None = None
    summary: GameSummary | None = None

    def to_dict(self) -> dict:
        d = {
            "room_id": self.room_id,
            "name": self.name,
            "max_players": self.max_players,
            "num_years": self.num_years,
            "is_public": self.is_public,
            "join_code": self.join_code,
            "require_all_human": self.require_all_human,
            "status": self.status,
            "player_count": len([p for p in self.players if p.is_human]),
            "players": [
                {"player_id": p.player_id, "name": p.name,
                 "role_name": p.role_name, "is_human": p.is_human,
                 "connected": p.connected}
                for p in self.players
            ],
        }
        if self.auction:
            d["auction"] = self.auction.to_dict()
        return d


# ---------------------------------------------------------------------------
# Game manager — holds all rooms and active games
# ---------------------------------------------------------------------------

class GameManager:
    def __init__(self):
        self.rooms: dict[str, GameRoom] = {}
        self._code_index: dict[str, str] = {}  # join_code -> room_id
        self._ws_connections: dict[str, dict[str, Any]] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    # ---- Room management ----

    def create_room(self, name: str, max_players: int = 7,
                    num_years: int = 3, creator_name: str = "Host",
                    is_public: bool = True,
                    require_all_human: bool = False) -> GameRoom:
        room_id = _short_id()
        creator_id = _short_id()
        code = _join_code()
        room = GameRoom(
            room_id=room_id, name=name,
            max_players=max_players, num_years=num_years,
            is_public=is_public, join_code=code,
            require_all_human=require_all_human,
            creator_id=creator_id,
        )
        room.players.append(LobbyPlayer(player_id=creator_id, name=creator_name))
        self.rooms[room_id] = room
        self._code_index[code] = room_id
        self._ws_connections[room_id] = {}
        return room

    def find_room_by_code(self, code: str) -> GameRoom | None:
        room_id = self._code_index.get(code.upper())
        if room_id:
            return self.rooms.get(room_id)
        return None

    def join_room(self, room_id: str, player_name: str) -> tuple[GameRoom, LobbyPlayer] | None:
        room = self.rooms.get(room_id)
        if not room or room.status not in ("waiting", "auction"):
            return None
        human_count = sum(1 for p in room.players if p.is_human)
        if human_count >= room.max_players:
            return None
        player_id = _short_id()
        lp = LobbyPlayer(player_id=player_id, name=player_name)
        room.players.append(lp)
        self._broadcast_room_update(room)
        return room, lp

    def _broadcast_room_update(self, room: GameRoom) -> None:
        self._thread_safe_broadcast(room.room_id, {
            "type": "room_update",
            "room": room.to_dict(),
        })

    # ---- Auction ----

    def start_auction(self, room_id: str) -> bool:
        room = self.rooms.get(room_id)
        if not room or room.status != "waiting":
            return False
        if len([p for p in room.players if p.is_human]) < 1:
            return False

        room.status = "auction"
        room.auction = AuctionState(
            bids={role: [] for role in ALL_ROLES},
            budget_spent={p.player_id: 0.0 for p in room.players if p.is_human},
            timer_end=time.time() + AUCTION_DURATION_SECONDS,
        )

        num_humans = len([p for p in room.players if p.is_human])
        budget = TOTAL_STARTING_DOLLOPS / num_humans

        self._thread_safe_broadcast(room_id, {
            "type": "auction_start",
            "roles": [
                {**ROLE_INFO[r], "name": r} for r in ALL_ROLES
            ],
            "timer_seconds": AUCTION_DURATION_SECONDS,
            "budget": round(budget, 1),
        })

        if self._loop:
            asyncio.run_coroutine_threadsafe(
                self._auction_timer(room_id, AUCTION_DURATION_SECONDS),
                self._loop,
            )
        return True

    async def _auction_timer(self, room_id: str, seconds: int) -> None:
        await asyncio.sleep(seconds)
        room = self.rooms.get(room_id)
        if room and room.status == "auction":
            self._resolve_auction(room_id)

    def place_bid(self, room_id: str, player_id: str,
                  role_name: str, amount: float) -> dict:
        room = self.rooms.get(room_id)
        if not room or room.status != "auction" or not room.auction:
            return {"error": "No active auction"}
        if role_name not in ALL_ROLES:
            return {"error": "Invalid role"}

        lp = next((p for p in room.players if p.player_id == player_id and p.is_human), None)
        if not lp:
            return {"error": "Player not found"}

        num_humans = len([p for p in room.players if p.is_human])
        budget = TOTAL_STARTING_DOLLOPS / num_humans
        amount = round(max(0.0, amount), 1)

        # Remove any existing bid by this player on this role
        existing = [b for b in room.auction.bids[role_name] if b.player_id == player_id]
        for old in existing:
            room.auction.budget_spent[player_id] -= old.amount
            room.auction.bids[role_name].remove(old)

        spent = room.auction.budget_spent.get(player_id, 0.0)
        if amount > budget - spent:
            amount = round(budget - spent, 1)
        if amount < 0:
            return {"error": "Insufficient budget"}

        room.auction.bids[role_name].append(RoleBid(
            player_id=player_id, player_name=lp.name,
            amount=amount, timestamp=time.time(),
        ))
        room.auction.budget_spent[player_id] = spent + amount

        self._thread_safe_broadcast(room_id, {
            "type": "auction_update",
            "auction": room.auction.to_dict(),
        })
        return {"ok": True, "amount": amount}

    def withdraw_bid(self, room_id: str, player_id: str, role_name: str) -> dict:
        room = self.rooms.get(room_id)
        if not room or room.status != "auction" or not room.auction:
            return {"error": "No active auction"}

        bids = room.auction.bids.get(role_name, [])
        removed = [b for b in bids if b.player_id == player_id]
        for b in removed:
            room.auction.budget_spent[player_id] -= b.amount
            bids.remove(b)

        self._thread_safe_broadcast(room_id, {
            "type": "auction_update",
            "auction": room.auction.to_dict(),
        })
        return {"ok": True}

    def _resolve_auction(self, room_id: str) -> None:
        room = self.rooms.get(room_id)
        if not room or not room.auction:
            return

        auction = room.auction
        auction.phase = "complete"
        winners: dict[str, str] = {}  # role -> player_id
        player_won: dict[str, str] = {}  # player_id -> role (one role per player)
        deductions: dict[str, float] = {}

        # Resolve each role: highest bid wins, ties broken by timestamp
        for role in ALL_ROLES:
            bids = sorted(
                auction.bids.get(role, []),
                key=lambda b: (-b.amount, b.timestamp),
            )
            for bid in bids:
                if bid.player_id not in player_won:
                    winners[role] = bid.player_id
                    player_won[bid.player_id] = role
                    deductions[bid.player_id] = deductions.get(bid.player_id, 0) + bid.amount
                    break

        # Check require_all_human
        if room.require_all_human:
            unclaimed = [r for r in ALL_ROLES if r not in winners]
            if unclaimed:
                self._thread_safe_broadcast(room_id, {
                    "type": "auction_failed",
                    "message": f"All roles must be claimed. Unclaimed: {', '.join(unclaimed)}",
                    "unclaimed": unclaimed,
                })
                auction.phase = "bidding"
                auction.timer_end = time.time() + AUCTION_DURATION_SECONDS
                if self._loop:
                    asyncio.run_coroutine_threadsafe(
                        self._auction_timer(room_id, AUCTION_DURATION_SECONDS),
                        self._loop,
                    )
                return

        auction.assignments = {role: pid for role, pid in winners.items()}

        # Assign roles to lobby players
        for role, pid in winners.items():
            lp = next((p for p in room.players if p.player_id == pid), None)
            if lp:
                lp.role_name = role

        # Fill unclaimed roles with AI
        ai_roles = []
        for role in ALL_ROLES:
            if role not in winners:
                ai_id = _short_id()
                ai_name = f"{role} Island (AI)"
                ai_lp = LobbyPlayer(
                    player_id=ai_id, name=ai_name,
                    role_name=role, is_human=False,
                )
                room.players.append(ai_lp)
                ai_roles.append(role)

        # Broadcast result
        result_assignments = {}
        for role in ALL_ROLES:
            lp = next((p for p in room.players if p.role_name == role), None)
            if lp:
                result_assignments[role] = {
                    "player_name": lp.name,
                    "player_id": lp.player_id,
                    "is_human": lp.is_human,
                }

        self._thread_safe_broadcast(room_id, {
            "type": "auction_result",
            "assignments": result_assignments,
            "ai_roles": ai_roles,
            "deductions": {pid: round(amt, 1) for pid, amt in deductions.items()},
        })

        # Start the game after a short delay
        if self._loop:
            asyncio.run_coroutine_threadsafe(
                self._delayed_game_start(room_id, deductions, delay=5),
                self._loop,
            )

    async def _delayed_game_start(self, room_id: str,
                                   deductions: dict[str, float],
                                   delay: int = 5) -> None:
        await asyncio.sleep(delay)
        self._launch_game(room_id, deductions)

    # ---- Game launch ----

    def _launch_game(self, room_id: str,
                     deductions: dict[str, float] | None = None) -> bool:
        room = self.rooms.get(room_id)
        if not room:
            return False

        num_humans = len([p for p in room.players if p.is_human])
        base_dollops = TOTAL_STARTING_DOLLOPS / num_humans if num_humans else 100.0

        specs = []
        for lp in room.players:
            role = lp.role_name
            if not role:
                continue
            player_dollops = base_dollops
            if lp.is_human and deductions:
                player_dollops -= deductions.get(lp.player_id, 0)
            elif not lp.is_human:
                player_dollops = base_dollops  # AI gets average budget
            specs.append(PlayerSpec(
                name=lp.name, role_names=[role], is_human=lp.is_human,
                starting_dollops=round(player_dollops, 1),
            ))

        config = GameConfig(player_specs=specs, num_years=room.num_years)

        player_send_fns: dict[int, object] = {}
        lobby_order = [lp for lp in room.players if lp.role_name]
        for idx, lp in enumerate(lobby_order):
            def make_send(lp_id=lp.player_id):
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

    def start_game_quick(self, room_id: str) -> bool:
        """Legacy quick-start: auto-assign roles, no auction."""
        room = self.rooms.get(room_id)
        if not room or room.status != "waiting":
            return False
        if len(room.players) < 2:
            return False

        used: set[str] = set()
        for lp in room.players:
            if not lp.role_name or lp.role_name in used:
                for r in ALL_ROLES:
                    if r not in used:
                        lp.role_name = r
                        break
            used.add(lp.role_name)

        # Fill remaining roles with AI
        for role in ALL_ROLES:
            if role not in used:
                ai_id = _short_id()
                room.players.append(LobbyPlayer(
                    player_id=ai_id, name=f"{role} Island (AI)",
                    role_name=role, is_human=False,
                ))

        return self._launch_game(room_id)

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
            lobby_player = next(
                (lp for lp in room.players if lp.player_id == player_id),
                None
            )
            if lobby_player and not lobby_player.is_human:
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
                for s in game.market.price_history[-8:]
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
        return HTMLResponse("<h1>Island Traders Server</h1>")

    @app.post("/api/rooms")
    async def create_room(body: dict = {}):
        room = manager.create_room(
            name=body.get("name", "Game Room"),
            max_players=body.get("max_players", 7),
            num_years=body.get("num_years", 3),
            creator_name=body.get("creator_name", "Host"),
            is_public=body.get("is_public", True),
            require_all_human=body.get("require_all_human", False),
        )
        return JSONResponse(room.to_dict())

    @app.get("/api/rooms")
    async def list_rooms():
        public = [
            r.to_dict() for r in manager.rooms.values()
            if r.is_public and r.status == "waiting"
        ]
        return JSONResponse(public)

    @app.get("/api/rooms/{room_id}")
    async def get_room(room_id: str):
        room = manager.rooms.get(room_id)
        if not room:
            return JSONResponse({"error": "Room not found"}, status_code=404)
        return JSONResponse(room.to_dict())

    @app.post("/api/rooms/join-by-code")
    async def join_by_code(body: dict = {}):
        code = body.get("code", "").strip().upper()
        name = body.get("name", "Player")
        room = manager.find_room_by_code(code)
        if not room:
            return JSONResponse({"error": "Invalid room code"}, status_code=404)
        result = manager.join_room(room.room_id, name)
        if not result:
            return JSONResponse({"error": "Cannot join room"}, status_code=400)
        room, lp = result
        return JSONResponse({"room": room.to_dict(), "player_id": lp.player_id})

    @app.post("/api/rooms/{room_id}/join")
    async def join_room(room_id: str, body: dict = {}):
        result = manager.join_room(room_id, body.get("name", "Player"))
        if not result:
            return JSONResponse({"error": "Cannot join room"}, status_code=400)
        room, lp = result
        return JSONResponse({"room": room.to_dict(), "player_id": lp.player_id})

    @app.post("/api/rooms/{room_id}/auction/start")
    async def start_auction(room_id: str):
        ok = manager.start_auction(room_id)
        if not ok:
            return JSONResponse({"error": "Cannot start auction"}, status_code=400)
        return JSONResponse({"status": "auction"})

    @app.post("/api/rooms/{room_id}/auction/bid")
    async def place_bid(room_id: str, body: dict = {}):
        result = manager.place_bid(
            room_id,
            body.get("player_id", ""),
            body.get("role_name", ""),
            float(body.get("amount", 0)),
        )
        if "error" in result:
            return JSONResponse(result, status_code=400)
        return JSONResponse(result)

    @app.post("/api/rooms/{room_id}/start")
    async def start_game_quick(room_id: str):
        ok = manager.start_game_quick(room_id)
        if not ok:
            return JSONResponse({"error": "Cannot start game"}, status_code=400)
        return JSONResponse({"status": "running"})

    @app.get("/api/rooms/{room_id}/state")
    async def get_state(room_id: str, player_id: str = ""):
        state = manager.get_game_state(room_id, player_id)
        if not state:
            return JSONResponse({"error": "No game state"}, status_code=404)
        return JSONResponse(state)

    @app.get("/api/roles")
    async def list_roles():
        return JSONResponse([{**ROLE_INFO[r], "name": r} for r in ALL_ROLES])

    # ---- WebSocket ----

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
            # Send current state
            if room.status == "auction" and room.auction:
                await websocket.send_text(json.dumps({
                    "type": "auction_update",
                    "auction": room.auction.to_dict(),
                }))
            elif room.status == "running":
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
                elif msg_type == "bid":
                    result = manager.place_bid(
                        room_id, player_id,
                        msg.get("role_name", ""),
                        float(msg.get("amount", 0)),
                    )
                    await websocket.send_text(json.dumps({"type": "bid_ack", **result}))
                elif msg_type == "withdraw_bid":
                    result = manager.withdraw_bid(room_id, player_id, msg.get("role_name", ""))
                    await websocket.send_text(json.dumps({"type": "bid_ack", **result}))
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
