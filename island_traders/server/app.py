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
import math
import random
import re
import string
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..engine.game import Game, GameConfig, PlayerSpec, GameSummary
from ..engine.revenue import revenue_opportunities
from ..engine.trading import InvalidDealError, StaleResourceError
from ..models.profession import Profession, PROFESSION_LABEL
from ..models.resource import ResourceType, NON_TRADABLE_RESOURCES
from ..models.role import ROLES
from ..models.training import (
    TrainingCapacityError,
    TrainingStatus,
    campus_has_technical_workshop,
    settling_seasons_on_return,
)
from ..models.deal import ACTIVE_DEAL_STATUSES, DealProposal
from ..models.capital_negotiation import (
    ACTIVE_CAPITAL_NEGOTIATION_STATUSES,
    CapitalNegotiationLedger,
    CapitalNegotiationStatus,
    CapitalOrderNegotiation,
)
from ..models.equity import (
    ISLAND_STARTING_CASH, share_price, fair_value, liquidation_value,
    AUCTIONED_SHARES, UNISSUED_HOLDER,
)
from ..models import shareholder_loans as sh_loans
from ..models.loan import CapitalFinanceError, LoanStatus, posted_funding_rates
from ..models.capacity import find_item
from ..constants import (
    APP_VERSION,
    SEASONS, CURRENCY_SYMBOL, KITCHEN_SPECS,
    TOTAL_STARTING_POPULATION, PEOPLE_PER_MEAL,
    STAFFING_FOOD_PER_STAFF_PER_SEASON,
    FLU_SEASON,
    MANUFACTURER_FINANCE_REFERRAL_RATE,
)
from ..constants_capacity import CAPITAL_CATALOGUE
from .ws_adapter import WebSocketIOAdapter

try:
    from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
    from pydantic import BaseModel, Field
except ImportError:
    FastAPI = WebSocket = WebSocketDisconnect = None
    StaticFiles = HTMLResponse = JSONResponse = None
    BaseModel = Field = None

logger = logging.getLogger("island_traders.server")

ALL_ROLES = ["Farmer", "Miner", "Transporter", "Educator",
             "Banker", "Manufacturer", "Doctor"]

ROLE_INFO = {
    "Farmer":       {"display_name": ROLES["Farmer"].display_name, "short_name": ROLES["Farmer"].short_name,
                     "island": ROLES["Farmer"].island, "produces": "Grain, Produce, Fish, Meat, Food",
                     "needs": "Farm Machinery, Oil", "color": "#27ae60"},
    "Miner":        {"display_name": ROLES["Miner"].display_name, "short_name": ROLES["Miner"].short_name,
                     "island": ROLES["Miner"].island, "produces": "Ore, Metal, Oil",
                     "needs": "Mining Equipment, Freight", "color": "#e67e22"},
    "Transporter":  {"display_name": ROLES["Transporter"].display_name, "short_name": ROLES["Transporter"].short_name,
                     "island": ROLES["Transporter"].island, "produces": "Freight, PassengerSeats",
                     "needs": "Transport Equipment, Oil", "color": "#3498db"},
    "Educator":     {"display_name": ROLES["Educator"].display_name, "short_name": ROLES["Educator"].short_name,
                     "island": ROLES["Educator"].island, "produces": "Expertise, Patents",
                     "needs": "Laboratory Equipment", "color": "#9b59b6"},
    "Banker":       {"display_name": ROLES["Banker"].display_name, "short_name": ROLES["Banker"].short_name,
                     "island": ROLES["Banker"].island, "produces": "Loans, Insurance",
                     "needs": "Expertise", "color": "#f1c40f"},
    "Manufacturer": {"display_name": ROLES["Manufacturer"].display_name, "short_name": ROLES["Manufacturer"].short_name,
                     "island": ROLES["Manufacturer"].island, "produces": "Machinery, Lab Equipment",
                     "needs": "Metal, Oil, Freight", "color": "#1abc9c"},
    "Doctor":       {"display_name": ROLES["Doctor"].display_name, "short_name": ROLES["Doctor"].short_name,
                     "island": ROLES["Doctor"].island, "produces": "Health Services, Vaccine",
                     "needs": "Expertise, Laboratory Equipment", "color": "#e74c3c"},
}


if BaseModel is not None:
    class CreateRoomRequest(BaseModel):
        name: str = Field("Game Room", description="Lobby display name.")
        creator_name: str = Field("Host", description="Name for the host lobby player.")
        max_players: int = Field(7, ge=2, le=7, description="Maximum lobby seats.")
        num_years: int = Field(3, ge=1, description="Number of game years to play.")
        is_public: bool = Field(True, description="Whether the room appears in public room listings.")
        require_all_human: bool = Field(
            False,
            description="If true, auction cannot resolve with AI-held roles.",
        )
        starting_capital: float = Field(
            1500.0,
            ge=0,
            description="Starting investor cash budget per player, in Dollops.",
        )
        auction_timer_seconds: int = Field(
            60,
            ge=0,
            description="Auction timer length in seconds.",
        )
        season_timer_seconds: int = Field(
            120,
            ge=0,
            description="Action-phase timer length in seconds.",
        )
        pre_season_timer_seconds: int = Field(
            30,
            ge=0,
            description="Pre-season ready timer length in seconds.",
        )
        debug_starting_inventory: dict[str, dict[str, int]] | None = Field(
            None,
            description=(
                "TEST/DEBUG ONLY. Role name -> {resource: qty} overrides added "
                "to a player's opening inventory at game launch (e.g. "
                "{'Farmer': {'Food': 200}} so food production doesn't cloud a "
                "test). Resource names are matched case-insensitively. Presence "
                "marks the room as a debug room; omit in real games."
            ),
        )


    class JoinByCodeRequest(BaseModel):
        code: str = Field(..., description="Six-character room join code.")
        name: str = Field("Player", description="Player name to join or rejoin with.")


    class JoinRoomRequest(BaseModel):
        name: str = Field("Player", description="Player name to join with.")


    class AddAIRequest(BaseModel):
        name: str = Field("AI Player", description="Display name for the built-in server AI.")


    class AuctionBidRequest(BaseModel):
        player_id: str = Field(..., description="Lobby player id placing the bid.")
        role_name: str = Field(..., description="Role/island being bid on, e.g. Farmer.")
        amount: float = Field(..., ge=0, description="Bid amount in Dollops.")


    class LeaveRoomRequest(BaseModel):
        player_id: str = Field(..., description="Lobby player id leaving the room.")
else:
    CreateRoomRequest = JoinByCodeRequest = JoinRoomRequest = AddAIRequest = AuctionBidRequest = dict
    LeaveRoomRequest = dict

AUCTION_DURATION_SECONDS    = 60   # fallback if room has no override
INVESTING_DURATION_SECONDS  = 180  # 3 minutes for Investing Phase
ISLAND_GUARANTEE_DURATION   = 90   # seconds per islandless human to choose
DEFAULT_STARTING_CAPITAL    = 1500.0  # Dp per player (economy-lifecycle Phase A; was 700)
DEFAULT_SEASON_TIMER        = 120     # seconds per season (0 = no timer)
DEFAULT_PRE_SEASON_TIMER    = 30      # seconds for pre-season review window (0 = skip)


# ---------------------------------------------------------------------------
# Post-auction human island guarantee pricing
# (requirements/production-capacity-model.md §19.1)
# ---------------------------------------------------------------------------

def compute_guarantee_price(
    ai_price_paid: float,
    starting_wealth: float,
    buyer_current_wealth: float,
) -> dict:
    """Calculate the price an islandless human pays to take an AI's extra island.

    Inputs:
      ai_price_paid       — what the AI paid for this specific role in the auction.
      starting_wealth     — the auction-budget reference value (e.g. 700 Dp).
      buyer_current_wealth — the human buyer's remaining cash (drives the floor).

    Returns a dict with the final price plus the breakdown components used by
    the UI to explain the calculation:
        {
          "ai_paid":      <float>,
          "ratio_of_start": <float, 0..>,   # ai_paid / starting_wealth
          "formula_band": "<low|mid|high>", # which clause fired
          "formula":      <float>,           # auction-price formula value
          "floor":        <float>,           # 20% of buyer current wealth
          "final":        <float>,           # max(formula, floor)
        }
    """
    starting_wealth = max(0.0, float(starting_wealth))
    buyer_current_wealth = max(0.0, float(buyer_current_wealth))
    ai_price_paid = max(0.0, float(ai_price_paid))

    if starting_wealth > 0:
        ratio = ai_price_paid / starting_wealth
    else:
        ratio = 0.0

    # Inclusive at both ends [11%, 15%] — confirmed in spec open question.
    if 0.11 <= ratio <= 0.15:
        formula_value = 2.0 * ai_price_paid
        band = "mid"
    elif ratio > 0.15:
        formula_value = 1.05 * ai_price_paid
        band = "high"
    else:
        formula_value = ai_price_paid
        band = "low"

    floor = 0.20 * buyer_current_wealth
    final = max(formula_value, floor)

    return {
        "ai_paid": round(ai_price_paid, 2),
        "ratio_of_start": round(ratio, 4),
        "formula_band": band,
        "formula": round(formula_value, 2),
        "floor": round(floor, 2),
        "final": round(final, 2),
    }


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
    # Saved auction_result payload — populated when _resolve_auction
    # broadcasts the result.  Used by the WebSocket reconnect handler to
    # replay the result panel to a client who joins during the brief
    # window between resolution and the room.status transition (bug fix:
    # "auction stuck at timer 0 with no Continue button").
    result_payload: dict | None = field(default=None, repr=False)

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
class IslandGuaranteeState:
    """Per-room state for the post-auction human island guarantee phase
    (requirements/production-capacity-model.md §19.1).

    `pending_buyers`: queue of islandless human lobby_player_ids waiting to choose
                     (sequential — earlier joiners pick first).
    `current_buyer`: who is currently choosing (None when none).
    `offers_for_current`: list of {role, seller_pid, seller_name, ai_paid,
                                   price_breakdown, affordable} for the active buyer.
    `auction_deductions`: carried over so we can finalize cash movements after
                          the guarantee phase resolves (matches existing
                          investing-phase pattern).
    """
    pending_buyers: list[str] = field(default_factory=list)
    current_buyer: str | None = None
    offers_for_current: list[dict] = field(default_factory=list)
    timer_end: float = 0.0
    auction_deductions: dict[str, float] = field(default_factory=dict)
    _timer_task: Any = field(default=None, repr=False)
    # Optional record of completed transfers, for the audit/event log.
    completed: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "current_buyer": self.current_buyer,
            "pending_buyers": list(self.pending_buyers),
            "offers": list(self.offers_for_current),
            "timer_remaining": max(0.0, round(self.timer_end - time.time(), 1)),
            "completed": list(self.completed),
        }


@dataclass
class InvestingState:
    """Per-room state for the Investing Phase between auction and game start.

    `selections`: human player_id -> list of CapitalItem.item_id chosen.
    `submitted`:  set of player_ids who have clicked "Ready".
    AI players auto-submit the mandatory minimum and never appear in `submitted`
    until auto-resolved.
    """
    timer_end: float = 0.0
    selections: dict[str, list[str]] = field(default_factory=dict)
    submitted: set[str] = field(default_factory=set)
    deductions: dict[str, float] = field(default_factory=dict)   # carried over from auction
    _timer_task: Any = field(default=None, repr=False)

    def to_dict(self) -> dict:
        return {
            "timer_remaining": max(0.0, round(self.timer_end - time.time(), 1)),
            "selections": {pid: list(ids) for pid, ids in self.selections.items()},
            "submitted": list(self.submitted),
        }


@dataclass
class LobbyPlayer:
    player_id: str
    name: str
    role_names: list[str] = field(default_factory=list)
    is_human: bool = True
    connected: bool = False

    @property
    def role_name(self) -> str | None:
        """Backwards-compat single-role accessor (returns first won role)."""
        return self.role_names[0] if self.role_names else None

    @role_name.setter
    def role_name(self, value: str | None) -> None:
        self.role_names = [value] if value else []


# ── Chat ──────────────────────────────────────────────────────────────────────
CHAT_HISTORY_MAX = 50          # messages retained per channel
CHAT_TEXT_MAX = 500            # max characters per message
ROOM_CHANNEL_ID = "room"       # the always-present room-wide channel


@dataclass
class ChatChannel:
    """A chat conversation. The room channel (`is_room=True`) reaches every
    human seat; private channels reach only their `participants` (lobby ids)."""
    channel_id: str
    topic: str
    is_room: bool = False
    participants: set[str] = field(default_factory=set)
    history: "deque[dict]" = field(
        default_factory=lambda: deque(maxlen=CHAT_HISTORY_MAX), repr=False
    )

    def summary(self) -> dict:
        return {
            "channel_id": self.channel_id,
            "topic": self.topic,
            "is_room": self.is_room,
            "participants": sorted(self.participants),
            "messages": list(self.history),
        }


@dataclass
class GameRoom:
    room_id: str
    name: str
    max_players: int = 7
    num_years: int = 3
    is_public: bool = True
    join_code: str = ""
    require_all_human: bool = False
    # Economy & timing parameters (configurable at room creation)
    starting_capital: float = DEFAULT_STARTING_CAPITAL  # Dp per player
    auction_timer_seconds: int = AUCTION_DURATION_SECONDS
    season_timer_seconds: int = DEFAULT_SEASON_TIMER     # 0 = no timer
    pre_season_timer_seconds: int = DEFAULT_PRE_SEASON_TIMER  # 0 = skip
    # TEST/DEBUG ONLY: role -> {resource: qty} opening-inventory overrides,
    # applied at game launch. Non-empty marks this as a debug room.
    debug_starting_inventory: dict[str, dict[str, int]] = field(default_factory=dict)
    status: str = "waiting"  # waiting | auction | guarantee | investing | running | finished
    players: list[LobbyPlayer] = field(default_factory=list)
    creator_id: str = ""
    auction: AuctionState | None = None
    investing: InvestingState | None = None
    # Post-auction human island guarantee (Issue: post-auction safety valve)
    guarantee: IslandGuaranteeState | None = None
    # AI auction prices per role (captured at resolution) — used to compute
    # the AI-island sale price during the guarantee phase.
    ai_role_prices: dict[str, float] = field(default_factory=dict)
    game: Game | None = None
    game_thread: threading.Thread | None = None
    io_adapter: WebSocketIOAdapter | None = None
    summary: GameSummary | None = None
    # Lobby player_id (string) → engine Player.player_id (int spec idx).
    # Set when the game launches; used to route WS responses + ready signals.
    lobby_to_engine_id: dict[str, int] = field(default_factory=dict)
    # Per-season ready/active state (simultaneous-play architecture)
    season_ready_set: set[str] = field(default_factory=set)
    season_active_humans: set[str] = field(default_factory=set)
    season_timer_task: Any = field(default=None, repr=False)
    season_timer_end: float = 0.0
    # Grace-period task that fires interrupt_all() a few seconds after all
    # humans mark Done Trading — gives the park loop time to engage so the
    # "Resume Trading" banner appears before the season ends.
    all_ready_task: Any = field(default=None, repr=False)
    # Sentinel to stop multiple Ready clicks queueing END_TURN responses
    # after a player's turn loop has already exited.
    season_human_done: set[str] = field(default_factory=set)
    # Pre-season window state.  "pre_season" while the review window is open;
    # "action" once the action phase begins.  Cleared to "action" on game start.
    season_phase: str = "action"
    current_year_index: int = 0
    current_season_index: int = 0
    # Event set by submit_ready() (or timer) to unblock the game thread that
    # is sleeping through the pre-season window.
    _pre_season_done: threading.Event = field(
        default_factory=threading.Event, repr=False
    )
    pre_season_end: float = 0.0  # epoch time the pre-season window closes

    # ── Pause/Resume (Issue #1) ───────────────────────────────────────────────
    # When `paused` is True, all timers are frozen and the game thread sleeping
    # through pre-season is held until resume.  Only the room creator (host)
    # may toggle pause.  Ready submissions are still accepted but do not
    # advance the game state until resume.
    paused: bool = False
    paused_at: float = 0.0  # epoch time the current pause began

    # Ring buffer of agent interaction events POSTed by external agent processes.
    # Capped at _AGENT_INTERACTIONS_MAX to avoid unbounded growth.
    agent_interactions: list[dict] = field(default_factory=list)

    # Chat channels (room-wide + private group "conspiracy" chats). Keyed by id.
    chat_channels: dict[str, ChatChannel] = field(default_factory=dict)

    def room_channel(self) -> ChatChannel:
        """Return (creating if needed) the always-present room-wide channel."""
        ch = self.chat_channels.get(ROOM_CHANNEL_ID)
        if ch is None:
            ch = ChatChannel(channel_id=ROOM_CHANNEL_ID, topic="Room", is_room=True)
            self.chat_channels[ROOM_CHANNEL_ID] = ch
        return ch

    def to_dict(self) -> dict:
        d = {
            "room_id": self.room_id,
            "name": self.name,
            "creator_id": self.creator_id,
            "max_players": self.max_players,
            "num_years": self.num_years,
            "is_public": self.is_public,
            "join_code": self.join_code,
            "require_all_human": self.require_all_human,
            "starting_capital": self.starting_capital,
            "auction_timer_seconds": self.auction_timer_seconds,
            "season_timer_seconds": self.season_timer_seconds,
            "pre_season_timer_seconds": self.pre_season_timer_seconds,
            # TEST/DEBUG override (empty in normal games); surfaced so a
            # playtester can confirm a debug room seeded the right inventory.
            "debug_starting_inventory": self.debug_starting_inventory,
            "status": self.status,
            "paused": self.paused,
            "player_count": len([p for p in self.players if p.is_human]),
            "players": [
                {"player_id": p.player_id, "name": p.name,
                 "role_name": p.role_name,           # backwards-compat (first role)
                 "role_names": list(p.role_names),
                 "is_human": p.is_human,
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
        # Protects _ws_connections against concurrent register / unregister /
        # send / broadcast — these run on the asyncio loop thread (endpoint
        # handlers) and on the game thread (via _thread_safe_send) so a
        # plain dict isn't enough.  Without this, a quick reconnect could
        # interleave the new connection's register with the old connection's
        # finally-unregister and drop the live socket from the table — the
        # bug #2 symptom of "action menu stops displaying for some players".
        self._ws_lock: threading.Lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    # ---- Room management ----

    def create_room(self, name: str, max_players: int = 7,
                    num_years: int = 3, creator_name: str = "Host",
                    is_public: bool = True,
                    require_all_human: bool = False,
                    starting_capital: float = DEFAULT_STARTING_CAPITAL,
                    auction_timer_seconds: int = AUCTION_DURATION_SECONDS,
                    season_timer_seconds: int = DEFAULT_SEASON_TIMER,
                    pre_season_timer_seconds: int = DEFAULT_PRE_SEASON_TIMER,
                    debug_starting_inventory: dict[str, dict[str, int]] | None = None,
                    room_id: str | None = None) -> GameRoom:
        # Playtest quick-seat: a caller may pin a deterministic room ID so all
        # seven tabs can be pre-composed before the room exists.  Only honoured
        # for the ``pt-`` prefix (keeps the override scoped to playtest rooms),
        # and idempotent — re-creating an existing pinned room returns it.
        if room_id and room_id.startswith("pt-"):
            existing = self.rooms.get(room_id)
            if existing is not None:
                return existing
        else:
            room_id = _short_id()
        creator_id = _short_id()
        code = _join_code()
        room = GameRoom(
            room_id=room_id, name=name,
            max_players=max_players, num_years=num_years,
            is_public=is_public, join_code=code,
            require_all_human=require_all_human,
            starting_capital=float(starting_capital),
            auction_timer_seconds=int(auction_timer_seconds),
            season_timer_seconds=int(season_timer_seconds),
            pre_season_timer_seconds=int(pre_season_timer_seconds),
            debug_starting_inventory=dict(debug_starting_inventory or {}),
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
        if not room or room.status != "waiting":
            return None
        rejoin = self.rejoin_room_by_name(room_id, player_name)
        if rejoin:
            return rejoin
        human_count = sum(1 for p in room.players if p.is_human)
        if human_count >= room.max_players:
            return None
        player_id = _short_id()
        lp = LobbyPlayer(player_id=player_id, name=player_name)
        room.players.append(lp)
        self._broadcast_room_update(room)
        return room, lp

    def rejoin_room_by_name(self, room_id: str, player_name: str) -> tuple[GameRoom, LobbyPlayer] | None:
        room = self.rooms.get(room_id)
        if not room:
            return None
        normalized = player_name.strip().casefold()
        if not normalized:
            return None
        lp = next(
            (p for p in room.players if p.is_human and p.name.strip().casefold() == normalized),
            None,
        )
        if not lp:
            return None
        return room, lp

    def add_ai_player(self, room_id: str, name: str) -> LobbyPlayer | None:
        room = self.rooms.get(room_id)
        if not room or room.status != "waiting":
            return None
        if len(room.players) >= 7:  # hard cap at 7 (one per role)
            return None
        player_id = _short_id()
        lp = LobbyPlayer(player_id=player_id, name=name, is_human=False)
        room.players.append(lp)
        self._broadcast_room_update(room)
        return lp

    def _broadcast_room_update(self, room: GameRoom) -> None:
        self._thread_safe_broadcast(room.room_id, {
            "type": "room_update",
            "room": room.to_dict(),
        })

    def _delete_room(self, room: GameRoom) -> None:
        """Remove a room and its indexes (used when the last human leaves)."""
        self.rooms.pop(room.room_id, None)
        if room.join_code:
            self._code_index.pop(room.join_code, None)
        with self._ws_lock:
            self._ws_connections.pop(room.room_id, None)

    def leave_room(self, room_id: str, player_id: str) -> dict:
        """Deregister a lobby player from a waiting room.

        Only allowed before the game starts (status == "waiting"). If the host
        leaves, host duties pass to the next human. If no humans remain, the room
        is torn down (an AI-only lobby can never start).
        """
        room = self.rooms.get(room_id)
        if not room:
            return {"error": "Room not found"}
        if room.status != "waiting":
            return {"error": "You can only leave before the game starts."}
        lp = next((p for p in room.players if p.player_id == player_id), None)
        if lp is None:
            return {"error": "You are not registered in this room."}

        room.players.remove(lp)

        if room.creator_id == player_id:
            new_host = next((p for p in room.players if p.is_human), None)
            room.creator_id = new_host.player_id if new_host else ""

        if not any(p.is_human for p in room.players):
            self._delete_room(room)
            return {"left": True, "room_closed": True}

        self._broadcast_room_update(room)
        return {"left": True, "room_closed": False}

    # ---- Auction ----

    def start_auction(self, room_id: str) -> bool:
        room = self.rooms.get(room_id)
        if not room or room.status != "waiting":
            return False
        if len([p for p in room.players if p.is_human]) < 1:
            return False

        room.status = "auction"
        auction_secs = room.auction_timer_seconds
        room.auction = AuctionState(
            bids={role: [] for role in ALL_ROLES},
            # Track budget spent for every player (humans + AIs)
            budget_spent={p.player_id: 0.0 for p in room.players},
            timer_end=time.time() + auction_secs,
        )

        num_players = len(room.players)
        budget = room.starting_capital

        self._thread_safe_broadcast(room_id, {
            "type": "auction_start",
            "roles": [
                {**ROLE_INFO[r], "name": r} for r in ALL_ROLES
            ],
            "timer_seconds": auction_secs,
            "budget": round(budget, 1),
        })

        if self._loop:
            fut = asyncio.run_coroutine_threadsafe(
                self._auction_timer(room_id, auction_secs),
                self._loop,
            )
            room.auction._timer_task = fut
            # Schedule AI bids spread across the auction window
            ai_players = [p for p in room.players if not p.is_human]
            if ai_players:
                asyncio.run_coroutine_threadsafe(
                    self._ai_auction_participation(room_id, auction_secs),
                    self._loop,
                )
        return True

    # ---- AI auction bidding ----
    HIGH_MARGIN_ROLES = ["Banker", "Manufacturer", "Doctor"]

    async def _ai_auction_participation(self, room_id: str, total_seconds: int) -> None:
        """Place AI bids spread across the auction window.

        Each AI bids on:
          (a) one high-margin role (Banker / Manufacturer / Doctor) — biggest stake
          (b) one randomly selected other role — smaller stake
        Bid sizing leaves operating capital after the auction.
        """
        import random as _random
        room = self.rooms.get(room_id)
        if not room or room.status != "auction":
            return
        ai_players = [p for p in room.players if not p.is_human]
        if not ai_players:
            return

        rng = _random.Random()
        budget = room.starting_capital

        # Spread first bids over first half of window, second over the second half.
        for ai in ai_players:
            high = rng.choice(self.HIGH_MARGIN_ROLES)
            others = [r for r in ALL_ROLES if r != high]
            random_pick = rng.choice(others)

            # Bid amounts as fraction of budget (leave ~30% for operations)
            high_amount = round(budget * rng.uniform(0.40, 0.60), 1)
            random_amount = round(budget * rng.uniform(0.10, 0.25), 1)

            # Stagger the bid placement
            delay_high = rng.uniform(2, max(3, total_seconds * 0.4))
            delay_random = rng.uniform(total_seconds * 0.4, max(total_seconds * 0.7, 5))

            asyncio.run_coroutine_threadsafe(
                self._delayed_ai_bid(room_id, ai.player_id, high, high_amount, delay_high),
                self._loop,
            )
            asyncio.run_coroutine_threadsafe(
                self._delayed_ai_bid(room_id, ai.player_id, random_pick, random_amount, delay_random),
                self._loop,
            )

    async def _delayed_ai_bid(
        self, room_id: str, player_id: str, role: str,
        amount: float, delay: float,
    ) -> None:
        await asyncio.sleep(delay)
        room = self.rooms.get(room_id)
        if not room or room.status != "auction":
            return
        result = self.place_bid(room_id, player_id, role, amount)
        # Failures (e.g. bid below current high) are logged silently — the AI
        # has done its best.
        logger.info("AI bid %s on %s for %.1f → %s",
                    player_id, role, amount, result)

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

        # Accept bids from any lobby player (humans + named AIs)
        lp = next((p for p in room.players if p.player_id == player_id), None)
        if not lp:
            return {"error": "Player not found"}

        budget = room.starting_capital
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
        winners: dict[str, str] = {}      # role -> player_id
        deductions: dict[str, float] = {} # player_id -> total Dp owed across all roles won
        per_role_paid: dict[str, float] = {}  # role -> winning bid amount (for guarantee)

        # Resolve each role independently: highest bid wins, ties broken by timestamp.
        # A single player can win MULTIPLE roles if they bid the highest on each.
        for role in ALL_ROLES:
            bids = sorted(
                auction.bids.get(role, []),
                key=lambda b: (-b.amount, b.timestamp),
            )
            if bids:
                top = bids[0]
                winners[role] = top.player_id
                deductions[top.player_id] = deductions.get(top.player_id, 0) + top.amount
                per_role_paid[role] = top.amount

        # Snapshot per-role auction prices on the room so the guarantee phase
        # (and any future post-auction features) can refer back to them.
        room.ai_role_prices = dict(per_role_paid)

        # Check require_all_human.  The room option means every role must be
        # won by a human player, not merely claimed by an AI placeholder.
        if room.require_all_human:
            not_human_claimed = []
            for role in ALL_ROLES:
                pid = winners.get(role)
                lp = next((p for p in room.players if p.player_id == pid), None)
                if not lp or not lp.is_human:
                    not_human_claimed.append(role)
            if not_human_claimed:
                self._thread_safe_broadcast(room_id, {
                    "type": "auction_failed",
                    "message": (
                        "All roles must be claimed by human players. "
                        f"Missing: {', '.join(not_human_claimed)}"
                    ),
                    "unclaimed": not_human_claimed,
                })
                auction.phase = "bidding"
                auction.timer_end = time.time() + room.auction_timer_seconds
                if self._loop:
                    fut = asyncio.run_coroutine_threadsafe(
                        self._auction_timer(room_id, room.auction_timer_seconds),
                        self._loop,
                    )
                    room.auction._timer_task = fut
                return

        auction.assignments = {role: pid for role, pid in winners.items()}

        # Assign roles to lobby players (a single player may have won multiple)
        for role, pid in winners.items():
            lp = next((p for p in room.players if p.player_id == pid), None)
            if lp and role not in lp.role_names:
                lp.role_names.append(role)

        # Any human with no won role gets first claim on leftover roles so they
        # remain playable rather than becoming a silent spectator.
        idle_humans = [p for p in room.players if p.is_human and not p.role_names]
        unclaimed = [r for r in ALL_ROLES if r not in winners]
        for human_lp in idle_humans:
            if not unclaimed:
                break
            role = unclaimed.pop(0)
            human_lp.role_names.append(role)

        # Any AI lobby player who did NOT win a role can absorb the next
        # leftover role (so named AIs stay relevant if their bids lost out).
        idle_ais = [p for p in room.players
                    if not p.is_human and not p.role_names]
        for ai_lp in idle_ais:
            if not unclaimed:
                break
            role = unclaimed.pop(0)
            ai_lp.role_names.append(role)

        # Any roles still unclaimed after that → spawn fresh generic AIs
        ai_roles = []
        for role in unclaimed:
            ai_id = _short_id()
            ai_name = f"{role} Island (AI)"
            ai_lp = LobbyPlayer(
                player_id=ai_id, name=ai_name,
                role_names=[role], is_human=False,
            )
            room.players.append(ai_lp)
            ai_roles.append(role)

        # Broadcast result
        result_assignments = {}
        for role in ALL_ROLES:
            lp = next((p for p in room.players if role in p.role_names), None)
            if lp:
                result_assignments[role] = {
                    "player_name": lp.name,
                    "player_id": lp.player_id,
                    "is_human": lp.is_human,
                }

        result_payload = {
            "type": "auction_result",
            "assignments": result_assignments,
            "ai_roles": ai_roles,
            "deductions": {pid: round(amt, 1) for pid, amt in deductions.items()},
        }
        # Save before broadcast so a reconnect handler can replay it for a
        # client that misses the live broadcast.
        auction.result_payload = result_payload
        self._thread_safe_broadcast(room_id, result_payload)

        # Post-auction human island guarantee (§19.1):
        # If any human player still has no island AND any AI controls 2+
        # islands, give the islandless humans a chance to buy an AI extra.
        # Otherwise proceed straight to Investing.
        if self._should_run_island_guarantee(room):
            if self._loop:
                asyncio.run_coroutine_threadsafe(
                    self._delayed_guarantee_start(room_id, deductions, delay=2),
                    self._loop,
                )
            return

        # Enter the Investing Phase after a short pause so players can see the
        # auction outcome.  When the user clicks "Continue to Game" on the
        # auction-result overlay, the front-end will see status=="investing"
        # and switch to the Investing screen.  The server kicks off the phase
        # immediately.
        if self._loop:
            asyncio.run_coroutine_threadsafe(
                self._delayed_investing_start(room_id, deductions, delay=2),
                self._loop,
            )

    # ---- Post-auction human island guarantee (§19.1) ----

    def _should_run_island_guarantee(self, room: GameRoom) -> bool:
        """Trigger condition: at least one human has zero roles AND at least
        one AI controls 2+ roles (so a swap is possible)."""
        islandless_humans = any(
            p.is_human and not p.role_names for p in room.players
        )
        ai_with_extras = any(
            (not p.is_human) and len(p.role_names) >= 2 for p in room.players
        )
        return islandless_humans and ai_with_extras

    def _islandless_humans_in_join_order(self, room: GameRoom) -> list[str]:
        return [p.player_id for p in room.players
                if p.is_human and not p.role_names]

    def _build_offers_for(self, room: GameRoom, buyer_pid: str) -> list[dict]:
        """All AI-held roles where the AI has 2+ roles are eligible offers.

        Each offer includes the calculated guarantee price plus a breakdown so
        the UI can show how the number was reached.  Affordability is computed
        against the buyer's current cash (starting_capital — any auction
        deductions, which for an islandless human is 0).
        """
        starting_wealth = room.starting_capital
        buyer = next((p for p in room.players if p.player_id == buyer_pid), None)
        buyer_deduction = (
            (room.guarantee.auction_deductions.get(buyer_pid, 0.0)
             if room.guarantee else 0.0)
        )
        buyer_current_wealth = max(0.0, starting_wealth - buyer_deduction)

        offers = []
        for ai_lp in room.players:
            if ai_lp.is_human or len(ai_lp.role_names) < 2:
                continue
            for role in ai_lp.role_names:
                ai_paid = float(room.ai_role_prices.get(role, 0.0))
                breakdown = compute_guarantee_price(
                    ai_price_paid=ai_paid,
                    starting_wealth=starting_wealth,
                    buyer_current_wealth=buyer_current_wealth,
                )
                offers.append({
                    "role": role,
                    "seller_player_id": ai_lp.player_id,
                    "seller_name": ai_lp.name,
                    "ai_paid": breakdown["ai_paid"],
                    "price": breakdown["final"],
                    "breakdown": breakdown,
                    "affordable": breakdown["final"] <= buyer_current_wealth + 1e-6,
                })
        # Stable order: by role name so the UI is predictable.
        offers.sort(key=lambda o: ALL_ROLES.index(o["role"])
                                  if o["role"] in ALL_ROLES else 99)
        return offers

    async def _delayed_guarantee_start(
        self, room_id: str, deductions: dict[str, float], delay: int = 2
    ) -> None:
        await asyncio.sleep(delay)
        self._start_island_guarantee(room_id, deductions)

    def _start_island_guarantee(
        self, room_id: str, deductions: dict[str, float]
    ) -> None:
        """Enter the guarantee phase.  Sequential per buyer."""
        room = self.rooms.get(room_id)
        if not room:
            return
        pending = self._islandless_humans_in_join_order(room)
        if not pending:
            # Nothing to do — fall through to investing.
            self._start_investing(room_id, deductions)
            return

        room.status = "guarantee"
        room.guarantee = IslandGuaranteeState(
            pending_buyers=pending,
            auction_deductions=dict(deductions),
        )
        self._advance_island_guarantee(room_id)

    def _advance_island_guarantee(self, room_id: str) -> None:
        """Move to the next pending buyer, or finalize if queue is empty."""
        room = self.rooms.get(room_id)
        if not room or not room.guarantee:
            return
        gs = room.guarantee

        # Cancel any in-flight per-buyer timer
        if gs._timer_task is not None:
            try: gs._timer_task.cancel()
            except Exception: pass
            gs._timer_task = None

        while gs.pending_buyers:
            buyer_pid = gs.pending_buyers.pop(0)
            offers = self._build_offers_for(room, buyer_pid)
            if not offers:
                # Their would-be offers may have all been bought by an earlier
                # buyer; skip and continue.
                continue
            gs.current_buyer = buyer_pid
            gs.offers_for_current = offers
            gs.timer_end = time.time() + ISLAND_GUARANTEE_DURATION
            self._broadcast_guarantee_state(room)
            if self._loop:
                fut = asyncio.run_coroutine_threadsafe(
                    self._guarantee_timer(room_id, ISLAND_GUARANTEE_DURATION),
                    self._loop,
                )
                gs._timer_task = fut
            return

        # Queue exhausted → finalize and proceed to investing
        self._finalize_island_guarantee(room_id)

    def _broadcast_guarantee_state(self, room: GameRoom) -> None:
        if not room.guarantee:
            return
        self._thread_safe_broadcast(room.room_id, {
            "type": "island_guarantee_state",
            "guarantee": room.guarantee.to_dict(),
        })

    async def _guarantee_timer(self, room_id: str, seconds: int) -> None:
        await asyncio.sleep(seconds)
        room = self.rooms.get(room_id)
        if not room or not room.guarantee:
            return
        # Time expired for the current buyer → they implicitly decline; move on.
        if room.guarantee.current_buyer is not None:
            logger.info("Room %s: island guarantee timer expired for buyer %s",
                        room_id, room.guarantee.current_buyer)
            room.guarantee.completed.append({
                "buyer_player_id": room.guarantee.current_buyer,
                "result": "timeout",
            })
            room.guarantee.current_buyer = None
            room.guarantee.offers_for_current = []
        self._advance_island_guarantee(room_id)

    def submit_guarantee_choice(
        self, room_id: str, lobby_player_id: str,
        accept: bool, role: str | None = None,
    ) -> dict:
        """Buyer accepts (with `role`) or declines the current offer set."""
        room = self.rooms.get(room_id)
        if not room or not room.guarantee:
            return {"error": "Not in guarantee phase"}
        gs = room.guarantee
        if lobby_player_id != gs.current_buyer:
            return {"error": "Not your turn to choose"}

        if not accept:
            gs.completed.append({
                "buyer_player_id": lobby_player_id,
                "result": "declined",
            })
            self._thread_safe_broadcast(room_id, {
                "type": "island_guarantee_resolved",
                "buyer_player_id": lobby_player_id,
                "result": "declined",
            })
            gs.current_buyer = None
            gs.offers_for_current = []
            self._advance_island_guarantee(room_id)
            return {"ok": True, "accepted": False}

        # Accept path — validate the chosen offer.
        chosen = next((o for o in gs.offers_for_current if o["role"] == role), None)
        if not chosen:
            return {"error": f"No offer available for role {role!r}"}
        if not chosen["affordable"]:
            return {"error": f"Price {chosen['price']} exceeds your current wealth"}

        # Execute the transfer.
        seller = next((p for p in room.players
                       if p.player_id == chosen["seller_player_id"]), None)
        buyer = next((p for p in room.players if p.player_id == lobby_player_id), None)
        if not seller or not buyer or role not in seller.role_names:
            return {"error": "Stale offer; role no longer available"}

        # Lobby-side role transfer
        seller.role_names.remove(role)
        buyer.role_names.append(role)

        # Cash movement: buyer pays seller (these are auction-side cash flows
        # tracked via deductions so the Game.setup() applies them correctly).
        gs.auction_deductions[lobby_player_id] = (
            gs.auction_deductions.get(lobby_player_id, 0.0) + chosen["price"]
        )
        # Refund the seller's effective net (they keep the price; reduce their
        # auction-side deduction by the price, or treat as a positive credit).
        gs.auction_deductions[chosen["seller_player_id"]] = (
            gs.auction_deductions.get(chosen["seller_player_id"], 0.0)
            - chosen["price"]
        )

        gs.completed.append({
            "buyer_player_id": lobby_player_id,
            "seller_player_id": chosen["seller_player_id"],
            "role": role,
            "price": chosen["price"],
            "ai_paid": chosen["ai_paid"],
            "breakdown": chosen["breakdown"],
            "result": "accepted",
        })

        self._thread_safe_broadcast(room_id, {
            "type": "island_guarantee_resolved",
            "buyer_player_id": lobby_player_id,
            "seller_player_id": chosen["seller_player_id"],
            "role": role,
            "price": chosen["price"],
            "breakdown": chosen["breakdown"],
            "result": "accepted",
        })
        # Also broadcast the updated room state so other clients see new owners.
        self._broadcast_room_update(room)

        gs.current_buyer = None
        gs.offers_for_current = []
        self._advance_island_guarantee(room_id)
        return {"ok": True, "accepted": True, "role": role, "price": chosen["price"]}

    def _finalize_island_guarantee(self, room_id: str) -> None:
        """All islandless buyers handled — broadcast completion and proceed
        to the Investing Phase using the (possibly modified) deductions."""
        room = self.rooms.get(room_id)
        if not room or not room.guarantee:
            return
        deductions = dict(room.guarantee.auction_deductions)
        completed = list(room.guarantee.completed)
        self._thread_safe_broadcast(room_id, {
            "type": "island_guarantee_complete",
            "completed": completed,
        })
        room.guarantee = None
        self._start_investing(room_id, deductions)

    async def _delayed_investing_start(
        self, room_id: str, deductions: dict[str, float], delay: int = 2
    ) -> None:
        await asyncio.sleep(delay)
        self._start_investing(room_id, deductions)

    async def _delayed_game_start(self, room_id: str,
                                   deductions: dict[str, float],
                                   delay: int = 5) -> None:
        await asyncio.sleep(delay)
        self._launch_game(room_id, deductions)

    # ---- Investing Phase ----

    def _start_investing(
        self, room_id: str, deductions: dict[str, float]
    ) -> None:
        """Enter the Investing Phase: each role chooses a capital portfolio."""
        from ..constants_capacity import MANDATORY_MINIMUM_INVESTMENT
        room = self.rooms.get(room_id)
        if not room:
            return

        room.status = "investing"
        state = InvestingState(
            timer_end=time.time() + INVESTING_DURATION_SECONDS,
            deductions=dict(deductions or {}),
        )

        # Pre-fill mandatory minimum selections for everyone (humans included
        # — they can adjust before submitting).  AI players also auto-submit.
        for lp in room.players:
            if not lp.role_names:
                continue
            mandatory: list[str] = []
            for role in lp.role_names:
                mandatory.extend(MANDATORY_MINIMUM_INVESTMENT.get(role, []))
            state.selections[lp.player_id] = mandatory
            if not lp.is_human:
                state.submitted.add(lp.player_id)
        room.investing = state

        # Per-player payload: their role catalogue + budget + mandatory items.
        for lp in room.players:
            if not lp.is_human or not lp.role_names:
                continue
            payload = self._investing_payload(room, lp)
            if payload:
                self._thread_safe_send(room_id, lp.player_id, payload)

        # Broadcast a compact status to all (so observers see the phase change)
        self._thread_safe_broadcast(room_id, {
            "type": "investing_phase",
            "timer_seconds": INVESTING_DURATION_SECONDS,
        })

        if self._loop:
            fut = asyncio.run_coroutine_threadsafe(
                self._investing_timer(room_id, INVESTING_DURATION_SECONDS),
                self._loop,
            )
            room.investing._timer_task = fut

    def _investing_payload(self, room: GameRoom, lp: LobbyPlayer) -> dict | None:
        """Build the per-player Investing Phase payload, including reconnects."""
        if not room.investing or not lp.is_human or not lp.role_names:
            return None
        from ..constants_capacity import CAPITAL_CATALOGUE, MANDATORY_MINIMUM_INVESTMENT

        spent_in_auction = room.investing.deductions.get(lp.player_id, 0.0)
        budget = round(room.starting_capital - spent_in_auction, 1)
        island_capital = round(ISLAND_STARTING_CASH, 1)
        setup_loan_rate = posted_funding_rates(0, 0)[3]
        from ..models.lease import lease_quote
        catalogue_payload = []
        mandatory_set: set[str] = set()
        for it in CAPITAL_CATALOGUE:
            if it.role in lp.role_names:
                # Pre-compute the lease quote at the investing-phase tick
                # (Y0/S0) so the client can render the buy-vs-lease UI
                # without having to know about posted_funding_rates.
                quote = None
                if it.lease_terms:
                    try:
                        quote = lease_quote(it, 0, 0)
                    except Exception:
                        quote = None
                catalogue_payload.append({
                    "item_id":          it.item_id,
                    "name":             it.name,
                    "role":             it.role,
                    "cost":             it.cost,
                    "island_capital":   island_capital,
                    "secured_loan_quote": {
                        "term_years": 3,
                        "interest_rate": setup_loan_rate,
                        "max_treasury_cover": island_capital,
                        "shortfall_if_selected": round(max(0.0, it.cost - island_capital), 1),
                    },
                    "delivery_seasons": it.delivery_seasons,
                    "description":      it.description,
                    "effects":          it.effects,
                    "lease_terms":      it.lease_terms,
                    "lease_quote":      quote,
                })
        for role in lp.role_names:
            mandatory_set.update(MANDATORY_MINIMUM_INVESTMENT.get(role, []))

        return {
            "type": "investing_start",
            "budget": budget,
            "island_capital": island_capital,
            "roles": list(lp.role_names),
            "catalogue": catalogue_payload,
            "mandatory": sorted(mandatory_set),
            "selections": list(room.investing.selections.get(lp.player_id, [])),
            "timer_seconds": max(0.0, round(room.investing.timer_end - time.time(), 1)),
        }

    async def _investing_timer(self, room_id: str, seconds: int) -> None:
        await asyncio.sleep(seconds)
        room = self.rooms.get(room_id)
        if room and room.status == "investing":
            self._resolve_investing(room_id)

    def submit_investment(
        self, room_id: str, player_id: str,
        item_ids: list[str], ready: bool,
    ) -> dict:
        """Update a player's selection.  When `ready=True` they're locked in;
        the phase advances once every human is ready (or the timer fires)."""
        from ..constants_capacity import CAPITAL_CATALOGUE, MANDATORY_MINIMUM_INVESTMENT
        from ..models.capacity import find_item

        room = self.rooms.get(room_id)
        if not room or room.status != "investing" or not room.investing:
            return {"error": "Not in investing phase"}
        lp = next((p for p in room.players if p.player_id == player_id), None)
        if not lp:
            return {"error": "Player not found"}
        if not lp.is_human:
            return {"error": "AI players cannot manually submit"}
        if not lp.role_names:
            return {"error": "Player has no assigned role"}

        # Validate items belong to one of this player's roles
        valid: list[str] = []
        for iid in item_ids:
            lease_prefix = "lease:"
            item_id = iid[len(lease_prefix):] if isinstance(iid, str) and iid.startswith(lease_prefix) else iid
            item = find_item(CAPITAL_CATALOGUE, item_id)
            if item and item.role in lp.role_names:
                if isinstance(iid, str) and iid.startswith(lease_prefix):
                    if item.lease_terms:
                        valid.append(iid)
                else:
                    valid.append(iid)

        room.investing.selections[player_id] = valid
        if ready:
            room.investing.submitted.add(player_id)
        else:
            room.investing.submitted.discard(player_id)

        self._thread_safe_broadcast(room_id, {
            "type": "investing_update",
            "submitted_count": len(room.investing.submitted),
            "human_count": sum(1 for p in room.players if p.is_human and p.role_names),
        })

        # All humans submitted? Resolve immediately.
        humans = {p.player_id for p in room.players if p.is_human and p.role_names}
        if humans.issubset(room.investing.submitted):
            self._resolve_investing(room_id)
        return {"ok": True, "selections": valid, "ready": ready}

    def _resolve_investing(self, room_id: str) -> None:
        """Apply purchases and advance to the actual game."""
        from ..constants_capacity import CAPITAL_CATALOGUE
        from ..models.capacity import find_item

        room = self.rooms.get(room_id)
        if not room or not room.investing:
            return

        # Tally per-player spend & validated selections; clamp to budget.
        base_dollops = room.starting_capital

        capital_purchases: dict[str, list[str]] = {}   # player_id -> item_ids actually bought
        capital_leases: dict[str, list[str]] = {}      # player_id -> item_ids leased
        capital_spend: dict[str, float] = {}
        purchase_costs: dict[str, dict[str, float]] = {}

        for lp in room.players:
            if not lp.role_names:
                continue
            selected = room.investing.selections.get(lp.player_id, [])
            spent_in_auction = room.investing.deductions.get(lp.player_id, 0.0)
            budget_remaining = base_dollops - spent_in_auction

            bought: list[str] = []
            leased: list[str] = []
            spend = 0.0
            for iid in selected:
                is_lease = isinstance(iid, str) and iid.startswith("lease:")
                item_id = iid[6:] if is_lease else iid
                item = find_item(CAPITAL_CATALOGUE, item_id)
                if not item or item.role not in lp.role_names:
                    continue
                price = item.cost
                if is_lease:
                    if not item.lease_terms:
                        continue
                    from ..models.lease import lease_quote
                    price = lease_quote(item, 0, 0)["annual_payment"]
                if spend + price > budget_remaining + 1e-6:
                    continue   # over budget — skip
                if is_lease:
                    leased.append(item_id)
                else:
                    bought.append(item_id)
                    purchase_costs.setdefault(lp.player_id, {})[item_id] = round(price, 1)
                spend += price
            capital_purchases[lp.player_id] = bought
            capital_leases[lp.player_id] = leased
            capital_spend[lp.player_id] = round(spend, 1)

        # Combined deduction: auction winning bid + investing capital spend.
        # Use investing.deductions (winning bids only) — auction.budget_spent
        # would include losing bids which players don't actually pay.
        auction_deductions = dict(room.investing.deductions)
        total_deductions = dict(capital_spend)
        for pid, amt in auction_deductions.items():
            total_deductions[pid] = total_deductions.get(pid, 0.0) + amt

        room.investing._timer_task = None
        room.investing = None

        self._thread_safe_broadcast(room_id, {
            "type": "investing_resolved",
            "purchases": capital_purchases,
            "leases": capital_leases,
            "spend": capital_spend,
        })
        self._launch_game(
            room_id, bids=auction_deductions,
            capital_purchases=capital_purchases,
            capital_leases=capital_leases,
            capital_spend=capital_spend,
            capital_purchase_costs=purchase_costs,
        )

    # ---- Game launch ----

    def _launch_game(self, room_id: str,
                     bids: dict[str, float] | None = None,
                     capital_purchases: dict[str, list[str]] | None = None,
                     capital_leases: dict[str, list[str]] | None = None,
                     capital_spend: dict[str, float] | None = None,
                     capital_purchase_costs: dict[str, dict[str, float]] | None = None) -> bool:
        room = self.rooms.get(room_id)
        if not room:
            return False

        # --- Equity flip (Phase 2b) -------------------------------------
        # Personal cash (investor wallet) = starting_capital − winning bid
        # (the bid leaves the game, paid to imaginary former owners).
        # Island treasury is seeded independently at ISLAND_STARTING_CASH and
        # funds the opening capital basket; any shortfall becomes a secured
        # three-year setup loan instead of draining the owner's personal cash.
        base_capital = room.starting_capital
        bids = bids or {}
        capital_spend = capital_spend or {}
        capital_purchase_costs = capital_purchase_costs or {}

        specs = []
        spec_to_lobby_pid: dict[int, str] = {}   # PlayerSpec idx -> lobby player_id
        for lp in room.players:
            roles = list(lp.role_names)
            if not roles:
                continue
            # Seed each engine Player's treasury at ISLAND_STARTING_CASH; the
            # personal-cash / loan flip is applied post-setup below.
            specs.append(PlayerSpec(
                name=lp.name, role_names=roles, is_human=lp.is_human,
                starting_dollops=round(ISLAND_STARTING_CASH, 1),
            ))
            spec_to_lobby_pid[len(specs) - 1] = lp.player_id

        config = GameConfig(player_specs=specs, num_years=room.num_years)

        player_send_fns: dict[int, object] = {}
        lobby_order = [lp for lp in room.players if lp.role_names]
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
        # Map lobby (string) → engine spec idx (int) so WS responses route right
        room.lobby_to_engine_id = {
            lobby_pid: spec_idx for spec_idx, lobby_pid in spec_to_lobby_pid.items()
        }

        # --- Apply the equity flip to each engine Player (post-setup) -------
        # treasury = ISLAND_STARTING_CASH − opening capital spend paid from the island
        # personal_cash = starting_capital − winning_bid
        # secured setup loan = any opening capital spend above the island treasury
        setup_loan_rate = posted_funding_rates(0, 0)[3]
        banker = next(
            (p for p in game.players if any(r.name == "Banker" for r in p.roles)),
            None,
        )
        for spec_idx, lobby_pid in spec_to_lobby_pid.items():
            if spec_idx >= len(game.players):
                continue
            p = game.players[spec_idx]
            bid = float(bids.get(lobby_pid, 0.0))
            cspend = float(capital_spend.get(lobby_pid, 0.0))
            remaining_treasury = ISLAND_STARTING_CASH
            p.personal_cash = round(base_capital - bid, 1)
            p.shareholder_loans = {}
            costs = dict(capital_purchase_costs.get(lobby_pid, {}))
            residual_spend = round(cspend - sum(costs.values()), 1)
            if residual_spend > 0:
                costs["opening.aggregate_spend"] = residual_spend
            for item_id, cost in costs.items():
                from_treasury = min(remaining_treasury, float(cost))
                remaining_treasury = round(remaining_treasury - from_treasury, 1)
                shortfall = round(float(cost) - from_treasury, 1)
                if shortfall <= 0:
                    continue
                lender_id = banker.player_id if banker else -1
                game.loan_ledger.create_loan(
                    borrower_id=p.player_id,
                    lender_id=lender_id,
                    principal=shortfall,
                    interest_rate=setup_loan_rate,
                    issued_year=0,
                    issued_season=0,
                    term_years=3,
                    posted_at_issue=setup_loan_rate,
                    collateral_item_id=item_id,
                    secured=True,
                )
                if banker and banker.player_id != p.player_id:
                    game.loan_ledger.create_loan(
                        borrower_id=banker.player_id,
                        lender_id=-1,
                        principal=shortfall,
                        interest_rate=setup_loan_rate,
                        issued_year=0,
                        issued_season=0,
                        term_years=3,
                        posted_at_issue=setup_loan_rate,
                    )
            p.dollops = round(max(0.0, remaining_treasury), 1)

        # Simultaneous-play mode is ALWAYS on for the server: each human
        # plays on their own turn-thread, exit via Ready button or (if
        # configured) the season timer. season_timer_seconds == 0 means
        # "no timer — Ready button is the only season-end trigger".
        game.turn_manager.parallel_mode = True

        def _on_player_done(engine_pid: int) -> None:
            lobby_pid = next(
                (lp for lp, ep in room.lobby_to_engine_id.items() if ep == engine_pid),
                None,
            )
            logger.info(
                "[season-timer] player_turn_complete room=%s engine_pid=%s "
                "lobby_pid=%s epoch=%.3f timer_end=%.3f phase=%s",
                room_id,
                engine_pid,
                lobby_pid,
                time.time(),
                room.season_timer_end,
                room.season_phase,
            )
            if lobby_pid:
                room.season_human_done.add(lobby_pid)
                self._broadcast_ready_update(room)

        game.turn_manager.on_player_turn_complete = _on_player_done
        game.turn_manager.wait_for_parallel_season_release = (
            lambda y, s: self._wait_for_timed_season_release(room_id, y, s)
        )

        # Hook season-start/end so we can install/refresh the timer + ready UI.
        game.before_season = lambda y, s: self._on_season_start(room_id, y, s)
        game.after_season  = lambda y, s: self._on_season_end(room_id, y, s)

        # Apply Investing Phase purchases to engine Players (after setup so the
        # Player objects exist).  Opening investments are setup purchases, so
        # even catalogue items with delivery_seasons > 0 are available
        # immediately. Mid-game purchases can still use capital_in_transit.
        if capital_purchases:
            from ..constants_capacity import CAPITAL_CATALOGUE
            from ..models.capacity import find_item
            for spec_idx, lobby_pid in spec_to_lobby_pid.items():
                bought = capital_purchases.get(lobby_pid, [])
                if not bought or spec_idx >= len(game.players):
                    continue
                p = game.players[spec_idx]
                for iid in bought:
                    item = find_item(CAPITAL_CATALOGUE, iid)
                    if not item:
                        continue
                    p.add_capital(iid, 1)
        if capital_leases:
            from ..constants_capacity import CAPITAL_CATALOGUE
            from ..models.capacity import find_item
            from ..models.lease import lease_quote
            banker = next(
                (p for p in game.players if any(r.name == "Banker" for r in p.roles)),
                None,
            )
            lessor_id = banker.player_id if banker else -1
            for spec_idx, lobby_pid in spec_to_lobby_pid.items():
                leased = capital_leases.get(lobby_pid, [])
                if not leased or spec_idx >= len(game.players):
                    continue
                p = game.players[spec_idx]
                for iid in leased:
                    item = find_item(CAPITAL_CATALOGUE, iid)
                    if not item or not item.lease_terms:
                        continue
                    p.add_capital(iid, 1)
                    quote = lease_quote(item, 0, 0)
                    if banker and banker.player_id != p.player_id:
                        banker.dollops += quote["annual_payment"]
                    game.lease_ledger.create_lease(
                        item_id=iid,
                        lessee_id=p.player_id,
                        lessor_id=lessor_id,
                        year=0,
                        season=0,
                        term_years=quote["term_years"],
                        annual_payment=quote["annual_payment"],
                        buyout_payment=quote["buyout_payment"],
                        locked_lease_rate=quote["locked_lease_rate"],
                        payments_made=1,
                        last_payment_year=0,
                    )

        # TEST/DEBUG: apply role-keyed opening-inventory overrides (e.g. start
        # the Farmer with 200 Food so food production doesn't cloud a test).
        # Only fires for debug rooms (non-empty mapping); resource names are
        # matched case-insensitively against ResourceType. Logged loudly so a
        # seeded game is never mistaken for a real one.
        if room.debug_starting_inventory:
            res_by_lower = {rt.value.lower(): rt for rt in ResourceType}
            for p in game.players:
                for role in p.roles:
                    overrides = room.debug_starting_inventory.get(role.name)
                    if not overrides:
                        continue
                    for res_name, qty in overrides.items():
                        rt = res_by_lower.get(str(res_name).strip().lower())
                        if rt is None:
                            logger.warning(
                                "Room %s debug inventory: unknown resource %r "
                                "for role %s — skipped.",
                                room_id, res_name, role.name,
                            )
                            continue
                        try:
                            amount = int(qty)
                        except (TypeError, ValueError):
                            continue
                        if amount <= 0:
                            continue
                        p.receive_resources(rt, amount)
                        logger.warning(
                            "[DEBUG SEED] Room %s: %s (%s) granted %d %s at launch.",
                            room_id, p.name, role.name, amount, rt.value,
                        )

        def _broadcast_state():
            state = self.get_game_state(room_id)
            if state:
                self._thread_safe_broadcast(room_id, state)
            # Push discrete market events (Issue #4) so clients (dashboards and AI
            # agents) can react to new bids/asks/fills between full-state snapshots.
            room = self.rooms.get(room_id)
            game = getattr(room, "game", None)
            market = getattr(game, "market", None)
            if market is not None:
                for ev in market.drain_events():
                    self._thread_safe_broadcast(room_id, {"type": "market_event", **ev})

        io.on_action_complete = _broadcast_state

        initial_state = self.get_game_state(room_id)
        if initial_state:
            self._thread_safe_broadcast(room_id, initial_state)

        def run_game():
            try:
                summary = game.run()
                room.summary = summary
                room.status = "finished"
                # Web win condition is investor NET WORTH (cash + equity +
                # loan receivables), not the engine's island total_wealth.
                final_tick = max(0, game.config.num_years * len(SEASONS) - 1)
                fprices = game.market.current_prices()
                books = [p.shareholder_loans for p in game.players]
                spi = {
                    str(p.player_id): share_price(
                        fair_value(
                            p.total_wealth(fprices, game.loan_ledger,
                                           CAPITAL_CATALOGUE, final_tick),
                            p.wealth_history,
                        )
                    )
                    for p in game.players
                }
                nw_ranked = sorted(
                    game.players,
                    key=lambda p: p.net_worth(
                        spi, sh_loans.receivable(books, str(p.player_id))
                    ),
                    reverse=True,
                )
                broadcast({
                    "type": "game_over",
                    "winner": nw_ranked[0].name if nw_ranked else summary.winner.name,
                    "rankings": [
                        {"name": p.name, "roles": p.role_names(),
                         "wealth": round(
                             p.net_worth(spi, sh_loans.receivable(books, str(p.player_id))), 1
                         )}
                        for p in nw_ranked
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
            assigned = lp.role_names[0] if lp.role_names else None
            if not assigned or assigned in used:
                for r in ALL_ROLES:
                    if r not in used:
                        lp.role_names = [r]
                        assigned = r
                        break
            if assigned:
                used.add(assigned)

        # Fill remaining roles with AI
        for role in ALL_ROLES:
            if role not in used:
                ai_id = _short_id()
                room.players.append(LobbyPlayer(
                    player_id=ai_id, name=f"{role} Island (AI)",
                    role_names=[role], is_human=False,
                ))

        return self._launch_game(room_id)

    def _player_capacity(
        self, p, current_tick: int | None = None, season_name: str = "Spring"
    ) -> dict:
        """Compute per-output max-producible + binding constraint for a player.

        Returns a dict shaped for direct UI consumption — the frontend renders
        the Production Capacity panel and Constraint Popup straight from this.
        """
        from ..constants_capacity import CAPITAL_CATALOGUE, PRODUCTION_RECIPES
        from ..constants import FARMER_SEASONAL_CONVERSION
        from ..models.capacity import (
            recipes_for_role, compute_capacity, find_item,
        )
        from ..models.profession import WorkerBand, primary_title
        from ..engine.engineering import (
            active_engineer_specialty_counts,
            adjusted_capacity_for_engineers,
            adjusted_recipe_for_engineers,
            adjusted_workforce_for_engineers,
            specialty_payload,
        )

        # Build workforce by band (active workers only)
        band_counts = p.workforce.band_summary()
        wf_by_band = {
            WorkerBand.MANAGER:    band_counts.get("Manager", 0),
            WorkerBand.TECHNICIAN: band_counts.get("Technician", 0),
            WorkerBand.WORKER:     band_counts.get("Worker", 0),
        }
        engineer_counts = active_engineer_specialty_counts(p)
        effective_wf_by_band = adjusted_workforce_for_engineers(
            wf_by_band, engineer_counts
        )

        on_hand = {r.value: p.inventory.get(r) for r in p.inventory.amounts}

        # Compute the player's expertise-degradation floor once per player
        # (doesn't depend on the recipe), then attach to every output entry
        # below.  Currently scaffolded but the production engine doesn't
        # apply the floor until EXPERTISE_DEGRADATION_ENABLED flips True
        # (calibration work pending).  Payload still reports the would-be
        # floor so the UI can pre-stage the "Operating at X% floor" chip.
        # 2026-05-27 graceful-degradation brief.
        from ..engine.production import ProductionEngine as _ProdEngine
        degradation_floor = _ProdEngine.expertise_degradation_floor(p)

        outputs = []
        seen: set[str] = set()
        for role in p.roles:
            for recipe in recipes_for_role(PRODUCTION_RECIPES, role.name):
                if recipe.output in seen:
                    continue
                seen.add(recipe.output)
                if (
                    recipe.role == "Miner"
                    and recipe.output == ResourceType.METAL.value
                    and p.capital_inventory.get("miner.enhanced_crusher_smelter", 0) > 0
                ):
                    from dataclasses import replace as _replace
                    recipe = _replace(
                        recipe,
                        inputs={
                            k: (v * 0.5 if k == ResourceType.OIL.value else v)
                            for k, v in recipe.inputs.items()
                        },
                    )
                # Apply patent boost to this output's input requirements
                recipe = adjusted_recipe_for_engineers(recipe, engineer_counts)
                mult = p.patent_input_multiplier(recipe.output)
                if mult < 1.0:
                    boosted_inputs = {k: v * mult for k, v in recipe.inputs.items()}
                    from dataclasses import replace as _replace
                    boosted = _replace(recipe, inputs=boosted_inputs)
                else:
                    boosted = recipe
                if recipe.role == "Farmer" and recipe.output == ResourceType.FOOD.value:
                    # Packaged Food accepts either Fish or Meat as its protein.
                    on_hand[ResourceType.FISH.value] = (
                        p.inventory.get(ResourceType.FISH)
                        + p.inventory.get(ResourceType.MEAT)
                    )
                farmer_raw_output = (
                    recipe.role == "Farmer"
                    and recipe.output in FARMER_SEASONAL_CONVERSION[season_name]["outputs"]
                    and recipe.output not in (
                        ResourceType.FOOD.value,
                        ResourceType.MEAT.value,
                    )
                )
                if farmer_raw_output:
                    seasonal_inputs = FARMER_SEASONAL_CONVERSION[season_name]["inputs"]
                    enough_for_seasonal_run = all(
                        p.inventory.get(ResourceType(resource)) >= amount
                        for resource, amount in seasonal_inputs.items()
                    )
                    boosted = recipe
                    on_hand_for_cap = dict(on_hand)
                    for resource in recipe.inputs:
                        on_hand_for_cap[resource] = (
                            float("inf") if enough_for_seasonal_run else 0
                        )
                else:
                    on_hand_for_cap = on_hand
                cap = compute_capacity(
                    recipe=boosted,
                    catalogue=CAPITAL_CATALOGUE,
                    owned=p.capital_inventory,
                    workforce=effective_wf_by_band,
                    on_hand=on_hand_for_cap,
                )
                cap = adjusted_capacity_for_engineers(cap, engineer_counts, recipe.output)
                # Per-input shortfall (units needed to lift the input cap to
                # the next bottleneck). Useful for the constraint popup
                # ("buy 4 more Oil").
                workforce_cap = cap.workforce_cap
                input_cap = cap.input_cap
                input_target = min(
                    cap.equipment_cap,
                    workforce_cap if workforce_cap != float("inf") else cap.equipment_cap,
                )
                if input_target == float("inf") or input_target <= 0:
                    input_target = 1 if boosted.inputs else 0
                inputs_short: dict[str, float] = {}
                if farmer_raw_output:
                    seasonal_inputs = FARMER_SEASONAL_CONVERSION[season_name]["inputs"]
                    for resource, need_total in seasonal_inputs.items():
                        have = p.inventory.get(ResourceType(resource))
                        short = need_total - have
                        if short > 0:
                            inputs_short[resource] = round(short, 2)
                elif input_cap < input_target:
                    for resource, per_unit in boosted.inputs.items():
                        if per_unit <= 0:
                            continue
                        need_total = per_unit * input_target
                        have = on_hand.get(resource, 0)
                        short = need_total - have
                        if short > 0:
                            inputs_short[resource] = round(short, 2)

                # Workforce shortfall by band
                workforce_short: dict[str, float] = {}
                workforce_target = min(
                    cap.equipment_cap,
                    input_cap if input_cap != float("inf") else cap.equipment_cap,
                )
                if workforce_target == float("inf") or workforce_target <= 0:
                    workforce_target = 1 if any(
                        recipe.labour_per_unit(band) > 0 for band in WorkerBand
                    ) else 0
                if workforce_cap < workforce_target:
                    for band in WorkerBand:
                        per_unit = recipe.labour_per_unit(band)
                        if per_unit <= 0:
                            continue
                        need = per_unit * workforce_target
                        have = effective_wf_by_band.get(band, 0)
                        short = need - have
                        if short > 0:
                            # Name the missing workers by their specific
                            # profession title (e.g. "Flight Crew") rather
                            # than the generic band ("Technician") so the
                            # constraint popup reads naturally.
                            label = primary_title(recipe.role, band)
                            # Round UP to whole workers — labour math is
                            # per-output-unit fractional (e.g. 0.04 Farmer
                            # per Food × 3 units = 0.12) but you can't
                            # hire 0.12 of a person.  The playtest report
                            # 2026-05-27 (Comet) flagged "0.12 Farmer" in
                            # Decision Hints as confusing.  Always show
                            # at least 1 missing worker when there's any
                            # shortfall.
                            workforce_short[label] = math.ceil(short)

                # Equipment shortfall. Prefer concrete catalogue options over
                # telling the player "buy capital" and making them hunt.
                equipment_short: dict[str, object] = {}
                equipment_target = min(
                    workforce_cap if workforce_cap != float("inf") else input_cap,
                    input_cap if input_cap != float("inf") else workforce_cap,
                )
                if equipment_target == float("inf") or equipment_target <= 0:
                    equipment_target = 1
                if cap.equipment_cap < equipment_target:
                    needed_capacity = equipment_target - cap.equipment_cap
                    options = []
                    for item in CAPITAL_CATALOGUE:
                        if item.role != recipe.role:
                            continue
                        capacity_each = item.effects.get("capacity", {}).get(recipe.output, 0)
                        unlocks = recipe.output in item.effects.get("unlocks_lines", [])
                        if capacity_each <= 0 and not unlocks:
                            continue
                        count_needed = 1 if unlocks else int(-(-needed_capacity // capacity_each))
                        options.append({
                            "item_id": item.item_id,
                            "name": item.name,
                            "count": count_needed,
                            "capacity_each": capacity_each,
                            "unlocks": unlocks,
                            "cost_each": item.cost,
                            "total_cost": round(item.cost * count_needed, 2),
                            "delivery_seasons": item.delivery_seasons,
                            "owned": p.capital_inventory.get(item.item_id, 0),
                            "description": item.description,
                        })
                    equipment_short = {
                        "needed_capacity": round(needed_capacity, 2),
                        "target": round(equipment_target, 2),
                        "options": options,
                    }

                caps = {
                    "equipment": cap.equipment_cap,
                    "workforce": workforce_cap,
                    "inputs": input_cap,
                }
                max_producible = cap.max_producible
                blockers = [
                    name for name, value in caps.items()
                    if value == max_producible
                ]
                outputs.append({
                    "output":         recipe.output,
                    "role":           recipe.role,
                    "is_service_output": recipe.output == "InsurancePolicies",
                    "max_producible": round(cap.max_producible, 2)
                                      if cap.max_producible != float("inf") else None,
                    "equipment_cap":  round(cap.equipment_cap, 2),
                    "workforce_cap":  round(cap.workforce_cap, 2)
                                      if cap.workforce_cap != float("inf") else None,
                    "input_cap":      round(cap.input_cap, 2)
                                      if cap.input_cap != float("inf") else None,
                    "binding":        cap.binding_constraint,
                    "blockers":       blockers,
                    "inputs_short":   inputs_short,
                    "workforce_short": workforce_short,
                    "equipment_short": equipment_short,
                    "patents_active": p.active_patent_count(recipe.output),
                    "patent_input_mult": round(mult, 3),
                    # Graceful-degradation floor (2026-05-27 brief, GitHub
                    # #47): when < 1.0, the island is missing expertise.
                    # The dashboard surfaces this as an "Operating at X%
                    # floor" chip so the player can see why output is
                    # reduced (or about to be).  1.0 = no floor applies.
                    "degradation_floor": round(degradation_floor, 3),
                    "engineer_specialties": specialty_payload(p),
                })

        effective_capital = p.effective_capital_inventory()
        kitchen_capacity = sum(
            int(spec["food_per_season"]) * effective_capital.get(item_id, 0)
            for item_id, spec in KITCHEN_SPECS.items()
        )
        if kitchen_capacity > 0 and ResourceType.FOOD.value not in seen:
            chef_limited_capacity = 0
            inputs_short: dict[str, float] = {}
            grain_units = p.inventory.get(ResourceType.GRAIN)
            produce_units = p.inventory.get(ResourceType.PRODUCE)
            protein_units = (
                p.inventory.get(ResourceType.FISH) + p.inventory.get(ResourceType.MEAT)
            )
            input_caps = []
            owned_kitchens = []
            for item_id, spec in KITCHEN_SPECS.items():
                count = effective_capital.get(item_id, 0)
                if count <= 0:
                    continue
                item = find_item(CAPITAL_CATALOGUE, item_id)
                label = item.name if item else item_id
                food_each = int(spec["food_per_season"])
                owned_kitchens.append(f"{count} × {label}")
                if spec.get("requires_chef", False):
                    chef_limited_capacity += (
                        min(count, p.workforce.count_profession(Profession.CHEF.value))
                        * food_each
                    )
                else:
                    chef_limited_capacity += count * food_each
                recipe = spec.get("recipe", {})
                for resource_name, per_food in recipe.items():
                    if per_food <= 0:
                        continue
                    have = (
                        protein_units if resource_name == "Protein"
                        else p.inventory.get(ResourceType(resource_name))
                    )
                    input_caps.append(have / per_food)
            input_cap = min(input_caps) if input_caps else float("inf")
            max_producible = min(kitchen_capacity, chef_limited_capacity, input_cap)
            target = min(kitchen_capacity, chef_limited_capacity)
            if target > 0 and input_cap < target:
                for resource_name, per_food in {
                    "Grain": 1,
                    "Produce": 1,
                    "Protein": 1,
                }.items():
                    per_food_needed = max(
                        (
                            spec.get("recipe", {}).get(resource_name, 0)
                            for item_id, spec in KITCHEN_SPECS.items()
                            if effective_capital.get(item_id, 0) > 0
                        ),
                        default=0,
                    )
                    if per_food_needed <= 0:
                        continue
                    have = (
                        protein_units if resource_name == "Protein"
                        else p.inventory.get(ResourceType(resource_name))
                    )
                    short = per_food_needed * target - have
                    if short > 0:
                        inputs_short[resource_name] = round(short, 2)
            workforce_short = {}
            if chef_limited_capacity < kitchen_capacity:
                chef_kitchens = sum(
                    effective_capital.get(item_id, 0)
                    for item_id, spec in KITCHEN_SPECS.items()
                    if spec.get("requires_chef", False)
                )
                chef_short = max(
                    0,
                    chef_kitchens - p.workforce.count_profession(Profession.CHEF.value),
                )
                if chef_short:
                    workforce_short["Chef"] = chef_short
            caps = {
                "equipment": kitchen_capacity,
                "workforce": chef_limited_capacity,
                "inputs": input_cap,
            }
            binding = min(caps, key=caps.get)
            outputs.append({
                "output": ResourceType.FOOD.value,
                "role": "Kitchen",
                "is_service_output": False,
                "max_producible": round(max_producible, 2)
                                  if max_producible != float("inf") else None,
                "equipment_cap": round(kitchen_capacity, 2),
                "workforce_cap": round(chef_limited_capacity, 2),
                "input_cap": round(input_cap, 2)
                              if input_cap != float("inf") else None,
                "binding": binding,
                "blockers": [
                    name for name, value in caps.items()
                    if value == caps[binding]
                ],
                "inputs_short": inputs_short,
                "workforce_short": workforce_short,
                "equipment_short": {},
                "patents_active": 0,
                "patent_input_mult": 1.0,
                "degradation_floor": 1.0,
                "enabled_by": owned_kitchens,
            })

        # Render owned capital with display info (name, role, count)
        capital_owned = []
        for item_id, count in p.capital_inventory.items():
            item = find_item(CAPITAL_CATALOGUE, item_id)
            if not item:
                continue
            failed_count = p.failed_capital.get(item_id, 0)
            queued_repairs = sum(
                int(entry.get("count", 1))
                for entry in p.capital_repair_in_progress
                if entry.get("item_id") == item_id
            )
            # Per-unit detail (#185/#188): each unit's age-quarter, status and
            # the order conditions it was bought with.
            units = []
            for u in p.capital_units.get(item_id, []):
                age = max(0, (current_tick or 0) - u.acquired_tick)
                units.append({
                    "unit_id":                u.unit_id,
                    "status":                 u.status,
                    "quarter":                min(20, age + 1),
                    "warranty":               u.warranty,
                    "spares_attached":        u.spares_attached,
                    "maintenance_term_years": u.maintenance_term_years,
                    "predictive_maintenance": u.predictive_maintenance,
                    "expedited_eligible":     u.expedited_eligible,
                    "purchase_value":         u.purchase_value,
                })
            capital_owned.append({
                "item_id":     item_id,
                "name":        item.name,
                "role":        item.role,
                "count":       count,
                "warrantied":  p.capital_warranties.get(item_id, 0),
                "failed":      failed_count,
                "repairable_failed": max(0, failed_count - queued_repairs),
                "description": item.description,
                "units":       units,
            })
        # Items still arriving
        in_transit = []
        for entry in p.capital_in_transit:
            rendered = dict(entry)
            item = find_item(CAPITAL_CATALOGUE, entry.get("item_id", ""))
            if item:
                rendered["name"] = item.name
                rendered["role"] = item.role
                rendered["description"] = item.description
            arrives_at = int(entry.get("arrives_at_tick", 0))
            rendered["arrival_year"] = arrives_at // len(SEASONS) + 1
            rendered["arrival_season"] = SEASONS[arrives_at % len(SEASONS)]
            if current_tick is not None:
                rendered["seasons_remaining"] = max(0, arrives_at - current_tick)
            in_transit.append(rendered)
        repairs_in_progress = []
        for entry in p.capital_repair_in_progress:
            rendered = dict(entry)
            item = find_item(CAPITAL_CATALOGUE, entry.get("item_id", ""))
            if item:
                rendered["name"] = item.name
                rendered["role"] = item.role
                rendered["description"] = item.description
            completes_at = int(entry.get("completes_at_tick", 0))
            rendered["completion_year"] = completes_at // len(SEASONS) + 1
            rendered["completion_season"] = SEASONS[completes_at % len(SEASONS)]
            if current_tick is not None:
                rendered["seasons_remaining"] = max(0, completes_at - current_tick)
            repairs_in_progress.append(rendered)

        # Build & Develop catalogue (UI v3 phase 4): every capital item this
        # island's role(s) can build, with owned / failed / mandatory state, so
        # the dashboard can render a persistent Build & Develop panel instead
        # of only exposing the catalogue inside the Purchase Equipment prompt.
        from ..models.capacity import items_for_role as _items_for_role
        from ..constants_capacity import MANDATORY_MINIMUM_INVESTMENT as _MANDATORY
        mandatory_ids: set[str] = set()
        for role in p.roles:
            mandatory_ids.update(_MANDATORY.get(role.name, []))
        capital_catalogue = []
        seen_cat: set[str] = set()
        for role in p.roles:
            for item in _items_for_role(CAPITAL_CATALOGUE, role.name):
                if item.item_id in seen_cat:
                    continue
                seen_cat.add(item.item_id)
                capital_catalogue.append({
                    "item_id":          item.item_id,
                    "name":             item.name,
                    "role":             item.role,
                    "cost":             round(item.cost),
                    "cash_only":        bool(item.effects.get("cash_only", False)),
                    "delivery_seasons": item.delivery_seasons,
                    "description":      item.description,
                    "owned":            p.capital_inventory.get(item.item_id, 0),
                    "failed":           p.failed_capital.get(item.item_id, 0),
                    "repairable_failed": max(
                        0,
                        p.failed_capital.get(item.item_id, 0) - sum(
                            int(entry.get("count", 1))
                            for entry in p.capital_repair_in_progress
                            if entry.get("item_id") == item.item_id
                        ),
                    ),
                    "mandatory":        item.item_id in mandatory_ids,
                })

        return {
            "outputs":         outputs,
            "capital_owned":   capital_owned,
            "capital_catalogue": capital_catalogue,
            "capital_in_transit": in_transit,
            "capital_repair_in_progress": repairs_in_progress,
            "band_counts":     band_counts,
            "engineer_specialties": specialty_payload(p),
        }

    @staticmethod
    def _profession_label(profession: str) -> str:
        try:
            return PROFESSION_LABEL.get(Profession(profession), profession)
        except ValueError:
            return profession

    def _training_pipeline_for_player(
        self,
        game: Game,
        player_id: int,
        player_names: dict[int, str],
        current_year_idx: int,
        current_season_idx: int,
    ) -> list[dict]:
        pipeline = []
        training = getattr(game, "training", None)
        if not training:
            return pipeline

        # Build a quick lookup of Educator players so we can re-run the
        # capacity-status check from the requester's side and report
        # *why* a pending batch is blocked (Sub-issue blocker + seasons-
        # blocked counter for the requester's dashboard, per the
        # training-expertise-deadlock brief Layer 3).
        turn_manager = getattr(game, "turn_manager", None)
        engine_players = {
            ep.player_id: ep for ep in getattr(game, "players", [])
        }
        requester_player = engine_players.get(player_id)

        for req in training.active_for_player(player_id):
            if req.return_year >= 0 and req.return_season >= 0:
                seasons_remaining = max(
                    0,
                    (req.return_year - current_year_idx) * len(SEASONS)
                    + (req.return_season - current_season_idx),
                )
                return_year = req.return_year + 1
                return_season = (
                    SEASONS[req.return_season]
                    if req.return_season < len(SEASONS)
                    else str(req.return_season)
                )
            else:
                seasons_remaining = None
                return_year = None
                return_season = None

            # Pipeline-health fields (only meaningful for AWAITING_EDUCATOR
            # requests, which are the deadlock cases).  For other statuses
            # these stay None / 0 / False so the existing client code is
            # untouched.
            blocker_reason: str | None = None
            seasons_blocked = 0
            can_supply_expertise = False
            if req.status.value == "awaiting_educator":
                if req.proposed_year >= 0 and req.proposed_season >= 0:
                    seasons_blocked = max(
                        0,
                        (current_year_idx - req.proposed_year) * len(SEASONS)
                        + (current_season_idx - req.proposed_season),
                    )
                educator = engine_players.get(req.educator_id)
                if educator is not None and turn_manager is not None:
                    try:
                        ok, reason = turn_manager._training_capacity_status(
                            educator, req
                        )
                    except Exception:
                        ok, reason = True, ""
                    if not ok:
                        blocker_reason = reason
                        if (
                            requester_player is not None
                            and "Expertise" in reason
                        ):
                            # Mirror the SUPPLY_TRAINING_EXPERTISE action's
                            # eligibility check: only show True when the
                            # requester actually has enough Expertise to
                            # cover the Educator's shortfall.
                            from ..models.profession import (  # noqa: WPS433
                                WorkerBand, band_of,
                            )

                            band = band_of(req.target_profession)
                            per_course = 2 if band == WorkerBand.MANAGER else 1
                            n_courses = (
                                turn_manager.courses_needed(len(req.worker_ids))
                            )
                            needed = per_course * n_courses
                            have_at_educator = educator.inventory.get(
                                ResourceType.EXPERTISE
                            )
                            shortfall = max(0, needed - have_at_educator)
                            have_at_requester = requester_player.inventory.get(
                                ResourceType.EXPERTISE
                            )
                            can_supply_expertise = (
                                shortfall > 0 and have_at_requester >= shortfall
                            )

            target_label = self._profession_label(req.target_profession)
            if req.engineer_specialty:
                target_label = f"{target_label} ({req.engineer_specialty})"
            pipeline.append({
                "batch_id": req.batch_id,
                "worker_count": len(req.worker_ids),
                "target_profession": target_label,
                "engineer_specialty": req.engineer_specialty or None,
                "duration_seasons": req.duration_seasons or None,
                # Status is the canonical TrainingStatus enum value.
                "status": req.status.value,
                "educator_player_id": req.educator_id,
                "educator_name": player_names.get(
                    req.educator_id,
                    f"Player {req.educator_id}",
                ),
                "transport_mode": req.transport_mode,
                "tickets_supplied_by_requester": req.tickets_supplied_by_requester,
                "dollops_to_educator": round(req.dollops_to_educator, 1),
                "return_year": return_year,
                "return_season": return_season,
                "seasons_remaining": seasons_remaining,
                "counter_message": req.counter_message or None,
                # Deadlock-visibility fields (2026-05-27 training-expertise
                # -deadlock brief Layer 3).
                "blocker_reason": blocker_reason,
                "seasons_blocked": seasons_blocked,
                "can_supply_expertise": can_supply_expertise,
            })
        return pipeline

    def _training_targets_for_player(
        self,
        game: Game,
        player_id: int,
    ) -> dict[int, str]:
        training = getattr(game, "training", None)
        if not training:
            return {}
        return training.dispatched_training_targets(player_id)

    def _training_options_for_player(
        self,
        game: Game,
        player: Player,
        year: int,
        season: int,
    ) -> dict:
        """Read-only menu for the Training Desk batch dialog (#158).

        Surfaces the same selectable professions / capacity / eligible-worker
        data the sequential wizard computes in
        ``TurnManager._action_request_training`` so the web client can build a
        multi-row booking dialog without a round-trip per field.  Mirrors that
        logic — no new mechanics.
        """
        training = getattr(game, "training", None)
        empty = {"professions": [], "eligible_worker_count": 0, "exhausted": []}
        if not training:
            return empty

        def _label(prof: str) -> str:
            try:
                return PROFESSION_LABEL.get(Profession(prof), prof)
            except ValueError:
                return prof

        capacity_map = training.capacity_summary(year, season)
        try:
            deficits = game.turn_manager._training_skill_deficits(player)
        except Exception:
            deficits = {}

        professions = []
        exhausted = []
        for prof, info in capacity_map.items():
            remaining = info.get("remaining", 0)
            if remaining > 0:
                professions.append({
                    "value": prof,
                    "label": _label(prof),
                    "remaining": remaining,
                    "annual_cap": info.get("annual_cap", 0),
                    "seasonal_cap": info.get("seasonal_cap"),
                    "suggested_count": max(0, min(deficits.get(prof, 0), remaining)),
                })
            else:
                exhausted.append({
                    "value": prof,
                    "label": _label(prof),
                    "trained": info.get("trained", 0),
                    "annual_cap": info.get("annual_cap", 0),
                })

        active = player.workforce.active_count
        eligible = (
            set(player.workforce.get_unskilled_ids(active))
            | set(player.workforce.get_trainable_ids(active))
        ) - set(training.reserved_worker_ids(player.player_id))

        return {
            "professions": professions,
            "eligible_worker_count": len(eligible),
            "exhausted": exhausted,
        }

    def _staffing_contracts_for_player(
        self,
        game: "Game",
        player_id: int,
        player_names: dict[int, str],
        current_year_idx: int,
        current_season_idx: int,
    ) -> list[dict]:
        """Serialise all active staffing contracts involving this player."""
        staffing = getattr(game, "staffing", None)
        if not staffing:
            return []
        from ..models.staffing import StaffingStatus
        from ..constants import SEASONS
        contracts = staffing.active_for_player(player_id)
        result = []
        for c in contracts:
            if c.return_year >= 0 and c.return_season >= 0:
                return_year_display = c.return_year + 1
                return_season_name = (
                    SEASONS[c.return_season] if c.return_season < len(SEASONS) else str(c.return_season)
                )
                seasons_remaining = max(
                    0,
                    (c.return_year - current_year_idx) * len(SEASONS)
                    + (c.return_season - current_season_idx),
                )
            else:
                return_year_display = None
                return_season_name = None
                seasons_remaining = None
            result.append({
                "contract_id": c.contract_id,
                "role": "requester" if c.requester_id == player_id else "provider",
                "other_player_id": c.provider_id if c.requester_id == player_id else c.requester_id,
                "other_player_name": player_names.get(
                    c.provider_id if c.requester_id == player_id else c.requester_id,
                    "Unknown",
                ),
                "profession": c.profession,
                "staff_count": c.staff_count,
                "duration_seasons": c.duration_seasons,
                "fee_total": round(c.fee_total, 1),
                "tickets_required": c.tickets_required,
                "tickets_supplied_by_requester": c.tickets_supplied_by_requester,
                "status": c.status.value,
                "return_year": return_year_display,
                "return_season": return_season_name,
                "seasons_remaining": seasons_remaining,
                "counter_fee": c.counter_fee,
                "counter_message": c.counter_message or None,
                "decision_acknowledged": c.decision_acknowledged,
            })
        return result

    def _training_queue_order_for_player(
        self,
        game: Game,
        player_id: int,
        player_names: dict[int, str],
    ) -> list[dict]:
        player = next((p for p in game.players if p.player_id == player_id), None)
        if player is None or not any(role.name == "Educator" for role in player.roles):
            return []
        training = getattr(game, "training", None)
        if not training:
            return []
        return [
            {
                "batch_id": req.batch_id,
                "requester_name": player_names.get(
                    req.requester_id, f"Player {req.requester_id}"
                ),
                "target_profession": self._profession_label(req.target_profession),
                "priority": req.priority,
                "dollops_offered": round(req.dollops_to_educator, 1),
                "requested_year": req.proposed_year + 1,
                "requested_season": SEASONS[req.proposed_season]
                    if 0 <= req.proposed_season < len(SEASONS)
                    else str(req.proposed_season),
            }
            for req in training.sorted_pending_for_educator(player_id)
        ]

    def _training_decisions_for_player(
        self,
        game: Game,
        player_id: int,
        current_year_idx: int,
        current_season_idx: int,
    ) -> list[dict]:
        training = getattr(game, "training", None)
        if not training:
            return []
        decisions = []
        for req in training.decisions_for_requester(player_id):
            decline_year = req.decline_year + 1 if req.decline_year >= 0 else None
            decline_season = (
                SEASONS[req.decline_season]
                if 0 <= req.decline_season < len(SEASONS)
                else None
            )
            decisions.append({
                "batch_id": req.batch_id,
                "status": req.status.value,
                "decline_reason": req.decline_reason,
                "decline_year": decline_year,
                "decline_season": decline_season,
                "original_offer": round(
                    req.original_dollops_to_educator
                    if req.original_dollops_to_educator
                    else req.dollops_to_educator,
                    1,
                ),
                "suggested_offer_if_any": (
                    round(req.dollops_to_educator, 1)
                    if req.status.value == "countered"
                    else None
                ),
                "target_profession": self._profession_label(req.target_profession),
                "n_workers": len(req.worker_ids),
            })
        return decisions

    def _training_capacity_for_player(
        self,
        game: Game,
        current_year_idx: int,
        current_season_idx: int,
    ) -> list[dict]:
        training = getattr(game, "training", None)
        if not training:
            return []
        rows: list[dict] = []
        for profession, info in training.capacity_summary(
            current_year_idx, current_season_idx
        ).items():
            remaining = info.get("remaining", 0)
            trained = info.get("trained", 0)
            annual_cap = info.get("annual_cap", 0)
            seasonal_cap = info.get("seasonal_cap")
            unavailable_reason = ""
            if remaining <= 0:
                if seasonal_cap is not None and trained < annual_cap:
                    unavailable_reason = (
                        f"Seasonal cap reached ({seasonal_cap}/season); "
                        "try again next season."
                    )
                else:
                    unavailable_reason = (
                        f"Annual cap reached ({trained}/{annual_cap}); "
                        "try again next year."
                    )
            rows.append({
                "profession": profession,
                "label": self._profession_label(profession),
                "available": remaining > 0,
                "remaining": remaining,
                "annual_cap": annual_cap,
                "trained": trained,
                "seasonal_cap": seasonal_cap,
                "unavailable_reason": unavailable_reason,
            })
        return rows

    @staticmethod
    def _deal_side_payload(resource: ResourceType | None, qty: int) -> dict | None:
        if resource is None or qty <= 0:
            return None
        return {"resource": resource.value, "qty": int(qty)}

    @staticmethod
    def _parse_deal_side(
        msg: dict,
        object_key: str,
        resource_key: str,
        qty_key: str,
        *,
        default_resource: ResourceType | None = None,
        default_qty: int = 0,
    ) -> tuple[ResourceType | None, int]:
        raw = msg.get(object_key)
        if isinstance(raw, dict):
            resource_value = raw.get("resource")
            qty_value = raw.get("qty", raw.get("quantity", 0))
        else:
            resource_value = msg.get(resource_key)
            qty_value = msg.get(qty_key, default_qty)
        if resource_value is None:
            resource = default_resource
        else:
            resource_text = str(resource_value).strip()
            resource = ResourceType(resource_text) if resource_text else None
        try:
            qty = int(qty_value)
        except (TypeError, ValueError):
            qty = default_qty
        if resource is None or qty <= 0:
            return None, 0
        return resource, qty

    def _deal_payload(
        self,
        deal: DealProposal,
        player_names: dict[int, str],
        viewer_id: int | None = None,
    ) -> dict:
        counterparty_id = None
        if viewer_id is not None:
            if viewer_id == deal.proposer_id:
                counterparty_id = deal.target_id
            elif viewer_id == deal.target_id:
                counterparty_id = deal.proposer_id
        return {
            "deal_id": deal.deal_id,
            "status": deal.status.value,
            "proposer_id": deal.proposer_id,
            "proposer_name": player_names.get(
                deal.proposer_id, f"Player {deal.proposer_id}"
            ),
            "target_id": deal.target_id,
            "target_name": player_names.get(
                deal.target_id, f"Player {deal.target_id}"
            ),
            "counterparty_id": counterparty_id,
            "counterparty_name": (
                player_names.get(counterparty_id, f"Player {counterparty_id}")
                if counterparty_id is not None else None
            ),
            "awaiting_id": deal.awaiting_id,
            "awaiting_name": (
                player_names.get(deal.awaiting_id, f"Player {deal.awaiting_id}")
                if deal.awaiting_id is not None else None
            ),
            "offer": self._deal_side_payload(deal.offer_resource, deal.offer_qty),
            "request": self._deal_side_payload(deal.request_resource, deal.request_qty),
            "sweetener": round(deal.gold_sweetener, 1),
            "message": deal.message or None,
            "last_response_by_id": deal.last_response_by_id,
            "last_response_by_name": (
                player_names.get(
                    deal.last_response_by_id,
                    f"Player {deal.last_response_by_id}",
                )
                if deal.last_response_by_id is not None else None
            ),
        }

    def _deal_lobby_id_for_engine_id(self, room, engine_player_id: int) -> str | None:
        for lobby_id, engine_id in (room.lobby_to_engine_id or {}).items():
            if engine_id == engine_player_id:
                return lobby_id
        return None

    def _deal_state_for_viewer(
        self,
        game: Game,
        viewer_engine_id: int | None,
        player_names: dict[int, str],
    ) -> tuple[list[dict], list[dict]]:
        if viewer_engine_id is None:
            return [], []
        deals = getattr(game.ledger, "deals", [])
        awaiting = [
            self._deal_payload(deal, player_names, viewer_engine_id)
            for deal in deals
            if deal.awaiting_id == viewer_engine_id
            and deal.status in ACTIVE_DEAL_STATUSES
        ]
        mine = [
            self._deal_payload(deal, player_names, viewer_engine_id)
            for deal in deals
            if deal.proposer_id == viewer_engine_id
        ]
        return awaiting, mine

    async def _handle_deal_propose(
        self,
        room_id: str,
        lobby_player_id: str,
        msg: dict,
        websocket,
    ) -> None:
        room = self.rooms.get(room_id)
        if not room or not room.game:
            await websocket.send_text(json.dumps({"type": "error", "message": "Room not found"}))
            return
        proposer = self._engine_player_for_lobby(room, lobby_player_id)
        if proposer is None:
            await websocket.send_text(json.dumps({"type": "error", "message": "Player not in game"}))
            return
        target = self._resolve_deal_target(room, msg)
        if target is None or target.player_id == proposer.player_id:
            await websocket.send_text(json.dumps({"type": "error", "message": "Invalid deal target"}))
            return

        try:
            offer_resource, offer_qty = self._parse_deal_side(
                msg, "offer", "offer_resource", "offer_qty"
            )
            request_resource, request_qty = self._parse_deal_side(
                msg, "request", "request_resource", "request_qty"
            )
            sweetener = float(msg.get("sweetener", msg.get("gold_sweetener", 0.0)) or 0.0)
            deal = room.game.turn_manager.trading.propose_deal(
                proposer,
                target,
                offer_resource,
                offer_qty,
                request_resource,
                request_qty,
                sweetener,
            )
        except (InvalidDealError, ValueError) as exc:
            await websocket.send_text(json.dumps({"type": "error", "message": str(exc)}))
            return

        player_names = {p.player_id: p.name for p in room.game.players}
        payload = self._deal_payload(deal, player_names, proposer.player_id)
        await websocket.send_text(json.dumps({
            "type": "deal_propose_ack",
            "result": "submitted",
            "deal_id": deal.deal_id,
            "deal": payload,
        }))
        state = self.get_game_state(room_id, lobby_player_id)
        if state:
            await websocket.send_text(json.dumps(state))
        target_lobby_id = self._deal_lobby_id_for_engine_id(room, target.player_id)
        if target_lobby_id:
            self._thread_safe_send(room_id, target_lobby_id, {
                "type": "deal_response",
                "deal_id": deal.deal_id,
                "result": "proposed",
                "from": proposer.name,
                "deal": self._deal_payload(deal, player_names, target.player_id),
            })
            self._thread_safe_send(
                room_id,
                target_lobby_id,
                self.get_game_state(room_id, target_lobby_id) or {},
            )

    def _resolve_deal_target(self, room, msg: dict) -> Player | None:
        raw = msg.get("target_player_id", msg.get("target_id"))
        if raw is None:
            return None
        engine_id = None
        try:
            engine_id = int(raw)
        except (TypeError, ValueError):
            engine_id = (room.lobby_to_engine_id or {}).get(str(raw))
        return next(
            (p for p in room.game.players if p.player_id == engine_id),
            None,
        )

    async def _handle_deal_respond(
        self,
        room_id: str,
        lobby_player_id: str,
        msg: dict,
        websocket,
    ) -> None:
        room = self.rooms.get(room_id)
        if not room or not room.game:
            await websocket.send_text(json.dumps({"type": "error", "message": "Room not found"}))
            return
        actor = self._engine_player_for_lobby(room, lobby_player_id)
        if actor is None:
            await websocket.send_text(json.dumps({"type": "error", "message": "Player not in game"}))
            return
        try:
            deal_id = int(msg.get("deal_id"))
        except (TypeError, ValueError):
            await websocket.send_text(json.dumps({"type": "error", "message": "Invalid deal_id"}))
            return
        deal = room.game.ledger.deal_by_id(deal_id)
        if deal is None:
            await websocket.send_text(json.dumps({"type": "error", "message": f"Deal #{deal_id} not found"}))
            return
        if deal.awaiting_id != actor.player_id or deal.status not in ACTIVE_DEAL_STATUSES:
            await websocket.send_text(json.dumps({
                "type": "error",
                "message": f"Deal #{deal_id} is not awaiting your response",
            }))
            return

        player_by_id = {p.player_id: p for p in room.game.players}
        proposer = player_by_id.get(deal.proposer_id)
        target = player_by_id.get(deal.target_id)
        if proposer is None or target is None:
            room.game.ledger.expire(deal.deal_id)
            await websocket.send_text(json.dumps({
                "type": "deal_response_ack",
                "result": "expired",
                "deal_id": deal.deal_id,
            }))
            return

        action = str(msg.get("action", "")).strip().lower()
        result = action
        try:
            if action == "accept":
                room.game.turn_manager.trading.accept_deal(
                    deal,
                    acceptor=target,
                    proposer=proposer,
                    acquired_tick=(
                        getattr(room, "current_year_index", 0) * len(SEASONS)
                        + getattr(room, "current_season_index", 0)
                    ),
                    players=room.game.players,
                )
                result = "accepted"
            elif action == "reject":
                room.game.turn_manager.trading.reject_deal(deal)
                deal.last_response_by_id = actor.player_id
                deal.message = str(msg.get("message", "") or "").strip()
                result = "rejected"
            elif action == "return":
                offer_resource, offer_qty = self._parse_deal_side(
                    msg,
                    "new_offer",
                    "new_offer_resource",
                    "new_offer_qty",
                    default_resource=deal.offer_resource,
                    default_qty=deal.offer_qty,
                )
                request_resource, request_qty = self._parse_deal_side(
                    msg,
                    "new_request",
                    "new_request_resource",
                    "new_request_qty",
                    default_resource=deal.request_resource,
                    default_qty=deal.request_qty,
                )
                sweetener = float(
                    msg.get(
                        "new_sweetener",
                        msg.get("new_gold_sweetener", deal.gold_sweetener),
                    )
                    or 0.0
                )
                room.game.turn_manager.trading.return_deal(
                    deal,
                    actor.player_id,
                    offer_resource,
                    offer_qty,
                    request_resource,
                    request_qty,
                    sweetener,
                    str(msg.get("message", "") or ""),
                )
                result = "returned"
            else:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": f"Unknown deal response action: {action!r}",
                }))
                return
        except StaleResourceError as exc:
            room.game.ledger.expire(deal.deal_id)
            result = "expired"
            deal.message = str(exc)
        except (InvalidDealError, ValueError) as exc:
            await websocket.send_text(json.dumps({"type": "error", "message": str(exc)}))
            return

        player_names = {p.player_id: p.name for p in room.game.players}
        actor_payload = self._deal_payload(deal, player_names, actor.player_id)
        await websocket.send_text(json.dumps({
            "type": "deal_response_ack",
            "result": result,
            "deal_id": deal.deal_id,
            "deal": actor_payload,
        }))
        state = self.get_game_state(room_id, lobby_player_id)
        if state:
            await websocket.send_text(json.dumps(state))

        notify_engine_id = deal.awaiting_id
        if result in ("accepted", "rejected", "expired"):
            notify_engine_id = (
                deal.proposer_id
                if actor.player_id == deal.target_id else deal.target_id
            )
        if notify_engine_id is not None:
            notify_lobby_id = self._deal_lobby_id_for_engine_id(room, notify_engine_id)
            if notify_lobby_id:
                self._thread_safe_send(room_id, notify_lobby_id, {
                    "type": "deal_response",
                    "deal_id": deal.deal_id,
                    "result": result,
                    "from": actor.name,
                    "deal": self._deal_payload(deal, player_names, notify_engine_id),
                })
                self._thread_safe_send(
                    room_id,
                    notify_lobby_id,
                    self.get_game_state(room_id, notify_lobby_id) or {},
                )

    async def _handle_training_counter_response(
        self,
        room_id: str,
        lobby_player_id: str,
        msg: dict,
        websocket,
    ) -> None:
        """Handle a requester's response to a training counter-offer.

        Message fields:
          batch_id : int   — the TrainingRequest batch_id
          action   : str   — "accept" | "counter" | "reject" | "ack"
          new_fee  : float — (counter only) the new proposed fee
          message  : str   — (counter only) optional message to Educator
        """
        room = self.rooms.get(room_id)
        if not room or not room.game:
            await websocket.send_text(json.dumps({"type": "error", "message": "Room not found"}))
            return

        engine_pid = (room.lobby_to_engine_id or {}).get(lobby_player_id)
        if engine_pid is None:
            await websocket.send_text(json.dumps({"type": "error", "message": "Player not in game"}))
            return

        training = getattr(room.game, "training", None)
        if not training:
            await websocket.send_text(json.dumps({"type": "error", "message": "Training not initialised"}))
            return

        batch_id = msg.get("batch_id")
        action = msg.get("action", "")

        try:
            if action == "approve":
                req = training.requester_accept_counter(batch_id)
                req.decision_acknowledged = True
                ack_msg = {"type": "training_counter_ack", "result": "accepted", "batch_id": batch_id}

            elif action == "counter":
                new_fee = float(msg.get("new_fee", 0))
                message = str(msg.get("message", ""))
                if new_fee <= 0:
                    await websocket.send_text(json.dumps({
                        "type": "error", "message": "Counter fee must be positive"
                    }))
                    return
                training.requester_counter(batch_id, new_fee, message)
                ack_msg = {"type": "training_counter_ack", "result": "countered", "batch_id": batch_id}

            elif action == "reject":
                req = training.requester_reject_counter(batch_id)
                req.decision_acknowledged = True
                ack_msg = {"type": "training_counter_ack", "result": "rejected", "batch_id": batch_id}

            elif action == "ack":
                training.acknowledge_decision(engine_pid, batch_id)
                ack_msg = {"type": "training_counter_ack", "result": "acked", "batch_id": batch_id}

            else:
                await websocket.send_text(json.dumps({
                    "type": "error", "message": f"Unknown training counter action: {action!r}"
                }))
                return

        except (ValueError, KeyError) as e:
            await websocket.send_text(json.dumps({"type": "error", "message": str(e)}))
            return

        await websocket.send_text(json.dumps(ack_msg))

        # Broadcast fresh state to the requester so their decision cards clear
        state = self.get_game_state(room_id, lobby_player_id)
        if state:
            await websocket.send_text(json.dumps(state))

        # If the requester counter-countered, also notify the Educator that there
        # is a new pending review.  We can't interrupt their turn thread, but a
        # state broadcast will refresh their sidebar on next UI poll.
        if action in ("approve", "counter", "reject"):
            # Find the Educator player and send them a fresh state too.
            req_obj = training.request_by_id(batch_id)
            if req_obj:
                educator_lobby_id = None
                for lp_id, ep in (room.lobby_to_engine_id or {}).items():
                    if ep == req_obj.educator_id:
                        educator_lobby_id = lp_id
                        break
                if educator_lobby_id:
                    self._thread_safe_send(
                        room_id, educator_lobby_id,
                        self.get_game_state(room_id, educator_lobby_id) or {},
                    )

    async def _handle_order_batch(
        self,
        room_id: str,
        lobby_player_id: str,
        msg: dict,
        websocket,
    ) -> None:
        room = self.rooms.get(room_id)
        batch_ref = msg.get("batch_ref")
        if not room or not room.game or room.status != "running":
            await websocket.send_text(json.dumps({
                "type": "order_batch_result",
                "batch_ref": batch_ref,
                "results": [],
                "error": "Game is not running.",
            }))
            return
        player = self._engine_player_for_lobby(room, lobby_player_id)
        if player is None:
            await websocket.send_text(json.dumps({
                "type": "order_batch_result",
                "batch_ref": batch_ref,
                "results": [],
                "error": "Player not in game.",
            }))
            return
        orders = msg.get("orders") or []
        results = room.game.turn_manager.trading.execute_order_list(
            player,
            orders,
            room.game.players,
        )
        await websocket.send_text(json.dumps({
            "type": "order_batch_result",
            "batch_ref": batch_ref,
            "results": results,
        }))
        state = self.get_game_state(room_id, lobby_player_id)
        if state:
            await websocket.send_text(json.dumps(state))

    async def _handle_market_order_update(
        self,
        room_id: str,
        lobby_player_id: str,
        msg: dict,
        websocket,
    ) -> None:
        room = self.rooms.get(room_id)
        if not room or not room.game or room.status != "running":
            await websocket.send_text(json.dumps({
                "type": "market_order_update_ack",
                "ok": False,
                "error": "Game is not running.",
            }))
            return
        player = self._engine_player_for_lobby(room, lobby_player_id)
        if player is None:
            await websocket.send_text(json.dumps({
                "type": "market_order_update_ack",
                "ok": False,
                "error": "Player not in game.",
            }))
            return

        side = str(msg.get("side", "")).strip().lower()
        action = str(msg.get("action", "cancel")).strip().lower()
        try:
            order_id = int(msg.get("order_id"))
            new_remaining = int(msg.get("remaining", 0))
            if side == "ask":
                if action == "cancel":
                    order = room.game.market.cancel_offer(player, order_id)
                elif action == "reduce":
                    order = room.game.market.reduce_offer(
                        player, order_id, new_remaining
                    )
                else:
                    raise ValueError("Unknown market order action")
                remaining = order.remaining
            elif side == "bid":
                if action == "cancel":
                    order = room.game.market.cancel_bid(player, order_id)
                elif action == "reduce":
                    order = room.game.market.reduce_bid(
                        player, order_id, new_remaining
                    )
                else:
                    raise ValueError("Unknown market order action")
                remaining = order.remaining
            else:
                raise ValueError("Order side must be 'ask' or 'bid'")
        except (TypeError, ValueError, PermissionError) as exc:
            await websocket.send_text(json.dumps({
                "type": "market_order_update_ack",
                "ok": False,
                "error": str(exc),
            }))
            return

        await websocket.send_text(json.dumps({
            "type": "market_order_update_ack",
            "ok": True,
            "side": side,
            "action": action,
            "order_id": order_id,
            "remaining": remaining,
        }))
        state = self.get_game_state(room_id, lobby_player_id)
        if state:
            await websocket.send_text(json.dumps(state))

    async def _handle_training_batch(
        self,
        room_id: str,
        lobby_player_id: str,
        msg: dict,
        websocket,
    ) -> None:
        room = self.rooms.get(room_id)
        batch_ref = msg.get("batch_ref")
        if not room or not room.game or room.status != "running":
            await websocket.send_text(json.dumps({
                "type": "training_batch_result",
                "batch_ref": batch_ref,
                "results": [],
                "error": "Game is not running.",
            }))
            return
        requester = self._engine_player_for_lobby(room, lobby_player_id)
        if requester is None:
            await websocket.send_text(json.dumps({
                "type": "training_batch_result",
                "batch_ref": batch_ref,
                "results": [],
                "error": "Player not in game.",
            }))
            return

        year = getattr(room, "current_year_index", 0)
        season = getattr(room, "current_season_index", 0)
        results = []
        for index, row in enumerate(msg.get("requests") or []):
            results.append(
                self._submit_training_batch_row(room, requester, row or {}, index, year, season)
            )

        await websocket.send_text(json.dumps({
            "type": "training_batch_result",
            "batch_ref": batch_ref,
            "results": results,
        }))
        state = self.get_game_state(room_id, lobby_player_id)
        if state:
            await websocket.send_text(json.dumps(state))

    def _submit_training_batch_row(
        self,
        room,
        requester: Player,
        row: dict,
        index: int,
        year: int,
        season: int,
    ) -> dict:
        try:
            profession = str(row.get("profession", "")).strip()
            count = int(row.get("count", 0))
            if not profession:
                raise ValueError("profession is required")
            if count <= 0:
                raise ValueError("count must be positive")
            educator = self._resolve_training_educator(room, requester, row)
            if educator is None:
                raise ValueError("No Educator player in this game.")
            if not any(role.name == "Educator" for role in educator.roles):
                raise ValueError("campus_player_id must identify an Educator.")
            worker_ids = self._select_training_workers(
                requester,
                count,
                room.game.training,
            )
            if len(worker_ids) < count:
                raise ValueError(
                    f"Only {len(worker_ids)} eligible worker(s) available."
                )
            transport_mode = str(row.get("transport_mode") or "air_ticket")
            if educator.player_id == requester.player_id:
                transport_mode = "self_training"
            tickets = int(row.get("tickets_supplied_by_requester", 0) or 0)
            fee = float(row.get("dollops_to_educator", row.get("fee", 0.0)) or 0.0)
            if transport_mode == "self_training":
                tickets = 0
                fee = 0.0
            specialty = str(row.get("specialty", row.get("engineer_specialty", "")) or "")
            duration = room.game.turn_manager._training_duration_for_selection(
                profession,
                worker_ids,
                requester,
                educator,
                specialty,
            )
            settling = settling_seasons_on_return(
                profession,
                has_technical_workshop=campus_has_technical_workshop(educator),
            )
            req = room.game.training.propose(
                requester_id=requester.player_id,
                worker_ids=worker_ids,
                educator_id=educator.player_id,
                dollops_to_educator=fee,
                target_profession=profession,
                year=year,
                season=season,
                transport_mode=transport_mode,
                tickets_supplied_by_requester=tickets,
                engineer_specialty=specialty,
                duration_seasons=duration,
                settling_seasons_on_return=settling,
            )
            return {
                "index": index,
                "status": "submitted",
                "batch_id": req.batch_id,
            }
        except (TrainingCapacityError, ValueError, TypeError) as exc:
            return {"index": index, "status": "rejected", "reason": str(exc)}

    def _select_training_workers(self, requester: Player, count: int, training) -> list[int]:
        trainable = requester.workforce.get_trainable_ids(requester.workforce.active_count)
        committed = training.reserved_worker_ids(requester.player_id)
        return [worker_id for worker_id in trainable if worker_id not in committed][:count]

    def _resolve_training_educator(self, room, requester: Player, row: dict) -> Player | None:
        campus_id = row.get("campus_player_id", row.get("educator_id"))
        if campus_id is not None:
            try:
                engine_id = int(campus_id)
            except (TypeError, ValueError):
                engine_id = (room.lobby_to_engine_id or {}).get(str(campus_id))
            return next((p for p in room.game.players if p.player_id == engine_id), None)
        if any(role.name == "Educator" for role in requester.roles):
            return requester
        return next(
            (
                player for player in room.game.players
                if any(role.name == "Educator" for role in player.roles)
            ),
            None,
        )

    def _engine_player_for_lobby(self, room, lobby_player_id: str) -> Player | None:
        engine_pid = (room.lobby_to_engine_id or {}).get(lobby_player_id)
        if engine_pid is None:
            return None
        return next(
            (player for player in room.game.players if player.player_id == engine_pid),
            None,
        )

    async def _handle_buy_out_float(
        self,
        room_id: str,
        lobby_player_id: str,
        msg: dict,
        websocket,
    ) -> None:
        """The controlling owner buys unissued shares of their own island.

        This is a primary issuance: investor personal cash becomes island
        treasury cash. Message: {shares:int}.
        """
        room = self.rooms.get(room_id)
        if not room or not room.game:
            await websocket.send_text(json.dumps({"type": "error", "message": "Room not found"}))
            return
        engine_pid = (room.lobby_to_engine_id or {}).get(lobby_player_id)
        if engine_pid is None:
            await websocket.send_text(json.dumps({"type": "error", "message": "Player not in game"}))
            return
        player = next((p for p in room.game.players if p.player_id == engine_pid), None)
        if player is None or player.cap_table is None:
            await websocket.send_text(json.dumps({"type": "error", "message": "No island to buy into"}))
            return

        owner_key = str(player.player_id)
        # Only the controlling owner may buy their island's float.
        if player.cap_table.held_by(owner_key) < AUCTIONED_SHARES:
            await websocket.send_text(json.dumps({
                "type": "error", "message": "Only the controlling owner can buy unissued shares."
            }))
            return

        try:
            shares = int(msg.get("shares", 0))
        except (TypeError, ValueError):
            shares = 0
        available = player.cap_table.unissued()
        shares = min(max(0, shares), available)
        if shares <= 0:
            await websocket.send_text(json.dumps({
                "type": "error", "message": "No unissued shares to buy."
            }))
            return

        # Live fair value per share (= liquidation value incl. shareholder
        # loans, fed through the going-concern premium).
        prices = room.game.market.current_prices()
        cyi = getattr(room, "current_year_index", 0)
        csi = getattr(room, "current_season_index", 0)
        tick = cyi * len(SEASONS) + csi
        liq = player.total_wealth(prices, room.game.loan_ledger, CAPITAL_CATALOGUE, tick)
        price = share_price(fair_value(liq, player.wealth_history))
        cost = round(shares * price, 1)
        if player.personal_cash < cost:
            await websocket.send_text(json.dumps({
                "type": "error",
                "message": f"Need {cost:.1f} Dp for {shares} share(s); you have "
                           f"{player.personal_cash:.1f} Dp.",
            }))
            return

        # Execute primary issuance: personal cash becomes island treasury cash;
        # shares move unissued -> owner; holdings mirror the cap table.
        total_liquid = round(player.personal_cash + player.dollops, 1)
        player.personal_cash = round(player.personal_cash - cost, 1)
        player.dollops = round(total_liquid - player.personal_cash, 1)
        player.cap_table.transfer(UNISSUED_HOLDER, owner_key, shares)
        player.holdings[owner_key] = player.holdings.get(owner_key, 0) + shares

        await websocket.send_text(json.dumps({
            "type": "buy_out_float_ack", "shares": shares,
            "cost": cost, "price_per_share": round(price, 2),
        }))
        state = self.get_game_state(room_id, lobby_player_id)
        if state:
            await websocket.send_text(json.dumps(state))

    async def _handle_capital_order(
        self,
        room_id: str,
        lobby_player_id: str,
        msg: dict,
        websocket,
    ) -> None:
        """Create a manufacturer-review capital order negotiation (#185)."""
        from ..models.capacity import find_item

        async def _err(message: str) -> None:
            await websocket.send_text(json.dumps({"type": "error", "message": message}))

        room = self.rooms.get(room_id)
        if not room or not room.game:
            await _err("Room not found"); return
        engine_pid = (room.lobby_to_engine_id or {}).get(lobby_player_id)
        if engine_pid is None:
            await _err("Player not in game"); return
        game = room.game
        buyer = next((p for p in game.players if p.player_id == engine_pid), None)
        if buyer is None:
            await _err("Player not found"); return
        item = find_item(CAPITAL_CATALOGUE, str(msg.get("item_id", "")))
        if item is None:
            await _err("Unknown capital item"); return

        # Parse order conditions defensively.
        try:
            term = max(0, min(5, int(msg.get("maintenance_term_years", 0))))
            spares_kits = max(0, int(msg.get("spares_kits", 0)))
        except (TypeError, ValueError):
            term, spares_kits = 0, 0
        predictive = bool(msg.get("predictive_maintenance", False))
        expedited = bool(msg.get("expedited_eligible", False))
        financing = bool(msg.get("financing", False))

        cash_only = bool(item.effects.get("cash_only", False))
        manufacturer = buyer if cash_only else None
        manufactured_resource = None
        if not cash_only:
            manufacturer = next(
                (p for p in game.players if any(r.name == "Manufacturer" for r in p.roles)),
                None,
            )
            if manufacturer is None:
                await _err("No Manufacturing island is available to build capital equipment."); return
            manufactured_resource = game.turn_manager._manufactured_resource_for_capital_item(item)
            if manufacturer.inventory.get(manufactured_resource) <= 0:
                await _err(
                    f"{manufacturer.name} has no {manufactured_resource.value} to build {item.name}."
                ); return

        from ..models.player import maintenance_contract_cost
        contract_cost = maintenance_contract_cost(item.cost, term, predictive)
        spares_cost = round(0.15 * item.cost * spares_kits, 2)
        recommended_total = round(item.cost + contract_cost + spares_cost, 2)
        try:
            buyer_offer = round(float(msg.get("buyer_offer", recommended_total)), 2)
        except (TypeError, ValueError):
            buyer_offer = recommended_total
        if buyer_offer <= 0:
            await _err("Offer total must be positive."); return

        if not getattr(game, "capital_negotiations", None):
            game.capital_negotiations = CapitalNegotiationLedger()
        negotiation = game.capital_negotiations.create(
            buyer_id=buyer.player_id,
            manufacturer_id=manufacturer.player_id,
            item_id=item.item_id,
            maintenance_term_years=term,
            predictive_maintenance=predictive,
            spares_kits=spares_kits,
            expedited_eligible=expedited,
            financing=financing,
            list_price=item.cost,
            recommended_total=recommended_total,
            buyer_offer=buyer_offer,
        )

        # Self-build: the Manufacturer is its own buyer (it ordered equipment it
        # manufactures, or a cash_only item with no separate manufacturer).  There
        # is no counterparty to review the order, so settle it immediately instead
        # of parking a negotiation that awaits the manufacturer's own response.
        # Such a record can be neither meaningfully accepted (an offer from
        # yourself) nor declined, so it jams the awaiting queue and blocks every
        # later order.  Settlement consumes the manufactured unit / cash as usual;
        # no referral or financing applies when buyer == manufacturer.
        if manufacturer.player_id == buyer.player_id:
            try:
                settlement = self._settle_capital_negotiation(
                    room, negotiation, negotiation.buyer_offer
                )
            except (CapitalFinanceError, ValueError) as exc:
                await _err(str(exc)); return
            await websocket.send_text(json.dumps({
                **settlement,
                "negotiation_id": negotiation.negotiation_id,
            }))
            state = self.get_game_state(room_id, lobby_player_id)
            if state:
                await websocket.send_text(json.dumps(state))
            return

        await websocket.send_text(json.dumps({
            "type": "capital_negotiation_ack",
            "result": "proposed",
            "negotiation_id": negotiation.negotiation_id,
            "negotiation": self._capital_negotiation_payload(
                negotiation, game, buyer.player_id
            ),
        }))
        state = self.get_game_state(room_id, lobby_player_id)
        if state:
            await websocket.send_text(json.dumps(state))
        if manufacturer.is_human:
            self._send_capital_negotiation_push(
                room,
                manufacturer.player_id,
                "proposed",
                negotiation,
                from_name=buyer.name,
            )
        else:
            await self._auto_respond_capital_negotiation(
                room_id, lobby_player_id, negotiation, websocket
            )

    async def _handle_capital_negotiation_respond(
        self,
        room_id: str,
        lobby_player_id: str,
        msg: dict,
        websocket,
    ) -> None:
        await self._handle_capital_negotiation_action(
            room_id, lobby_player_id, msg, websocket, actor_role="manufacturer"
        )

    async def _handle_capital_negotiation_accept(
        self,
        room_id: str,
        lobby_player_id: str,
        msg: dict,
        websocket,
    ) -> None:
        await self._handle_capital_negotiation_action(
            room_id, lobby_player_id, msg, websocket, actor_role="buyer"
        )

    async def _handle_capital_negotiation_action(
        self,
        room_id: str,
        lobby_player_id: str,
        msg: dict,
        websocket,
        *,
        actor_role: str,
    ) -> None:
        async def _err(message: str) -> None:
            await websocket.send_text(json.dumps({"type": "error", "message": message}))

        room = self.rooms.get(room_id)
        if not room or not room.game:
            await _err("Room not found"); return
        actor = self._engine_player_for_lobby(room, lobby_player_id)
        if actor is None:
            await _err("Player not in game"); return
        try:
            negotiation_id = int(msg.get("negotiation_id"))
        except (TypeError, ValueError):
            await _err("Invalid negotiation_id"); return
        ledger = getattr(room.game, "capital_negotiations", None)
        negotiation = ledger.get(negotiation_id) if ledger else None
        if negotiation is None:
            await _err(f"Capital negotiation #{negotiation_id} not found"); return
        if negotiation.awaiting_id != actor.player_id:
            await _err(
                f"Capital negotiation #{negotiation_id} is not awaiting your response"
            ); return

        action = str(msg.get("action", "")).strip().lower()
        if actor_role == "buyer":
            action = "accept"
            if actor.player_id != negotiation.buyer_id:
                await _err("Only the buyer can accept this counter-offer."); return
            if negotiation.status != CapitalNegotiationStatus.COUNTERED:
                await _err("Only countered capital orders can be buyer-accepted."); return
        elif actor.player_id != negotiation.manufacturer_id:
            await _err("Only the Manufacturer can respond to this capital order."); return

        try:
            if action == "accept":
                total = (
                    negotiation.counter_total
                    if negotiation.status == CapitalNegotiationStatus.COUNTERED
                    else negotiation.buyer_offer
                )
                settlement = self._settle_capital_negotiation(
                    room, negotiation, float(total)
                )
                result = "accepted"
            elif action == "counter":
                if negotiation.status != CapitalNegotiationStatus.PROPOSED:
                    raise ValueError("Only proposed capital orders can be countered.")
                counter_total = round(float(msg.get("counter_total")), 2)
                if counter_total <= 0:
                    raise ValueError("Counter total must be positive.")
                negotiation.counter_total = counter_total
                negotiation.status = CapitalNegotiationStatus.COUNTERED
                negotiation.awaiting_id = negotiation.buyer_id
                settlement = None
                result = "countered"
            elif action == "decline":
                if negotiation.status != CapitalNegotiationStatus.PROPOSED:
                    raise ValueError("Only proposed capital orders can be declined.")
                negotiation.status = CapitalNegotiationStatus.DECLINED
                negotiation.awaiting_id = None
                settlement = None
                result = "declined"
            else:
                await _err(f"Unknown capital negotiation action: {action!r}"); return
        except (CapitalFinanceError, ValueError) as exc:
            await _err(str(exc)); return

        payload = self._capital_negotiation_payload(
            negotiation, room.game, actor.player_id
        )
        ack = {
            "type": "capital_negotiation_ack",
            "result": result,
            "negotiation_id": negotiation.negotiation_id,
            "negotiation": payload,
        }
        if settlement:
            ack.update(settlement)
        await websocket.send_text(json.dumps(ack))
        state = self.get_game_state(room_id, lobby_player_id)
        if state:
            await websocket.send_text(json.dumps(state))

        notify_id = (
            negotiation.buyer_id
            if actor.player_id == negotiation.manufacturer_id
            else negotiation.manufacturer_id
        )
        self._send_capital_negotiation_push(
            room, notify_id, result, negotiation, from_name=actor.name,
            settlement=settlement,
        )

    async def _auto_respond_capital_negotiation(
        self,
        room_id: str,
        lobby_player_id: str,
        negotiation: CapitalOrderNegotiation,
        websocket,
    ) -> None:
        room = self.rooms.get(room_id)
        if not room or not room.game:
            return
        if negotiation.buyer_offer >= negotiation.recommended_total:
            try:
                settlement = self._settle_capital_negotiation(
                    room, negotiation, negotiation.buyer_offer
                )
            except (CapitalFinanceError, ValueError) as exc:
                await websocket.send_text(json.dumps({"type": "error", "message": str(exc)}))
                return
            result = "accepted"
        else:
            negotiation.counter_total = negotiation.recommended_total
            negotiation.status = CapitalNegotiationStatus.COUNTERED
            negotiation.awaiting_id = negotiation.buyer_id
            settlement = None
            result = "countered"
        await websocket.send_text(json.dumps({
            "type": "capital_negotiation_ack",
            "result": result,
            "negotiation_id": negotiation.negotiation_id,
            "negotiation": self._capital_negotiation_payload(
                negotiation, room.game, negotiation.buyer_id
            ),
            **(settlement or {}),
        }))
        state = self.get_game_state(room_id, lobby_player_id)
        if state:
            await websocket.send_text(json.dumps(state))

    def _settle_capital_negotiation(
        self,
        room,
        negotiation: CapitalOrderNegotiation,
        agreed_total: float,
    ) -> dict:
        from ..models.capacity import find_item
        from ..models.player import maintenance_contract_cost

        if negotiation.status not in ACTIVE_CAPITAL_NEGOTIATION_STATUSES:
            raise ValueError(
                f"Capital negotiation #{negotiation.negotiation_id} is already "
                f"{negotiation.status.value}"
            )
        game = room.game
        buyer = next((p for p in game.players if p.player_id == negotiation.buyer_id), None)
        manufacturer = next(
            (p for p in game.players if p.player_id == negotiation.manufacturer_id),
            None,
        )
        if buyer is None or manufacturer is None:
            negotiation.status = CapitalNegotiationStatus.EXPIRED
            negotiation.awaiting_id = None
            raise ValueError("Capital negotiation party no longer exists.")
        item = find_item(CAPITAL_CATALOGUE, negotiation.item_id)
        if item is None:
            negotiation.status = CapitalNegotiationStatus.EXPIRED
            negotiation.awaiting_id = None
            raise ValueError("Capital item no longer exists.")

        cash_only = bool(item.effects.get("cash_only", False))
        manufactured_resource = None
        if not cash_only:
            manufactured_resource = game.turn_manager._manufactured_resource_for_capital_item(item)
            if manufacturer.inventory.get(manufactured_resource) <= 0:
                raise ValueError(
                    f"{manufacturer.name} has no {manufactured_resource.value} to build {item.name}."
                )
        agreed_total = round(float(agreed_total), 2)
        if agreed_total <= 0:
            raise ValueError("Agreed total must be positive.")
        pays = cash_only or manufacturer.player_id != buyer.player_id
        cyi = getattr(room, "current_year_index", 0)
        csi = getattr(room, "current_season_index", 0)
        current_tick = cyi * len(SEASONS) + csi

        loan = None
        financed = False
        referral_fee = 0.0
        if pays:
            want_finance = (
                negotiation.financing
                and game.turn_manager._find_banker() is not None
            )
            if want_finance:
                loan_term = (
                    min(3, max(1, negotiation.maintenance_term_years))
                    if negotiation.maintenance_term_years else 2
                )
                try:
                    loan = game.turn_manager.issue_capital_finance_loan(
                        buyer, agreed_total, loan_term, cyi, csi
                    )
                    financed = True
                except CapitalFinanceError as exc:
                    if buyer.dollops < agreed_total:
                        raise CapitalFinanceError(str(exc))
            if not financed and buyer.dollops < agreed_total:
                raise ValueError(
                    f"Need {agreed_total:.1f} Dp for this order; you have "
                    f"{buyer.dollops:.1f} Dp."
                )

        if not cash_only:
            manufacturer.give_resources(manufactured_resource, 1)
        if pays:
            buyer.spend_dollops(agreed_total)
            if manufacturer.player_id != buyer.player_id:
                manufacturer.receive_dollops(agreed_total)
            if financed:
                banker = game.turn_manager._find_banker()
                fee = round(MANUFACTURER_FINANCE_REFERRAL_RATE * agreed_total, 2)
                if (banker is not None
                        and banker.player_id != manufacturer.player_id
                        and banker.dollops >= fee):
                    banker.spend_dollops(fee)
                    manufacturer.receive_dollops(fee)
                    referral_fee = fee

        contract_cost = maintenance_contract_cost(
            item.cost,
            negotiation.maintenance_term_years,
            negotiation.predictive_maintenance,
        )
        order = {
            "maintenance_term_years": negotiation.maintenance_term_years,
            "predictive_maintenance": negotiation.predictive_maintenance,
            "guarantee_seasons": 1,
            "warranty": negotiation.maintenance_term_years > 0,
            "spares_kits": negotiation.spares_kits,
            "expedited_eligible": negotiation.expedited_eligible,
            "financing": negotiation.financing,
            "purchase_value": item.cost,
        }
        arrives_at = buyer.place_capital_order(
            item.item_id, order, current_tick, item.delivery_seasons
        )
        negotiation.status = CapitalNegotiationStatus.ACCEPTED
        negotiation.awaiting_id = None
        return {
            "type": "capital_order_ack",
            "item_id": item.item_id,
            "name": item.name,
            "upfront": agreed_total,
            "agreed_total": agreed_total,
            "contract_cost": contract_cost,
            "spares_kits": negotiation.spares_kits,
            "financing": negotiation.financing,
            "financed": financed,
            "loan_id": loan.loan_id if loan is not None else None,
            "loan_repayment": loan.repayment_amount if loan is not None else None,
            "referral_fee": referral_fee,
            "arrives_at_tick": arrives_at,
        }

    def _capital_negotiation_payload(
        self,
        negotiation: CapitalOrderNegotiation,
        game: Game,
        viewer_id: int | None,
    ) -> dict:
        from ..models.capacity import find_item

        item = find_item(CAPITAL_CATALOGUE, negotiation.item_id)
        player_names = {p.player_id: p.name for p in game.players}
        return {
            "negotiation_id": negotiation.negotiation_id,
            "status": negotiation.status.value,
            "buyer_id": negotiation.buyer_id,
            "buyer_name": player_names.get(negotiation.buyer_id),
            "manufacturer_id": negotiation.manufacturer_id,
            "manufacturer_name": player_names.get(negotiation.manufacturer_id),
            "counterparty_id": (
                negotiation.manufacturer_id
                if viewer_id == negotiation.buyer_id else negotiation.buyer_id
            ),
            "awaiting_id": negotiation.awaiting_id,
            "awaiting_name": (
                player_names.get(negotiation.awaiting_id)
                if negotiation.awaiting_id is not None else None
            ),
            "item_id": negotiation.item_id,
            "name": item.name if item else negotiation.item_id,
            "maintenance_term_years": negotiation.maintenance_term_years,
            "predictive_maintenance": negotiation.predictive_maintenance,
            "spares_kits": negotiation.spares_kits,
            "expedited_eligible": negotiation.expedited_eligible,
            "financing": negotiation.financing,
            "list_price": negotiation.list_price,
            "recommended_total": negotiation.recommended_total,
            "buyer_offer": negotiation.buyer_offer,
            "counter_total": negotiation.counter_total,
        }

    def _capital_negotiation_state_for_viewer(
        self,
        game: Game,
        viewer_engine_id: int | None,
    ) -> tuple[list[dict], list[dict]]:
        if viewer_engine_id is None:
            return [], []
        ledger = getattr(game, "capital_negotiations", None)
        if ledger is None:
            return [], []
        awaiting = [
            self._capital_negotiation_payload(negotiation, game, viewer_engine_id)
            for negotiation in ledger.awaiting(viewer_engine_id)
        ]
        mine = [
            self._capital_negotiation_payload(negotiation, game, viewer_engine_id)
            for negotiation in ledger.for_player(viewer_engine_id)
        ]
        return awaiting, mine

    def _send_capital_negotiation_push(
        self,
        room,
        engine_player_id: int,
        result: str,
        negotiation: CapitalOrderNegotiation,
        *,
        from_name: str,
        settlement: dict | None = None,
    ) -> None:
        lobby_id = self._deal_lobby_id_for_engine_id(room, engine_player_id)
        if not lobby_id:
            return
        payload = {
            "type": "capital_negotiation",
            "result": result,
            "negotiation_id": negotiation.negotiation_id,
            "from": from_name,
            "negotiation": self._capital_negotiation_payload(
                negotiation, room.game, engine_player_id
            ),
        }
        if settlement:
            payload.update({
                key: value for key, value in settlement.items()
                if key != "type"
            })
        self._thread_safe_send(room.room_id, lobby_id, payload)
        self._thread_safe_send(
            room.room_id,
            lobby_id,
            self.get_game_state(room.room_id, lobby_id) or {},
        )

    async def _handle_capital_repair(
        self,
        room_id: str,
        lobby_player_id: str,
        msg: dict,
        websocket,
    ) -> None:
        async def _ack(ok: bool, message: str, **extra) -> None:
            await websocket.send_text(json.dumps({
                "type": "capital_repair_ack",
                "ok": ok,
                "message": message,
                **extra,
            }))

        room = self.rooms.get(room_id)
        if not room or not room.game or room.status != "running":
            await _ack(False, "Game is not running.")
            return
        player = self._engine_player_for_lobby(room, lobby_player_id)
        if player is None:
            await _ack(False, "Player not in game.")
            return
        game = room.game
        item_id = str(msg.get("item_id", "")).strip()
        item = find_item(CAPITAL_CATALOGUE, item_id)
        if item is None:
            await _ack(False, "Unknown capital item.")
            return

        queued = game._repair_in_progress_count(player, item_id)
        failed_units = [
            u for u in player.capital_units.get(item_id, [])
            if u.status == "failed"
        ]
        unit = failed_units[queued] if queued < len(failed_units) else None
        if unit is None:
            await _ack(False, f"No failed {item.name} unit is awaiting repair.")
            return

        cyi = getattr(room, "current_year_index", 0)
        csi = getattr(room, "current_season_index", 0)
        current_tick = cyi * len(SEASONS) + csi
        repaired = game._attempt_capital_repair(
            player, item, current_tick, unit=unit
        )
        if not repaired:
            await _ack(
                False,
                f"Repair needs enough Dollops and Freight for {item.name}.",
            )
            return

        await _ack(True, f"Repair started for {item.name}.", item_id=item_id)
        state = self.get_game_state(room_id, lobby_player_id)
        if state:
            await websocket.send_text(json.dumps(state))

    def _leases_detail_for_player(
        self,
        game: Game,
        player_id: int,
        current_year_idx: int,
        current_season_idx: int,
    ) -> list[dict]:
        from ..models.capacity import find_item
        leases = getattr(game, "lease_ledger", None)
        if not leases:
            return []
        details = []
        for lease in leases.active_leases_for(player_id):
            item = find_item(CAPITAL_CATALOGUE, lease.item_id)
            role = "lessee" if lease.lessee_id == player_id else "lessor"
            if lease.status.value == "awaiting_buyout":
                next_year = lease.maturity_year
                next_season = 0
                payment_type = "buyout"
            else:
                next_year = max(current_year_idx, lease.last_payment_year + 1)
                next_season = 0
                payment_type = "annual"
            seasons_to_next = max(
                0,
                (next_year - current_year_idx) * len(SEASONS)
                + (next_season - current_season_idx),
            )
            details.append({
                "lease_id": lease.lease_id,
                "item_id": lease.item_id,
                "item_name": item.name if item else lease.item_id,
                "role": role,
                "counterparty_id": lease.lessor_id if role == "lessee" else lease.lessee_id,
                "annual_payment": round(lease.annual_payment, 1),
                "buyout_payment": round(lease.buyout_payment, 1),
                "payments_made": lease.payments_made,
                "term_years": lease.term_years,
                "seasons_to_next_payment": seasons_to_next,
                "status": lease.status.value,
                "next_payment_year": next_year + 1,
                "next_payment_season": SEASONS[next_season],
                "next_payment_type": payment_type,
            })
        return details

    def _decision_hints_for_player(self, pd: dict) -> list[dict]:
        hints: list[dict] = []
        capacity = pd.get("capacity", {})
        for output in capacity.get("outputs", []):
            inputs_short = output.get("inputs_short") or {}
            if inputs_short:
                resource = next(iter(inputs_short))
                hints.append({
                    "tone": "blocked",
                    "title": f"Unblock {output.get('output')}",
                    "why": f"{resource} is limiting this production line.",
                    "text": f"{resource} is limiting this production line.",
                    "target": {
                        "type": "resource_shortfall",
                        "resource": resource,
                    },
                })
                continue

            equipment_options = (output.get("equipment_short") or {}).get("options") or []
            if equipment_options:
                item = equipment_options[0]
                hints.append({
                    "tone": "blocked",
                    "title": f"Expand {output.get('output')}",
                    "why": f"{item.get('name')} would increase this line's capacity.",
                    "text": f"{item.get('name')} would increase this line's capacity.",
                    "target": {
                        "type": "equipment_shortfall",
                        "capital_item": item.get("item_id"),
                    },
                })
                continue

            workforce_short = output.get("workforce_short") or {}
            if workforce_short:
                profession = next(iter(workforce_short))
                hints.append({
                    "tone": "blocked",
                    "title": f"Train for {output.get('output')}",
                    "why": f"{profession} is the tight workforce constraint.",
                    "text": f"{profession} is the tight workforce constraint.",
                    "target": {
                        "type": "workforce_shortfall",
                        "profession": profession,
                    },
                })

        for loan in pd.get("loans_detail", []):
            target_type = "loan_due" if loan.get("role") == "borrower" else "loan_offer"
            hints.append({
                "tone": "watch",
                "title": "Review loan position",
                "why": "There is an active loan to monitor.",
                "text": "There is an active loan to monitor.",
                "target": {
                    "type": target_type,
                    "loan_id": loan.get("loan_id"),
                },
            })
            break

        for policy in pd.get("policies_detail", []):
            hints.append({
                "tone": "watch",
                "title": "Review insurance",
                "why": "There is an active insurance policy to monitor.",
                "text": "There is an active insurance policy to monitor.",
                "target": {
                    "type": "insurance_review",
                    "policy_id": policy.get("policy_id"),
                },
            })
            break

        return hints

    def get_game_state(self, room_id: str, player_id: str | None = None) -> dict | None:
        room = self.rooms.get(room_id)
        if not room or not room.game:
            return None
        game = room.game
        prices = game.market.current_prices()

        # Reverse map engine player_id (int) → lobby player_id (string)
        engine_to_lobby = {
            ep: lp for lp, ep in (room.lobby_to_engine_id or {}).items()
        }
        current_year_idx = getattr(room, "current_year_index", 0)
        current_season_idx = getattr(room, "current_season_index", 0)
        current_tick = current_year_idx * len(SEASONS) + current_season_idx
        player_names = {p.player_id: p.name for p in game.players}
        event_results = getattr(game, "_last_event_results", {}) or {}
        flu_strain_loss = max(
            (getattr(event, "flu_strain_loss", 0.0) for event in event_results.values()),
            default=0.0,
        )
        viewer_engine_id = (
            (room.lobby_to_engine_id or {}).get(player_id)
            if player_id is not None else None
        )

        # --- Equity (Phase 2b): per-island share price + investor net worth ---
        # liquidation value (= total_wealth, already net of bank + shareholder
        # loans) feeds fair_value; share_price drives net-worth scoring.
        share_price_by_island: dict[str, float] = {}
        island_loan_books = [p.shareholder_loans for p in game.players]
        for _p in game.players:
            _liq = _p.total_wealth(prices, game.loan_ledger, CAPITAL_CATALOGUE, current_tick)
            share_price_by_island[str(_p.player_id)] = share_price(
                fair_value(_liq, _p.wealth_history)
            )

        def banker_loan_book_status(player: Player) -> dict[str, int]:
            if not any(role.name == "Banker" for role in player.roles):
                return {"active": 0, "cap": 0}
            n_bankers = player.workforce.count_profession(Profession.BANKER.value)
            cap = max(1, 2 * n_bankers)
            active = sum(
                1 for loan in game.loan_ledger.loans
                if loan.lender_id == player.player_id
                and loan.status == LoanStatus.ACTIVE
            )
            return {"active": active, "cap": cap}

        players_data = []
        for p in game.players:
            loan_book = banker_loan_book_status(p)
            training_targets = self._training_targets_for_player(game, p.player_id)
            training_options = self._training_options_for_player(
                game, p, current_year_idx, current_season_idx
            )
            pd = {
                "player_id": p.player_id,
                "lobby_player_id": engine_to_lobby.get(p.player_id),
                "name": p.name,
                "roles": p.role_names(),
                "role_names": [r.name for r in p.roles],
                "dollops": round(p.dollops, 1),
                # --- Equity (Phase 2b): two balance sheets + ownership ---
                "treasury": round(p.dollops, 1),          # island operating cash (alias of dollops)
                "personal_cash": round(p.personal_cash, 1),  # investor wallet
                "household_cash": round(p.household_cash, 1),
                "net_worth": round(
                    p.net_worth(
                        share_price_by_island,
                        sh_loans.receivable(island_loan_books, str(p.player_id)),
                    ),
                    1,
                ),
                "owns_pct": round(
                    p.cap_table.fraction(str(p.player_id)) * 100, 1
                ) if p.cap_table else None,
                "unissued_pct": round(
                    (p.cap_table.unissued() / 100) * 100, 1
                ) if p.cap_table else None,
                "unissued_shares": p.cap_table.unissued() if p.cap_table else 0,
                "share_price": round(share_price_by_island.get(str(p.player_id), 0.0), 2),
                "shareholder_loan_owed": round(sh_loans.total_owed(p.shareholder_loans), 1),
                "shareholder_loan_receivable": round(
                    sh_loans.receivable(island_loan_books, str(p.player_id)), 1
                ),
                "wealth": round(
                    p.total_wealth(prices, game.loan_ledger, CAPITAL_CATALOGUE, current_tick),
                    1,
                ),
                # Signed decomposition of the win-condition score (P7 / #86).
                # Components sum to ``wealth``; lets the dashboard render a
                # "why is my net worth X?" panel without re-deriving the math.
                "wealth_breakdown": {
                    k: round(v, 1)
                    for k, v in p.wealth_breakdown(
                        prices, game.loan_ledger, CAPITAL_CATALOGUE, current_tick
                    )["components"].items()
                },
                "revenue_opportunities": revenue_opportunities(
                    p,
                    game.market,
                    game.players,
                    getattr(game, "season", SEASONS[current_season_idx]),
                ),
                "equipment_value": round(p.capital_book_value(CAPITAL_CATALOGUE, current_tick), 1),
                "loans_outstanding": round(game.loan_ledger.outstanding_debt(p.player_id), 1),
                "loans_receivable": round(game.loan_ledger.loans_receivable(p.player_id), 1),
                "banker_active_loans": loan_book["active"],
                "banker_active_loan_cap": loan_book["cap"],
                "spares_held": p.inventory.get(ResourceType.SPARES),
                "spares_capacity": p.spares_capacity(),
                # Structured per-loan detail (Issue #6 — Loan rollover UI).
                # Includes both borrower-side and lender-side active loans
                # so the dashboard can show roles consistently.
                "loans_detail": [
                    {
                        "loan_id": l.loan_id,
                        "role": "borrower" if l.borrower_id == p.player_id else "lender",
                        "principal": round(l.principal, 1),
                        "interest_rate": l.interest_rate,
                        "repayment_amount": round(l.repayment_amount, 1),
                        "term_years": l.term_years,
                        "secured": l.secured,
                        "collateral_item_id": l.collateral_item_id,
                        "issued_year": l.issued_year + 1,
                        "issued_season": SEASONS[l.issued_season]
                            if l.issued_season < len(SEASONS) else str(l.issued_season),
                        "maturity_year": l.maturity_year + 1,
                        "maturity_season": SEASONS[l.maturity_season]
                            if l.maturity_season < len(SEASONS) else str(l.maturity_season),
                        "seasons_to_maturity": max(0,
                            (l.maturity_year - current_year_idx) * len(SEASONS)
                            + (l.maturity_season - current_season_idx)),
                        "counterparty_id": l.lender_id
                            if l.borrower_id == p.player_id else l.borrower_id,
                    }
                    for l in game.loan_ledger.active_loans_for(p.player_id)
                ],
                "leases_detail": self._leases_detail_for_player(
                    game, p.player_id, current_year_idx, current_season_idx
                ),
                "workforce_count": p.workforce.count,
                "workforce_active": len(p.workforce.active_workers),
                "workforce_bands": p.workforce.band_summary(),
                "workforce_training_bands": p.workforce.training_band_summary(
                    training_targets
                ),
                "workforce_professions": p.workforce.profession_summary(
                    training_targets
                ),
                "training_pipeline": self._training_pipeline_for_player(
                    game,
                    p.player_id,
                    player_names,
                    current_year_idx,
                    current_season_idx,
                ),
                # Read-only menu for the Training Desk batch dialog (#158).
                "training_options": training_options,
                "training_queue_order": self._training_queue_order_for_player(
                    game,
                    p.player_id,
                    player_names,
                ),
                "training_decisions": self._training_decisions_for_player(
                    game,
                    p.player_id,
                    current_year_idx,
                    current_season_idx,
                ),
                "training_capacity": self._training_capacity_for_player(
                    game,
                    current_year_idx,
                    current_season_idx,
                ),
                "staffing_contracts": self._staffing_contracts_for_player(
                    game, p.player_id, player_names, current_year_idx, current_season_idx,
                ),
                "workforce_efficiency": round(p.workforce.average_efficiency * 100),
                "production_capacity": round(p.production_capacity * 100),
                "population": p.population,
                "qol_score": round(getattr(p, "_qol_score", 0.0), 3),
                "food_coverage": round(getattr(p, "_food_coverage", 0.0), 3),
                "health_coverage": round(getattr(p, "_health_coverage", 0.0), 3),
                "pollution_index": round(getattr(p, "_pollution_index", 0.0), 3),
                "flu_strain_loss": round(
                    getattr(event_results.get(p.player_id), "flu_strain_loss", 0.0),
                    4,
                ),
                "flu_doses_needed": getattr(
                    event_results.get(p.player_id), "flu_doses_needed", 0
                ),
                "flu_doses_administered": getattr(
                    event_results.get(p.player_id), "flu_doses_administered", 0
                ),
                "flu_effective_loss": round(
                    getattr(event_results.get(p.player_id), "flu_effective_loss", 0.0),
                    4,
                ),
                "campus_load": (
                    game.training.visiting_trainees(p.player_id)
                    if any(r.name == "Educator" for r in p.roles) else 0
                ),
                "visiting_staff_count": (
                    getattr(game, "staffing", None) and
                    getattr(game, "staffing").visiting_staff(p.player_id) or 0
                ),
                # Plain descriptive strings for back-compat with older UI code
                "policies": [
                    pol.describe() for pol in p.insurance_policies if pol.active
                ],
                # Structured per-policy detail (Issue #5 — Insurance review UI)
                "policies_detail": [
                    {
                        "policy_id": pol.policy_id,
                        "policy_type": pol.policy_type,
                        "premium_paid": round(pol.premium_paid, 1),
                        "purchased_tick": pol.purchased_tick,
                        "expires_at_tick": pol.expires_at_tick,
                        "expires_year": pol.expires_at_tick // len(SEASONS) + 1,
                        "expires_season": SEASONS[pol.expires_at_tick % len(SEASONS)]
                            if (pol.expires_at_tick % len(SEASONS)) < len(SEASONS)
                            else "",
                        "seasons_remaining":
                            pol.seasons_remaining(current_year_idx, current_season_idx),
                        "cancel_refund":
                            pol.cancel_refund(current_year_idx, current_season_idx),
                        "banker_player_id": pol.banker_player_id,
                    }
                    for pol in p.insurance_policies if pol.active
                ],
            }
            # Inventory is public information for every seat — including AI
            # islands, so the Trade Finder can surface them as trading
            # partners (UI v2 phase 1, #114). Previously inventory was
            # omitted when the *requester* was an AI seat. `is_ai` flags the
            # seat itself so the UI can badge AI islands.
            seat_lp = next(
                (lp for lp in room.players
                 if lp.player_id == engine_to_lobby.get(p.player_id)),
                None
            )
            pd["is_ai"] = bool(seat_lp and not seat_lp.is_human)
            # Expose the human flag too — chat (new-chat island picker), roster
            # cards, etc. filter on `is_human`, which the in-game payload was
            # missing (only `is_ai` was set), so they saw no human islands.
            pd["is_human"] = not pd["is_ai"]
            pd["inventory"] = {
                r.value: p.inventory.get(r)
                for r in ResourceType if p.inventory.get(r) > 0
            }
            # Production capacity panel + constraint data
            pd["capacity"] = self._player_capacity(
                p,
                current_tick=current_tick,
                season_name=getattr(game, "season", SEASONS[current_season_idx]),
            )
            pd["decision_hints"] = self._decision_hints_for_player(pd)
            players_data.append(pd)

        mkt_summary = game.market.market_summary()
        market_data = {}
        for r in ResourceType:
            # Phase D1 Banker service model: Finance is no longer a tradable
            # market commodity, but the enum remains for saved-game/back-compat.
            # Spares (#185/#188) are likewise non-tradable — never market goods.
            if r == ResourceType.FINANCE or r in NON_TRADABLE_RESOURCES:
                continue
            info = mkt_summary.get(r.value, {})
            formula_price = round(game.market.current_price(r), 2)
            ask_price = info.get("ask_price")
            bid_price = info.get("bid_price")
            market_data[r.value] = {
                "bid_price": bid_price,
                "bid_quantity": info.get("bid_quantity", 0),
                "ask_price": ask_price,
                "ask_quantity": info.get("ask_quantity", 0),
                "price": ask_price or formula_price,
                "best_price": ask_price,
                "quantity": info.get("ask_quantity", 0),
                "formula_price": formula_price,
            }

        player_by_id = {p.player_id: p for p in game.players}
        barter_deals = []
        for deal in getattr(game.ledger, "deals", []):
            if deal.status not in ACTIVE_DEAL_STATUSES:
                continue
            proposer = player_by_id.get(deal.proposer_id)
            target = player_by_id.get(deal.target_id)
            warnings = []
            if proposer and deal.offer_resource and deal.offer_qty > 0:
                have = proposer.inventory.get(deal.offer_resource)
                if have < deal.offer_qty:
                    warnings.append(
                        f"{proposer.name} needs {deal.offer_qty - have} more "
                        f"{deal.offer_resource.value}"
                    )
            if target and deal.request_resource and deal.request_qty > 0:
                have = target.inventory.get(deal.request_resource)
                if have < deal.request_qty:
                    warnings.append(
                        f"{target.name} needs {deal.request_qty - have} more "
                        f"{deal.request_resource.value}"
                    )
            if proposer and deal.gold_sweetener > 0 and proposer.dollops < deal.gold_sweetener:
                warnings.append(
                    f"{proposer.name} needs {deal.gold_sweetener - proposer.dollops:.1f} more Dp"
                )
            if target and deal.gold_sweetener < 0 and target.dollops < abs(deal.gold_sweetener):
                warnings.append(
                    f"{target.name} needs {abs(deal.gold_sweetener) - target.dollops:.1f} more Dp"
                )
            barter_deals.append({
                "deal_id": deal.deal_id,
                "from": player_names.get(deal.proposer_id, f"Player {deal.proposer_id}"),
                "to": player_names.get(deal.target_id, f"Player {deal.target_id}"),
                "offer": (
                    f"{deal.offer_qty} {deal.offer_resource.value}"
                    if deal.offer_resource and deal.offer_qty else "Dollops"
                ),
                "request": (
                    f"{deal.request_qty} {deal.request_resource.value}"
                    if deal.request_resource and deal.request_qty else "Dollops"
                ),
                "sweetener": round(deal.gold_sweetener, 1),
                "status": deal.status.value,
                "awaiting_id": deal.awaiting_id,
                "awaiting": player_names.get(
                    deal.awaiting_id, f"Player {deal.awaiting_id}"
                ) if deal.awaiting_id is not None else None,
                "message": deal.message or None,
                "warnings": warnings,
            })
        barter_needs = []
        sustenance_alerts_by_player_id: dict[int, list[dict]] = {}
        for p in game.players:
            needs = []
            for r in p.all_required_inputs():
                if p.inventory.get(r) <= 0:
                    needs.append(r.value)
            campus_food_units = (
                game.training.visiting_trainees(p.player_id)
                * STAFFING_FOOD_PER_STAFF_PER_SEASON
                if any(r.name == "Educator" for r in p.roles) else 0.0
            )
            # Add visiting medical staff to the extra_residents count so
            # the host island's sustenance calculation includes them.
            staffing = getattr(game, "staffing", None)
            if staffing:
                campus_food_units += (
                    staffing.visiting_staff(p.player_id)
                    * STAFFING_FOOD_PER_STAFF_PER_SEASON
                )
            campus_extra = campus_food_units * PEOPLE_PER_MEAL
            # Sustenance basket alert (2026-05-25 model): aggregate the
            # whole basket into a single "meals runway" figure rather
            # than one alert per resource. Inventory is fungible across
            # the basket (Food OR Grain+Produce+(Fish|Meat) with 2:1
            # substitution), so a per-resource runway is misleading.
            meals_per_season = p.meals_needed(extra_residents=campus_extra)
            if meals_per_season > 0:
                meals_on_hand = p.meals_available()
                runway = round(meals_on_hand / meals_per_season, 2)
                if runway < 2:
                    # Context flags so the client can give actionable
                    # advice rather than a blind "buy food" (2026-05-27
                    # Codex Player: "'Meals runway: 0' told me to buy
                    # food, but there was no ask, only bids.  The hint
                    # remained prominent even after I posted a food
                    # bid.").
                    basket = (
                        ResourceType.FOOD, ResourceType.GRAIN,
                        ResourceType.PRODUCE, ResourceType.FISH,
                        ResourceType.MEAT,
                    )
                    market_has_supply = any(
                        game.market.available_offers(r) for r in basket
                    )
                    player_has_pending_bid = any(
                        any(b.buyer_id == p.player_id
                            for b in game.market.available_bids(r))
                        for r in basket
                    )
                    sustenance_alerts_by_player_id.setdefault(p.player_id, []).append({
                        "resource": "Meals",
                        "on_hand": meals_on_hand,
                        "seasonal_need": meals_per_season,
                        "runway_seasons": runway,
                        "recommended_purchase":
                            max(0, meals_per_season * 2 - meals_on_hand),
                        "severity": "danger" if runway < 1 else "warning",
                        # When False, the client should suggest produce /
                        # train Farmer / build Kitchen rather than "buy
                        # food" — there's nothing on the market to buy.
                        "market_has_supply": market_has_supply,
                        # When True, the player already has a resting bid
                        # for a basket resource; the client can soften the
                        # "buy food now" urgency to "waiting on your bid".
                        "player_has_pending_bid": player_has_pending_bid,
                    })
                if meals_on_hand < meals_per_season:
                    needs.append(
                        f"{meals_per_season - meals_on_hand} meal(s) of sustenance "
                        f"(Food OR Grain+Produce+(Fish|Meat))"
                    )
            if any(r.name == "Educator" for r in p.roles):
                pending_tickets = sum(
                    len(req.worker_ids)
                    for req in game.training.pending_for_educator(p.player_id)
                    if getattr(req, "transport_mode", "") == "air_ticket"
                )
                ticket_short = pending_tickets - p.inventory.get(ResourceType.PASSENGER_SEATS)
                if ticket_short > 0:
                    needs.append(f"{ticket_short} PassengerSeats for training travel")
            if needs:
                barter_needs.append({
                    "player": p.name,
                    "roles": p.role_names(),
                    "needs": needs,
                })

        current_year = current_year_idx + 1
        current_season = SEASONS[current_season_idx]
        deals_awaiting_me, my_deals = self._deal_state_for_viewer(
            game, viewer_engine_id, player_names
        )
        capital_negotiations_awaiting_me, my_capital_negotiations = (
            self._capital_negotiation_state_for_viewer(game, viewer_engine_id)
        )
        my_market_orders = (
            game.market.player_orders(viewer_engine_id)
            if viewer_engine_id is not None else {"offers": [], "bids": []}
        )

        return {
            "type": "game_state",
            "room_id": room_id,
            "join_code": room.join_code,
            "room_name": room.name,
            "status": room.status,
            "year": current_year,
            "season": current_season,
            # Authoritative season-timer state so ANY tab (late join, reconnect,
            # mid-season re-render) syncs its countdown to the server clock — not
            # just the one-shot season_start broadcast. server_now lets the client
            # correct for clock offset; season_timer_end is the epoch deadline
            # (0 = no active action-phase timer).
            "season_phase": room.season_phase,
            "server_now": round(time.time(), 3),
            "season_timer_end": (
                round(room.season_timer_end, 3)
                if (room.season_phase == "action" and room.season_timer_end > 0)
                else 0
            ),
            "funding_rates": {
                str(term): round(rate * 100, 2)
                for term, rate in posted_funding_rates(
                    current_year_idx, current_season_idx
                ).items()
            },
            "flu": {
                "season": FLU_SEASON,
                "strain_loss": round(flu_strain_loss, 4),
                "active": flu_strain_loss > 0,
            },
            "players": players_data,
            "sustenance_alerts": {
                str(player_id): alerts
                for player_id, alerts in sustenance_alerts_by_player_id.items()
            },
            "market": market_data,
            "my_market_orders": my_market_orders,
            "barter_market": {"deals": barter_deals, "needs": barter_needs},
            "deals_awaiting_me": deals_awaiting_me,
            "my_deals": my_deals,
            "capital_negotiations_awaiting_me": capital_negotiations_awaiting_me,
            "my_capital_negotiations": my_capital_negotiations,
            # Chat channels visible to this viewer (room + private ones they're
            # in). Powers the spectator read-only panel and player resync — a
            # spectator polls with the watched seat's id, so this surfaces that
            # seat's channels.
            "chat": self._chat_visible_channels(room, player_id),
            "price_history": [
                {"year": s.year, "season": s.season,
                 "prices": {
                     r.value: round(p, 2)
                     for r, p in s.prices.items()
                     if r != ResourceType.FINANCE
                 }}
                for s in game.market.price_history[-8:]
            ],
            # Replay a bounded slice of the ticker so late/reconnecting tabs
            # still see AI turns, which intentionally run before humans.
            "recent_log": list(room.io_adapter._log[-200:]) if room.io_adapter else [],
            "log_count": len(room.io_adapter._log) if room.io_adapter else 0,
        }

    # ---- Thread-safe WebSocket sending ----

    def _thread_safe_send(self, room_id: str, lobby_player_id: str, msg: dict) -> None:
        with self._ws_lock:
            ws = self._ws_connections.get(room_id, {}).get(lobby_player_id)
        if ws and self._loop:
            asyncio.run_coroutine_threadsafe(
                self._async_send(ws, msg), self._loop
            )

    def _thread_safe_broadcast(self, room_id: str, msg: dict) -> None:
        # Snapshot the values inside the lock so the loop iterates an
        # immutable list (asyncio.run_coroutine_threadsafe is fast enough
        # to do outside the lock — we just need the values, not the dict).
        with self._ws_lock:
            connections = list(self._ws_connections.get(room_id, {}).values())
        if self._loop:
            for ws in connections:
                asyncio.run_coroutine_threadsafe(
                    self._async_send(ws, msg), self._loop
                )

    @staticmethod
    async def _async_send(ws, msg: dict) -> None:
        try:
            await ws.send_text(json.dumps(msg))
        except Exception:
            pass

    # ── Chat ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_mentions(text: str, names: set[str]) -> list[str]:
        """Return player names @-mentioned in `text` (case-insensitive match)."""
        if "@" not in text:
            return []
        lower = {n.casefold(): n for n in names}
        found: list[str] = []
        for token in re.findall(r"@([\w'-]+)", text):
            real = lower.get(token.casefold())
            if real and real not in found:
                found.append(real)
        return found

    def _chat_payload(self, room: GameRoom, lp: LobbyPlayer,
                      channel: ChatChannel, text: str) -> dict:
        names = {p.name for p in room.players}
        return {
            "type": "chat",
            "channel_id": channel.channel_id,
            "topic": channel.topic,
            "from": lp.name,
            "from_id": lp.player_id,
            "role": lp.role_names[0] if lp.role_names else "",
            "text": text,
            "ts": time.time(),
            "mentions": self._parse_mentions(text, names),
        }

    def _chat_recipients(self, room: GameRoom, channel: ChatChannel) -> list[str]:
        """Lobby ids that should receive messages on this channel.

        Room channel → every human seat. Private channel → its human
        participants. AI seats are intentionally excluded from WS delivery (the
        agent doesn't read chat yet); spectators receive chat via game_state.
        """
        humans = {p.player_id for p in room.players if p.is_human}
        if channel.is_room:
            return list(humans)
        return [pid for pid in channel.participants if pid in humans]

    def _chat_deliver(self, room: GameRoom, channel: ChatChannel, payload: dict) -> None:
        for lobby_id in self._chat_recipients(room, channel):
            self._thread_safe_send(room.room_id, lobby_id, payload)

    def _chat_visible_channels(self, room: GameRoom, viewer_lobby_id: str | None) -> list[dict]:
        """Channel summaries visible to a viewer — the room channel plus any
        private channel the viewer participates in. A spectator polls with the
        watched seat's id, so this also surfaces that AI's private channels."""
        room.room_channel()
        out: list[dict] = []
        for ch in room.chat_channels.values():
            if ch.is_room or (viewer_lobby_id and viewer_lobby_id in ch.participants):
                out.append(ch.summary())
        return out

    def handle_chat(self, room_id: str, lobby_id: str, msg: dict) -> None:
        room = self.rooms.get(room_id)
        if not room:
            return
        lp = next((p for p in room.players if p.player_id == lobby_id), None)
        if lp is None:
            return
        text = str(msg.get("text", "")).strip()[:CHAT_TEXT_MAX]
        if not text:
            return
        room.room_channel()
        channel = room.chat_channels.get(msg.get("channel_id") or ROOM_CHANNEL_ID)
        if channel is None:
            return
        if not channel.is_room and lobby_id not in channel.participants:
            return  # not a member of this private channel
        payload = self._chat_payload(room, lp, channel, text)
        channel.history.append(payload)
        self._chat_deliver(room, channel, payload)

    def handle_chat_create_channel(self, room_id: str, lobby_id: str, msg: dict) -> None:
        room = self.rooms.get(room_id)
        if not room:
            return
        creator = next((p for p in room.players if p.player_id == lobby_id), None)
        if creator is None:
            return
        topic = (str(msg.get("topic", "")).strip()[:80]) or "Private chat"
        by_name = {p.name.strip().casefold(): p.player_id for p in room.players}
        participants = {creator.player_id}
        for n in (msg.get("participants") or []):
            pid = by_name.get(str(n).strip().casefold())
            if pid:
                participants.add(pid)
        if len(participants) < 2:
            return  # a private channel needs at least one other member
        channel = ChatChannel(
            channel_id=_short_id(), topic=topic, is_room=False, participants=participants,
        )
        room.chat_channels[channel.channel_id] = channel
        info = {"type": "chat_channel", "channel": channel.summary()}
        for pid in self._chat_recipients(room, channel):
            self._thread_safe_send(room_id, pid, info)

    @staticmethod
    def heartbeat_ack(msg: dict) -> dict:
        """Build an app-level WebSocket heartbeat acknowledgement.

        Browser clients and agent adapters cannot rely on protocol-level ping
        frames, so the Island Traders WS protocol accepts lightweight
        ``{"type": "ping"}`` / ``{"type": "heartbeat"}`` messages and replies
        with ``pong``. Echoing optional fields lets clients measure round-trip
        time without the server needing to understand their clock format.
        """
        ack = {"type": "pong"}
        for key in ("client_time", "sent_at", "nonce"):
            if key in msg:
                ack[key] = msg[key]
        ack["server_time"] = time.time()
        return ack

    def register_ws(self, room_id: str, lobby_player_id: str, ws) -> None:
        with self._ws_lock:
            if room_id not in self._ws_connections:
                self._ws_connections[room_id] = {}
            self._ws_connections[room_id][lobby_player_id] = ws

    def unregister_ws(self, room_id: str, lobby_player_id: str, ws=None) -> bool:
        """Remove this player's socket entry from the connection table.

        When ``ws`` is provided, only removes the entry if the stored
        socket is the same object — fixes the reconnect race where a new
        connection has already replaced this slot before the old
        connection's ``finally`` block fires.  Returns ``True`` iff an
        entry was actually removed (i.e. this socket was still the live
        one).  Without ``ws``, removes whatever is stored (legacy /
        forced cleanup).
        """
        with self._ws_lock:
            conns = self._ws_connections.get(room_id, {})
            if ws is None:
                return conns.pop(lobby_player_id, None) is not None
            if conns.get(lobby_player_id) is ws:
                del conns[lobby_player_id]
                return True
            return False

    def handle_player_response(self, room_id: str, lobby_player_id: str, value) -> None:
        """Route a WS response message to the right engine player's event."""
        room = self.rooms.get(room_id)
        if not room or not room.io_adapter:
            logger.debug("handle_player_response: room %s not found or no io_adapter", room_id)
            return
        engine_pid = room.lobby_to_engine_id.get(lobby_player_id)
        if engine_pid is None:
            logger.warning("handle_player_response: lobby_player_id %s has no engine mapping "
                           "(room %s, phase %s)", lobby_player_id, room_id, room.season_phase)
            return
        room.io_adapter.receive_response(engine_pid, value)

    # ---- Pause / Resume (Issue #1) ----

    def request_pause(self, room_id: str, lobby_player_id: str, paused: bool) -> dict:
        """Host-only request to pause or resume the game.

        On pause:
          * `room.paused` is set to True and `paused_at` records the time.
          * All active asyncio timers (auction, investing, season-action) are
            cancelled; their `*_timer_end` epochs are frozen.
          * The pre-season wait loop (running on the game thread) sees
            `room.paused` and holds until resume.
          * `submit_ready` still accepts presses but does NOT advance the game
            state (no interrupt_all, no _pre_season_done.set).
          * Broadcasts `game_paused` to all clients.

        On resume:
          * Computes the pause duration.
          * Bumps every frozen `*_timer_end` forward by that duration.
          * Reschedules the asyncio timer task with the new remaining seconds.
          * Clears `room.paused`.
          * Broadcasts `game_resumed`.
          * After resume the normal Ready-quorum / timer logic catches up.
        """
        room = self.rooms.get(room_id)
        if not room:
            return {"error": "Room not found"}
        if lobby_player_id != room.creator_id:
            return {"error": "Only the host can pause or resume the game"}
        if room.status not in ("auction", "investing", "running"):
            return {"error": f"Cannot pause from status '{room.status}'"}

        if paused:
            if room.paused:
                return {"ok": True, "paused": True, "noop": True}
            self._do_pause(room)
            return {"ok": True, "paused": True}
        else:
            if not room.paused:
                return {"ok": True, "paused": False, "noop": True}
            self._do_resume(room)
            return {"ok": True, "paused": False}

    def _do_pause(self, room: GameRoom) -> None:
        room.paused = True
        room.paused_at = time.time()

        # Freeze auction timer
        if room.auction and room.auction._timer_task is not None:
            try:
                room.auction._timer_task.cancel()
            except Exception:
                pass
            room.auction._timer_task = None

        # Freeze investing timer
        if room.investing and room.investing._timer_task is not None:
            try:
                room.investing._timer_task.cancel()
            except Exception:
                pass
            room.investing._timer_task = None

        # Freeze action-phase season timer
        if room.season_timer_task is not None:
            try:
                room.season_timer_task.cancel()
            except Exception:
                pass
            room.season_timer_task = None

        # Pre-season timer is enforced inside the game thread's wait loop;
        # it inspects `room.paused` on each iteration.  No task to cancel.

        self._thread_safe_broadcast(room.room_id, {
            "type": "game_paused",
            "at": room.paused_at,
        })
        logger.info("Room %s paused by host (status=%s, phase=%s)",
                    room.room_id, room.status, room.season_phase)

    def _do_resume(self, room: GameRoom) -> None:
        now = time.time()
        pause_duration = max(0.0, now - room.paused_at)

        # Bump every frozen end-epoch forward by the pause duration so the
        # remaining time picks up where it left off.
        if room.auction and room.auction.timer_end > 0:
            room.auction.timer_end += pause_duration
            remaining = max(0.0, room.auction.timer_end - now)
            if self._loop and remaining > 0:
                fut = asyncio.run_coroutine_threadsafe(
                    self._auction_timer(room.room_id, remaining), self._loop,
                )
                room.auction._timer_task = fut
            elif (remaining <= 0
                    and room.status == "auction"
                    and room.auction.phase != "complete"):
                # Pause happened right at (or after) auction expiry — the
                # cancelled timer task never got to call _resolve_auction.
                # Resolve immediately on resume so the auction doesn't sit
                # forever with timer_remaining=0 and no Continue button.
                # Bug fix: "auction stuck at timer 0 after pause/resume".
                self._resolve_auction(room.room_id)

        if room.investing and room.investing.timer_end > 0:
            room.investing.timer_end += pause_duration
            remaining = max(0.0, room.investing.timer_end - now)
            if self._loop and remaining > 0:
                fut = asyncio.run_coroutine_threadsafe(
                    self._investing_timer(room.room_id, remaining), self._loop,
                )
                room.investing._timer_task = fut

        if room.season_timer_end > 0:
            room.season_timer_end += pause_duration
            remaining = max(0.0, room.season_timer_end - now)
            if self._loop and remaining > 0:
                fut = asyncio.run_coroutine_threadsafe(
                    self._season_timer(room.room_id, int(remaining)), self._loop,
                )
                room.season_timer_task = fut

        if room.pre_season_end > 0:
            room.pre_season_end += pause_duration

        room.paused = False
        room.paused_at = 0.0

        self._thread_safe_broadcast(room.room_id, {
            "type": "game_resumed",
            "pause_duration": round(pause_duration, 2),
        })
        # Re-broadcast the in-season ready/timer state so clients see the
        # bumped countdown immediately.
        if room.status == "running" and room.season_phase in ("pre_season", "action"):
            self._broadcast_ready_update(room)
        logger.info("Room %s resumed by host after %.1fs paused",
                    room.room_id, pause_duration)

        # After resume, re-check the Ready quorum.  Pre-season readiness always
        # closes the review window.  In action phase, only ready-only games
        # (season_timer_end == 0) close on quorum; timed seasons stay open
        # until the countdown expires so players can undo/resume trading.
        if (room.status == "running"
                and room.season_active_humans
                and room.season_ready_set >= room.season_active_humans):
            if room.season_phase == "action" and room.io_adapter:
                if room.season_timer_end <= 0:
                    if self._loop is not None:
                        if room.all_ready_task is None:
                            fut = asyncio.run_coroutine_threadsafe(
                                self._delayed_interrupt(room.room_id), self._loop
                            )
                            room.all_ready_task = fut
                    else:
                        # No event loop (e.g. unit-test environment): interrupt immediately.
                        room.io_adapter.interrupt_all()
            elif room.season_phase == "pre_season":
                room._pre_season_done.set()

    # ---- Simultaneous-play: per-season Ready + Timer ----

    def _on_season_start(self, room_id: str, year: int, season_index: int) -> None:
        """Reset per-season ready/timer state, run optional pre-season window,
        then broadcast season_start for the action phase.

        This method runs on the game thread (a daemon thread spawned by
        _launch_game).  If pre_season_timer_seconds > 0 it BLOCKS that thread
        until either every human clicks "Ready to start" or the timer fires —
        giving everyone a review window before the action phase opens.
        """
        room = self.rooms.get(room_id)
        if not room or not room.io_adapter:
            return

        season_name = SEASONS[season_index] if season_index < len(SEASONS) else str(season_index)
        room.current_year_index = year
        room.current_season_index = season_index
        current_tick = year * len(SEASONS) + season_index
        if room.game:
            for player in room.game.players:
                delivered = player.deliver_in_transit(current_tick)
                if delivered:
                    names = ", ".join(delivered)
                    room.io_adapter.print(
                        f"  {player.name}'s ordered capital arrived: {names}"
                    )
        humans = {
            lp.player_id for lp in room.players
            if lp.is_human and lp.role_names
        }

        # ── Pre-season review window ──────────────────────────────────────────
        pre_secs = max(0, int(room.pre_season_timer_seconds))
        if pre_secs > 0 and humans:
            room.season_phase = "pre_season"
            room.season_ready_set = set()
            room.season_active_humans = humans
            room._pre_season_done.clear()
            room.pre_season_end = time.time() + pre_secs

            self._thread_safe_broadcast(room_id, {
                "type": "pre_season_start",
                "year": year + 1,
                "season": season_name,
                "season_index": season_index,
                "timer_seconds": pre_secs,
                "active_humans": list(humans),
            })

            # Block the game thread until everyone is Ready OR the timer
            # naturally expires.  Polled in 0.5s slices so the loop can
            # respect `room.paused` — when paused, `pre_season_end` is bumped
            # forward by _do_resume() so the timeout is automatically extended.
            while True:
                if room._pre_season_done.is_set():
                    break
                now = time.time()
                if not room.paused and now >= room.pre_season_end:
                    break  # natural timeout
                # Wait briefly; if the done-event fires, return immediately.
                if room._pre_season_done.wait(timeout=0.5):
                    break

            room.pre_season_end = 0.0
            self._thread_safe_broadcast(room_id, {"type": "pre_season_end"})

        # ── Action phase ──────────────────────────────────────────────────────
        room.io_adapter.begin_season()
        room.season_phase = "action"
        room.season_active_humans = humans
        room.season_ready_set = set()
        room.season_human_done = set()
        room.all_ready_task = None   # reset any stale grace task from prior season
        secs = max(0, int(room.season_timer_seconds))
        room.season_timer_end = (time.time() + secs) if secs > 0 else 0.0
        logger.info(
            "[season-timer] season_start room=%s year=%s season=%s "
            "epoch=%.3f timer_end=%.3f seconds=%s active_humans=%s",
            room_id,
            year + 1,
            season_name,
            time.time(),
            room.season_timer_end,
            secs,
            sorted(humans),
        )

        self._thread_safe_broadcast(room_id, {
            "type": "season_start",
            "year": year + 1,
            "season": season_name,
            "season_index": season_index,
            "timer_seconds": secs,        # 0 = Ready-only mode
            # Authoritative timing so clients sync their countdown to the server
            # clock instead of starting it at message-receipt (avoids the "season
            # ended before my countdown finished" desync).
            "server_now": round(time.time(), 3),
            "timer_end": round(room.season_timer_end, 3) if secs > 0 else 0,
            "active_humans": list(humans),
        })

        # Broadcast per-player event results for the Conditions panel.
        # game._last_event_results is set by game.run() just before calling
        # before_season, so it's always fresh at this point.
        if room.game:
            event_results = getattr(room.game, "_last_event_results", {})
            player_names = {p.player_id: p.name for p in room.game.players}
            events_payload = {}
            has_disaster = False
            disaster_name = None
            for pid, ev in event_results.items():
                events_payload[str(pid)] = {
                    "player_name": player_names.get(pid, f"Player {pid}"),
                    "event_name": ev.event_name,
                    "yield_modifier": ev.yield_modifier,
                    "outage": ev.outage,
                    "natural_disaster": ev.natural_disaster,
                    "description": ev.describe(),
                    # Impact + duration for the disaster pop-up (UI #86-adjacent).
                    "damage_seasons": ev.damage_seasons,
                    "price_shock_resource": (
                        ev.price_shock_resource.value
                        if ev.price_shock_resource else None
                    ),
                    "price_shock_multiplier": ev.price_shock_multiplier,
                    # A disruptive event is anything off-normal — drives whether
                    # the client raises a modal.
                    "disruptive": (
                        ev.natural_disaster or ev.outage or ev.yield_modifier < 1.0
                    ),
                }
                if ev.natural_disaster and not has_disaster:
                    has_disaster = True
                    disaster_name = ev.event_name
            self._thread_safe_broadcast(room_id, {
                "type": "season_events",
                "year": year + 1,
                "season": season_name,
                "events": events_payload,
                "regional_disaster": disaster_name,
            })
        # Defensive: broadcast the cleared Ready/Done sets immediately so
        # the client's `imReady` / `seasonDoneSet` can't ride over from
        # the previous season due to message ordering / stale state.
        # (2026-05-27 done-trading-undo brief Sub-issue A.)
        self._broadcast_ready_update(room)

        # Only install the action-phase timer if it's > 0.
        if secs > 0 and self._loop:
            fut = asyncio.run_coroutine_threadsafe(
                self._season_timer(room_id, secs), self._loop,
            )
            room.season_timer_task = fut

    def _on_season_end(self, room_id: str, year: int, season_index: int) -> None:
        """Clear the season timer + broadcast resolution."""
        room = self.rooms.get(room_id)
        if not room:
            return
        room.season_timer_task = None
        room.season_timer_end = 0.0
        # Cancel any pending all-ready grace interrupt (season is already done).
        if room.all_ready_task is not None:
            room.all_ready_task.cancel()
            room.all_ready_task = None
        season_name = SEASONS[season_index] if season_index < len(SEASONS) else str(season_index)
        logger.info(
            "[season-timer] season_resolved room=%s year=%s season=%s "
            "epoch=%.3f",
            room_id,
            year + 1,
            season_name,
            time.time(),
        )
        self._thread_safe_broadcast(room_id, {
            "type": "season_resolved",
            "year": year + 1,
            "season": season_name,
        })

    # Grace added to the server-side season countdown so the authoritative timer
    # never fires *before* a client's visible countdown reaches 0. The client
    # starts its countdown when it receives `season_start` (broadcast + network
    # + render latency after the server starts its clock), so without this the
    # season could resolve while players still see a few seconds left. The
    # season_start payload also carries `server_now` + `timer_end` so clients can
    # sync their display to the server clock; this grace covers the residual
    # latency + the client's 250ms tick/rounding.
    _SEASON_TIMER_GRACE_SECONDS: float = 1.5

    def _wait_for_timed_season_release(
        self, room_id: str, year: int, season_index: int
    ) -> None:
        """Hold an action season open until its advertised timer has expired.

        In simultaneous play the engine turn threads can all finish before the
        human-facing timer. Without this hold, run_season returns and advances
        the game even though clients still show trading time remaining.
        """
        room = self.rooms.get(room_id)
        if not room or room.season_phase != "action" or room.season_timer_end <= 0:
            return
        logger.info(
            "[season-timer] all_turn_threads_complete room=%s year=%s season=%s "
            "epoch=%.3f timer_end=%.3f",
            room_id,
            year + 1,
            SEASONS[season_index] if season_index < len(SEASONS) else season_index,
            time.time(),
            room.season_timer_end,
        )
        while True:
            room = self.rooms.get(room_id)
            if not room or room.status != "running" or room.season_phase != "action":
                return
            if room.season_timer_end <= 0:
                return
            release_at = room.season_timer_end + self._SEASON_TIMER_GRACE_SECONDS
            remaining = release_at - time.time()
            if remaining <= 0:
                logger.info(
                    "[season-timer] timed_season_release room=%s epoch=%.3f "
                    "timer_end=%.3f",
                    room_id,
                    time.time(),
                    room.season_timer_end,
                )
                return
            time.sleep(min(0.5, remaining))

    async def _season_timer(self, room_id: str, seconds: int) -> None:
        """Sleep for the season window (plus grace), then force-end pending turns."""
        await asyncio.sleep(max(0.0, seconds) + self._SEASON_TIMER_GRACE_SECONDS)
        room = self.rooms.get(room_id)
        if not room or not room.io_adapter:
            return
        logger.info(
            "[season-timer] _season_timer_fire room=%s epoch=%.3f "
            "timer_end=%.3f seconds=%s",
            room_id,
            time.time(),
            room.season_timer_end,
            seconds,
        )
        # Only fire if the season is still active (turn threads haven't all
        # finished). interrupt_all unblocks every pending IO prompt with None,
        # which causes choose_action to return END_TURN and exit each loop.
        room.io_adapter.interrupt_all()
        logger.info(
            "[season-timer] season_timeout_broadcast room=%s epoch=%.3f "
            "timer_end=%.3f",
            room_id,
            time.time(),
            room.season_timer_end,
        )
        self._thread_safe_broadcast(room_id, {
            "type": "season_timeout",
            "server_now": round(time.time(), 3),
            "timer_end": round(room.season_timer_end, 3),
        })

    # Grace period (seconds) between "all humans ready" and the actual
    # interrupt_all().  Gives the park loop time to engage + show the
    # "Resume Trading" banner, especially in single-player games where the
    # interrupt would otherwise fire on the same request as mark_player_ready.
    _ALL_READY_GRACE_SECONDS: float = 3.0

    async def _delayed_interrupt(self, room_id: str) -> None:
        """Wait for the grace period, then end the season if still all-ready."""
        await asyncio.sleep(self._ALL_READY_GRACE_SECONDS)
        room = self.rooms.get(room_id)
        if not room or not room.io_adapter:
            return
        room.all_ready_task = None
        logger.info(
            "[season-timer] _delayed_interrupt_check room=%s epoch=%.3f "
            "timer_end=%.3f phase=%s ready=%s active=%s",
            room_id,
            time.time(),
            room.season_timer_end,
            room.season_phase,
            sorted(room.season_ready_set),
            sorted(room.season_active_humans),
        )
        # Only interrupt if the season is still active and all active humans
        # are still in the ready set (someone may have clicked Undo during
        # the grace window).
        if (room.status == "running"
                and room.season_phase == "action"
                and not room.paused
                and room.season_active_humans
                and room.season_ready_set >= room.season_active_humans):
            logger.info(
                "[season-timer] _delayed_interrupt_fire room=%s epoch=%.3f "
                "timer_end=%.3f",
                room_id,
                time.time(),
                room.season_timer_end,
            )
            room.io_adapter.interrupt_all()

    def _broadcast_ready_update(self, room: "GameRoom") -> None:
        """Tell every connected client who has clicked Ready / completed."""
        # Choose the active timer based on current phase.
        if room.season_phase == "pre_season" and room.pre_season_end:
            timer_rem = max(0.0, round(room.pre_season_end - time.time(), 1))
        elif room.season_timer_end:
            timer_rem = max(0.0, round(room.season_timer_end - time.time(), 1))
        else:
            timer_rem = 0.0
        self._thread_safe_broadcast(room.room_id, {
            "type": "ready_update",
            "ready":   list(room.season_ready_set),
            "done":    list(room.season_human_done),
            "active":  list(room.season_active_humans),
            "phase":   room.season_phase,
            "timer_remaining": timer_rem,
        })

    # ---- Agent interaction store ----

    _AGENT_INTERACTIONS_MAX = 2000  # max records kept per room

    def post_agent_interactions(self, room_id: str, events: list[dict]) -> dict:
        """Append agent interaction records to the room's in-memory store.

        Called by the POST /api/rooms/{room_id}/agent-interactions route.
        Records are kept in arrival order; the oldest are evicted once the
        ring buffer reaches _AGENT_INTERACTIONS_MAX.  The caller (an external
        agent process) is responsible for including useful fields such as
        ``run_id``, ``seq``, ``timestamp``, ``direction``, ``kind``, and
        ``message_type`` — see the transcript format in island-traders-agents.
        """
        room = self.rooms.get(room_id)
        if room is None:
            return {"error": "Room not found"}
        if not isinstance(events, list):
            return {"error": "events must be a list"}
        room.agent_interactions.extend(events)
        excess = len(room.agent_interactions) - self._AGENT_INTERACTIONS_MAX
        if excess > 0:
            del room.agent_interactions[:excess]
        return {"accepted": len(events), "total": len(room.agent_interactions)}

    def get_agent_interactions(
        self, room_id: str, limit: int = 100, since_seq: int = 0
    ) -> dict | None:
        """Return agent interaction records for the room.

        ``since_seq`` filters to records whose ``seq`` field is strictly
        greater than the given value (0 = return all).  ``limit`` caps the
        number of returned records (0 = no cap).
        """
        room = self.rooms.get(room_id)
        if room is None:
            return None
        events: list[dict] = room.agent_interactions
        if since_seq > 0:
            events = [e for e in events if e.get("seq", 0) > since_seq]
        total = len(room.agent_interactions)
        if limit > 0:
            events = events[-limit:]
        return {"events": events, "total": total}

    def submit_ready(self, room_id: str, lobby_player_id: str, ready: bool = True) -> dict:
        """Mark a player as Ready (or unready) for the current season phase.

        Pre-season phase: Ready means "I'm done reviewing; let's start trading."
          When all active humans are ready, unblocks the game thread that is
          sleeping through the pre-season window.

        Action phase: Ready means "I'm done trading this season."
          In ready-only games, all-human readiness ends the season. In timed
          games, readiness parks each player but the trading window remains
          open until the timer expires, so players can resume while time remains.
        """
        room = self.rooms.get(room_id)
        if not room or not room.io_adapter:
            return {"error": "Game not running"}
        if lobby_player_id not in room.season_active_humans:
            return {"error": "Not an active human player this season"}

        engine_pid = room.lobby_to_engine_id.get(lobby_player_id)

        if room.season_phase == "pre_season":
            # Pre-season: collect readies; when all in, unblock the game thread.
            if ready:
                room.season_ready_set.add(lobby_player_id)
            else:
                room.season_ready_set.discard(lobby_player_id)
            self._broadcast_ready_update(room)
            # While paused we collect readies but do NOT advance — the host
            # must resume first.  _do_resume() re-checks the quorum.
            if (not room.paused
                    and room.season_active_humans
                    and room.season_ready_set >= room.season_active_humans):
                room._pre_season_done.set()
            return {"ok": True, "ready": ready}

        # ── Action phase ──────────────────────────────────────────────────────
        if ready:
            room.season_ready_set.add(lobby_player_id)
            # Set the per-player Ready flag — even if they're mid-action
            # (e.g. inside a market buy dialog) the next choose_action will
            # return END_TURN and exit the loop.  Skip while paused so the
            # in-flight prompt isn't unblocked until the host resumes.
            if (engine_pid is not None
                    and lobby_player_id not in room.season_human_done
                    and not room.paused):
                room.io_adapter.mark_player_ready(engine_pid)
        else:
            room.season_ready_set.discard(lobby_player_id)
            if engine_pid is not None and not room.paused:
                room.io_adapter.unmark_player_ready(engine_pid)

        self._broadcast_ready_update(room)

        if ready:
            # All active humans Ready → end only ready-only seasons after a
            # brief grace period so the park loop can engage and the "Resume
            # Trading" banner appears before the interrupt fires.  Timed
            # seasons stay open until the countdown expires.
            if (not room.paused
                    and room.season_active_humans
                    and room.season_ready_set >= room.season_active_humans
                    and room.season_timer_end <= 0
                    and room.all_ready_task is None
                    and self._loop is not None):
                fut = asyncio.run_coroutine_threadsafe(
                    self._delayed_interrupt(room.room_id), self._loop
                )
                room.all_ready_task = fut
        else:
            # Player un-readied — cancel any pending grace-period interrupt
            # so the season doesn't end while they're back in the menu.
            if room.all_ready_task is not None:
                room.all_ready_task.cancel()
                room.all_ready_task = None

        return {"ok": True, "ready": ready}


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    if FastAPI is None:
        raise ImportError(
            "FastAPI and uvicorn are required for the game server. "
            "Install with: pip install fastapi uvicorn[standard] websockets"
        )

    app = FastAPI(
        title="Island Traders API",
        version=APP_VERSION,
        description=(
            "HTTP API for creating Island Traders rooms, joining by room code, "
            "starting auctions/games, and reading game state. Real-time player "
            "interaction happens over WebSocket at `/ws/{room_id}/{player_id}`; "
            "clients send prompt replies as `{type: 'response', value: ...}`."
        ),
        openapi_tags=[
            {
                "name": "Lobby",
                "description": "Create rooms, list public waiting rooms, and join/rejoin by code.",
            },
            {
                "name": "Game Flow",
                "description": "Advance the room through auction, quick-start, and state inspection.",
            },
            {
                "name": "Reference",
                "description": "Static reference data for clients and agents.",
            },
        ],
    )
    manager = GameManager()

    @app.get("/version", tags=["Reference"], summary="Get server version")
    async def _get_version():
        return {"version": APP_VERSION}

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

    @app.post(
        "/api/rooms",
        tags=["Lobby"],
        summary="Create a room",
        description=(
            "Creates a waiting-room lobby and returns its room id, join code, "
            "and host lobby player. External agent clients usually create a "
            "room here or join an existing room by code."
        ),
    )
    async def create_room(body: CreateRoomRequest | None = None):
        body = body or CreateRoomRequest()
        room = manager.create_room(
            name=body.name,
            max_players=body.max_players,
            num_years=body.num_years,
            creator_name=body.creator_name,
            is_public=body.is_public,
            require_all_human=body.require_all_human,
            starting_capital=body.starting_capital,
            auction_timer_seconds=body.auction_timer_seconds,
            season_timer_seconds=body.season_timer_seconds,
            pre_season_timer_seconds=body.pre_season_timer_seconds,
            debug_starting_inventory=body.debug_starting_inventory,
        )
        return JSONResponse(room.to_dict())

    @app.get(
        "/api/rooms",
        tags=["Lobby"],
        summary="List public waiting rooms",
        description="Returns public rooms that are still in the waiting-room phase.",
    )
    async def list_rooms():
        public = [
            r.to_dict() for r in manager.rooms.values()
            if r.is_public and r.status == "waiting"
        ]
        return JSONResponse(public)

    @app.get(
        "/api/rooms/{room_id}",
        tags=["Lobby"],
        summary="Get room details",
        description="Returns the lobby/room metadata for a room id.",
    )
    async def get_room(room_id: str):
        room = manager.rooms.get(room_id)
        if not room:
            return JSONResponse({"error": "Room not found"}, status_code=404)
        return JSONResponse(room.to_dict())

    @app.get(
        "/api/rooms/by-code/{code}",
        tags=["Lobby"],
        summary="Resolve a room by its join code (read-only)",
        description=(
            "Returns room metadata (room_id, name, status) for a join code "
            "WITHOUT joining or taking a seat. Used by the spectator view so a "
            "watcher can supply the share code instead of the internal room id."
        ),
    )
    async def room_by_code(code: str):
        room = manager.find_room_by_code(code.strip().upper())
        if not room:
            return JSONResponse({"error": "Invalid room code"}, status_code=404)
        return JSONResponse({
            "room_id": room.room_id,
            "name": room.name,
            "status": room.status,
            "join_code": room.join_code,
        })

    @app.post(
        "/api/rooms/join-by-code",
        tags=["Lobby"],
        summary="Join or rejoin by room code",
        description=(
            "Join a waiting room by its short room code. If the game is already "
            "running, this also supports reconnecting by using the same player "
            "name originally used in the room."
        ),
    )
    async def join_by_code(body: JoinByCodeRequest):
        code = body.code.strip().upper()
        name = body.name
        room = manager.find_room_by_code(code)
        if not room:
            return JSONResponse({"error": "Invalid room code"}, status_code=404)
        result = manager.join_room(room.room_id, name)
        if not result and room.status != "waiting":
            result = manager.rejoin_room_by_name(room.room_id, name)
        if not result:
            if room.status == "waiting":
                message = "Cannot join room"
            else:
                message = "Game is already running. Enter the same player name you used in this room to rejoin."
            return JSONResponse({"error": message}, status_code=400)
        room, lp = result
        return JSONResponse({"room": room.to_dict(), "player_id": lp.player_id})

    @app.post(
        "/api/rooms/{room_id}/join",
        tags=["Lobby"],
        summary="Join (or rejoin) by room id",
        description=(
            "Join a waiting room when the full room id is already known. If the "
            "game has already started, reconnects you to your existing seat when "
            "the same player name is supplied (mirroring join-by-code). This is "
            "what the quick-seat ?join= URLs rely on to rejoin an established game."
        ),
    )
    async def join_room(room_id: str, body: JoinRoomRequest | None = None):
        body = body or JoinRoomRequest()
        result = manager.join_room(room_id, body.name)
        if not result:
            # Game already running: reconnect to the existing seat by name,
            # mirroring the join-by-code rejoin path.
            room = manager.rooms.get(room_id)
            if room and room.status != "waiting":
                result = manager.rejoin_room_by_name(room_id, body.name)
        if not result:
            return JSONResponse({"error": "Cannot join room"}, status_code=400)
        room, lp = result
        return JSONResponse({"room": room.to_dict(), "player_id": lp.player_id})

    @app.post(
        "/api/rooms/{room_id}/leave",
        tags=["Lobby"],
        summary="Leave a waiting room",
        description=(
            "Deregisters a lobby player from a room before the game starts "
            "(e.g. you joined the wrong game). Host duties pass to the next "
            "human; if no humans remain, the room is closed."
        ),
    )
    async def leave_room(room_id: str, body: LeaveRoomRequest):
        result = manager.leave_room(room_id, body.player_id)
        if "error" in result:
            status = 404 if result["error"] == "Room not found" else 400
            return JSONResponse(result, status_code=status)
        return JSONResponse(result)

    @app.post(
        "/api/rooms/{room_id}/ai",
        tags=["Lobby"],
        summary="Add built-in server AI",
        description=(
            "Adds a built-in deterministic server AI to a waiting room. This is "
            "different from an external GPT/Perplexity client, which should "
            "join as a normal player and connect to the WebSocket."
        ),
    )
    async def add_ai(room_id: str, body: AddAIRequest | None = None):
        body = body or AddAIRequest()
        lp = manager.add_ai_player(room_id, body.name)
        if not lp:
            return JSONResponse({"error": "Cannot add AI player"}, status_code=400)
        return JSONResponse({"player_id": lp.player_id, "name": lp.name})

    @app.post(
        "/api/rooms/{room_id}/auction/start",
        tags=["Game Flow"],
        summary="Start the role auction",
        description="Starts the timed role auction for a waiting room.",
    )
    async def start_auction(room_id: str):
        ok = manager.start_auction(room_id)
        if not ok:
            return JSONResponse({"error": "Cannot start auction"}, status_code=400)
        return JSONResponse({"status": "auction"})

    @app.post(
        "/api/rooms/{room_id}/auction/bid",
        tags=["Game Flow"],
        summary="Place an auction bid",
        description=(
            "Places or raises a lobby player's bid on a role during the auction. "
            "WebSocket clients can also send `{type:'bid', role_name, amount}`."
        ),
    )
    async def place_bid(room_id: str, body: AuctionBidRequest):
        result = manager.place_bid(
            room_id,
            body.player_id,
            body.role_name,
            float(body.amount),
        )
        if "error" in result:
            return JSONResponse(result, status_code=400)
        return JSONResponse(result)

    @app.post(
        "/api/rooms/{room_id}/start",
        tags=["Game Flow"],
        summary="Quick-start a room",
        description=(
            "Legacy quick-start: auto-assigns roles, fills missing roles with "
            "server AI, and launches the game without the auction."
        ),
    )
    async def start_game_quick(room_id: str):
        ok = manager.start_game_quick(room_id)
        if not ok:
            return JSONResponse({"error": "Cannot start game"}, status_code=400)
        return JSONResponse({"status": "running"})

    @app.get(
        "/api/rooms/{room_id}/state",
        tags=["Game Flow"],
        summary="Get current game state",
        description=(
            "Returns the current room/game state. Pass `player_id` to receive "
            "the player-specific view used by the dashboard and terminal agents."
        ),
    )
    async def get_state(room_id: str, player_id: str = ""):
        state = manager.get_game_state(room_id, player_id)
        if not state:
            return JSONResponse({"error": "No game state"}, status_code=404)
        return JSONResponse(state)

    @app.get(
        "/api/rooms/{room_id}/log",
        tags=["Game Flow"],
        summary="Download room log",
        response_class=PlainTextResponse,
    )
    async def get_log(room_id: str):
        """Download the full server-side game log as plain text.

        Driven by the dashboard's "Download Log" button (2026-05-27
        playtest ask for offline debugging).  Returns 404 if the room
        doesn't exist or has no IO adapter (game hasn't started yet).
        """
        room = manager.rooms.get(room_id)
        if room is None or room.io_adapter is None:
            return JSONResponse({"error": "No game log available"}, status_code=404)
        log_text = room.io_adapter.export_log()
        header = (
            f"# Island Traders game log\n"
            f"# Room: {room.name} ({room.room_id})\n"
            f"# Version: {APP_VERSION}\n"
            f"# Status: {room.status}\n"
            f"# Year/Season: {getattr(room.game, 'year', '?')} / "
            f"{getattr(room.game, 'season', '?')}\n"
            f"# ----------------------------------------\n\n"
        )
        return PlainTextResponse(
            header + log_text,
            media_type="text/plain",
            headers={
                "Content-Disposition":
                    f'attachment; filename="island-traders-log-{room.room_id}.txt"',
            },
        )

    @app.post(
        "/api/rooms/{room_id}/agent-interactions",
        tags=["Game Flow"],
        summary="Ingest agent interaction events",
        description="External LLM agent processes POST transcript-style interaction "
                    "records here; stored in a room-scoped ring buffer for the observer UI.",
    )
    async def post_agent_interactions(room_id: str, request: Request):
        """Ingest agent interaction events from an external LLM agent process.

        Accepts a JSON object ``{"events": [...]}`` or a bare JSON array.
        A single-event object is also accepted for convenience.

        Records are stored in a room-scoped ring buffer (2 000 max) and
        served by the GET endpoint below.  No authentication: intended for
        local / trusted agent processes only.
        """
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

        if isinstance(body, list):
            events = body
        elif isinstance(body, dict) and "events" in body:
            events = body["events"]
            if not isinstance(events, list):
                return JSONResponse({"error": "events must be an array"}, status_code=400)
        elif isinstance(body, dict):
            events = [body]
        else:
            return JSONResponse({"error": "Expected JSON object or array"}, status_code=400)

        result = manager.post_agent_interactions(room_id, events)
        if "error" in result:
            return JSONResponse(result, status_code=404)
        return JSONResponse(result)

    @app.get(
        "/api/rooms/{room_id}/agent-interactions",
        tags=["Game Flow"],
        summary="Fetch agent interaction events",
        description="Returns stored agent interaction records for the room, "
                    "with optional limit and since_seq filters.",
    )
    async def get_agent_interactions(
        room_id: str, limit: int = 100, since_seq: int = 0
    ):
        """Return agent interaction records for the room.

        Query params:
        - ``limit``: max records to return (default 100, 0 = no cap)
        - ``since_seq``: only return records with seq > this value (0 = all)
        """
        result = manager.get_agent_interactions(room_id, limit=limit, since_seq=since_seq)
        if result is None:
            return JSONResponse({"error": "Room not found"}, status_code=404)
        return JSONResponse(result)

    @app.get(
        "/api/roles",
        tags=["Reference"],
        summary="List playable roles",
        description="Returns role names, display names, island names, production, needs, and UI colors.",
    )
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

        # Backfill chat: the channels (room + any private ones) this seat can see,
        # with recent history, so a (re)connecting client's panel has context.
        await websocket.send_text(json.dumps({
            "type": "chat_history",
            "channels": manager._chat_visible_channels(room, player_id),
        }))

        try:
            # Send current state
            if room.status == "auction" and room.auction:
                # If the auction has already resolved but the room.status
                # hasn't flipped yet (the 2-second window before
                # _delayed_investing_start / _delayed_guarantee_start fires)
                # — OR a client missed the live auction_result broadcast —
                # replay the saved result so they see the Continue button.
                # Without this, clients that reconnect during that window
                # got dropped back into the auction view with timer=0 and
                # no way to advance.  Bug: "auction stuck at timer 0".
                if (room.auction.phase == "complete"
                        and room.auction.result_payload is not None):
                    await websocket.send_text(json.dumps(
                        room.auction.result_payload
                    ))
                else:
                    remaining = max(0.0, round(room.auction.timer_end - time.time(), 1))
                    await websocket.send_text(json.dumps({
                        "type": "auction_start",
                        "roles": [
                            {**ROLE_INFO[r], "name": r} for r in ALL_ROLES
                        ],
                        "timer_seconds": remaining,
                        "budget": round(room.starting_capital, 1),
                    }))
                    await websocket.send_text(json.dumps({
                        "type": "auction_update",
                        "auction": room.auction.to_dict(),
                    }))
            elif room.status == "guarantee" and room.guarantee:
                await websocket.send_text(json.dumps({
                    "type": "island_guarantee_state",
                    "guarantee": room.guarantee.to_dict(),
                }))
            elif room.status == "investing" and room.investing:
                await websocket.send_text(json.dumps({
                    "type": "investing_phase",
                    "timer_seconds": max(0.0, round(room.investing.timer_end - time.time(), 1)),
                }))
                payload = manager._investing_payload(room, lp)
                if payload:
                    await websocket.send_text(json.dumps(payload))
            elif room.status == "running":
                state = manager.get_game_state(room_id, player_id)
                if state:
                    await websocket.send_text(json.dumps(state))
                engine_pid = room.lobby_to_engine_id.get(player_id)
                if room.io_adapter and engine_pid is not None:
                    room.io_adapter.replay_pending_prompt(engine_pid)
                # Fresh ready_update on reconnect — otherwise the client's
                # cached `imReady` from before disconnect persists and
                # the "Done Trading ✓" button can appear stuck for a
                # season the player has not actually opted out of.
                # (2026-05-27 done-trading-undo brief Sub-issue A.)
                manager._broadcast_ready_update(room)

            # If the game is paused, let the reconnecting client know so it
            # can show the paused overlay immediately.
            if room.paused:
                await websocket.send_text(json.dumps({
                    "type": "game_paused",
                    "at": room.paused_at,
                }))

            while True:
                raw = await websocket.receive_text()
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                msg_type = msg.get("type", "")
                if msg_type in ("ping", "heartbeat"):
                    await websocket.send_text(json.dumps(manager.heartbeat_ack(msg)))
                elif msg_type == "response":
                    manager.handle_player_response(room_id, player_id, msg.get("value"))
                elif msg_type == "get_state":
                    state = manager.get_game_state(room_id, player_id)
                    if state:
                        await websocket.send_text(json.dumps(state))
                    # Also replay any unresolved IO prompt for this player.
                    # The initial WS connect already does this, but mid-game
                    # the client can lose its action prompt (Decision-Hint
                    # button drove a modal the user cancelled, dialog state
                    # drift, etc).  The "📋 Menu" recovery button calls
                    # requestState() — which lands here — and expects the
                    # server to redeliver the live engine prompt so the user
                    # can continue trading instead of staring at a dead
                    # season clock.
                    engine_pid = room.lobby_to_engine_id.get(player_id)
                    if (room.status == "running"
                            and room.io_adapter
                            and engine_pid is not None):
                        room.io_adapter.replay_pending_prompt(engine_pid)
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
                elif msg_type == "investment_submit":
                    result = manager.submit_investment(
                        room_id, player_id,
                        list(msg.get("item_ids") or []),
                        bool(msg.get("ready", False)),
                    )
                    await websocket.send_text(json.dumps({
                        "type": "investment_ack", **result
                    }))
                elif msg_type == "ready":
                    result = manager.submit_ready(
                        room_id, player_id, bool(msg.get("ready", True)),
                    )
                    await websocket.send_text(json.dumps({
                        "type": "ready_ack", **result
                    }))
                elif msg_type == "pause_request":
                    result = manager.request_pause(
                        room_id, player_id, bool(msg.get("paused", True)),
                    )
                    await websocket.send_text(json.dumps({
                        "type": "pause_ack", **result
                    }))
                elif msg_type == "guarantee_choice":
                    result = manager.submit_guarantee_choice(
                        room_id, player_id,
                        bool(msg.get("accept", False)),
                        msg.get("role"),
                    )
                    await websocket.send_text(json.dumps({
                        "type": "guarantee_ack", **result
                    }))
                elif msg_type == "chat":
                    manager.handle_chat(room_id, player_id, msg)
                elif msg_type == "chat_create_channel":
                    manager.handle_chat_create_channel(room_id, player_id, msg)
                elif msg_type == "training_counter_response":
                    await manager._handle_training_counter_response(
                        room_id, player_id, msg, websocket
                    )
                elif msg_type in ("deal_propose", "propose_deal"):
                    await manager._handle_deal_propose(
                        room_id, player_id, msg, websocket
                    )
                elif msg_type == "deal_respond":
                    await manager._handle_deal_respond(
                        room_id, player_id, msg, websocket
                    )
                elif msg_type == "order_batch":
                    await manager._handle_order_batch(
                        room_id, player_id, msg, websocket
                    )
                elif msg_type == "market_order_update":
                    await manager._handle_market_order_update(
                        room_id, player_id, msg, websocket
                    )
                elif msg_type == "training_batch":
                    await manager._handle_training_batch(
                        room_id, player_id, msg, websocket
                    )
                elif msg_type == "buy_out_float":
                    await manager._handle_buy_out_float(
                        room_id, player_id, msg, websocket
                    )
                elif msg_type == "capital_order":
                    await manager._handle_capital_order(
                        room_id, player_id, msg, websocket
                    )
                elif msg_type == "capital_negotiation_respond":
                    await manager._handle_capital_negotiation_respond(
                        room_id, player_id, msg, websocket
                    )
                elif msg_type == "capital_negotiation_accept":
                    await manager._handle_capital_negotiation_accept(
                        room_id, player_id, msg, websocket
                    )
                elif msg_type == "capital_repair":
                    await manager._handle_capital_repair(
                        room_id, player_id, msg, websocket
                    )

        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.exception("WebSocket error for %s/%s", room_id, player_id)
        finally:
            # Identity-aware unregister: only flip `connected` to False if
            # this socket was still the live one for the slot.  If a quick
            # reconnect has already replaced it (a new tab, browser refresh,
            # network blip + auto-reconnect), the new socket stays in the
            # table and `connected` stays True so subsequent server-to-client
            # messages still reach the player.  Fixes bug #2.
            if manager.unregister_ws(room_id, player_id, websocket):
                lp.connected = False

    return app


def main():
    import argparse
    import os
    # Honour the PORT env var (used by autoPort-assigned preview ports and most
    # PaaS providers).  Falls back to 8000 only if neither --port nor PORT is set.
    default_port = int(os.environ.get("PORT", "8000"))
    default_host = os.environ.get("HOST", "0.0.0.0")
    parser = argparse.ArgumentParser(description="Island Traders Game Server")
    parser.add_argument("--host", default=default_host)
    parser.add_argument("--port", type=int, default=default_port)
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
