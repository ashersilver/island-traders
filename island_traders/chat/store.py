"""
Persistence layer for the chat system.

SQLiteChatStore uses Python's built-in sqlite3 — no extra dependencies.
Swap for PostgresChatStore later by implementing the same interface.

All datetimes stored as UTC ISO-8601 strings; returned as datetime objects.
Lists stored as JSON arrays.
"""
from __future__ import annotations
import json
import sqlite3
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path

from .models import Agreement, AgreementStatus, ChatMessage, ChatRoom, MessageType


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Abstract interface
# ---------------------------------------------------------------------------

class ChatStore(ABC):

    # --- Rooms ---
    @abstractmethod
    def save_room(self, room: ChatRoom) -> None: ...

    @abstractmethod
    def get_room(self, room_id: str) -> ChatRoom | None: ...

    @abstractmethod
    def list_rooms_for_player(self, player_id: int) -> list[ChatRoom]: ...

    @abstractmethod
    def add_participant(self, room_id: str, player_id: int) -> None: ...

    @abstractmethod
    def remove_participant(self, room_id: str, player_id: int) -> None: ...

    # --- Messages ---
    @abstractmethod
    def save_message(self, msg: ChatMessage) -> ChatMessage: ...   # returns msg with assigned id

    @abstractmethod
    def get_messages(self, room_id: str, since_id: int = 0) -> list[ChatMessage]: ...

    # --- Agreements ---
    @abstractmethod
    def save_agreement(self, agreement: Agreement) -> Agreement: ...  # returns with assigned id

    @abstractmethod
    def update_agreement(self, agreement: Agreement) -> None: ...

    @abstractmethod
    def get_agreement(self, agreement_id: int) -> Agreement | None: ...

    @abstractmethod
    def list_pending_for_player(self, player_id: int) -> list[Agreement]: ...

    @abstractmethod
    def list_ratified(self) -> list[Agreement]: ...


# ---------------------------------------------------------------------------
# SQLite implementation
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_rooms (
    room_id     TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    created_by  INTEGER NOT NULL,
    is_private  INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS room_participants (
    room_id    TEXT NOT NULL,
    player_id  INTEGER NOT NULL,
    joined_at  TEXT NOT NULL,
    PRIMARY KEY (room_id, player_id)
);

CREATE TABLE IF NOT EXISTS messages (
    message_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id       TEXT NOT NULL,
    sender_id     INTEGER NOT NULL,
    sender_name   TEXT NOT NULL,
    content       TEXT NOT NULL,
    message_type  TEXT NOT NULL DEFAULT 'chat',
    timestamp     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agreements (
    agreement_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id             TEXT NOT NULL,
    proposer_id         INTEGER NOT NULL,
    description         TEXT NOT NULL,
    party_ids           TEXT NOT NULL,
    accepted_by         TEXT NOT NULL DEFAULT '[]',
    rejected_by         TEXT NOT NULL DEFAULT '[]',
    status              TEXT NOT NULL DEFAULT 'pending',
    linked_game_action  TEXT,
    created_at          TEXT NOT NULL,
    resolved_at         TEXT
);

CREATE INDEX IF NOT EXISTS idx_messages_room ON messages (room_id, message_id);
CREATE INDEX IF NOT EXISTS idx_agreements_status ON agreements (status);
"""


class SQLiteChatStore(ChatStore):
    """
    SQLite-backed chat store. Thread-safe via check_same_thread=False
    with WAL mode for concurrent reads.
    """

    def __init__(self, db_path: str = "island_traders_chat.db") -> None:
        self._db_path = str(Path(db_path).resolve())
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    # --- Rooms ---

    def save_room(self, room: ChatRoom) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO chat_rooms (room_id, name, created_by, is_private, created_at)"
                " VALUES (?,?,?,?,?)",
                (room.room_id, room.name, room.created_by,
                 int(room.is_private), room.created_at.isoformat()),
            )
            for pid in room.participant_ids:
                conn.execute(
                    "INSERT OR IGNORE INTO room_participants (room_id, player_id, joined_at)"
                    " VALUES (?,?,?)",
                    (room.room_id, pid, room.created_at.isoformat()),
                )

    def get_room(self, room_id: str) -> ChatRoom | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM chat_rooms WHERE room_id=?", (room_id,)
            ).fetchone()
            if not row:
                return None
            pids = [
                r["player_id"] for r in conn.execute(
                    "SELECT player_id FROM room_participants WHERE room_id=?", (room_id,)
                )
            ]
            return ChatRoom(
                room_id=row["room_id"],
                name=row["name"],
                created_by=row["created_by"],
                participant_ids=pids,
                is_private=bool(row["is_private"]),
                created_at=_dt(row["created_at"]),
            )

    def list_rooms_for_player(self, player_id: int) -> list[ChatRoom]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT room_id FROM room_participants WHERE player_id=?", (player_id,)
            ).fetchall()
        return [self.get_room(r["room_id"]) for r in rows if self.get_room(r["room_id"])]

    def add_participant(self, room_id: str, player_id: int) -> None:
        from datetime import datetime, timezone
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO room_participants (room_id, player_id, joined_at)"
                " VALUES (?,?,?)",
                (room_id, player_id, datetime.now(timezone.utc).isoformat()),
            )

    def remove_participant(self, room_id: str, player_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM room_participants WHERE room_id=? AND player_id=?",
                (room_id, player_id),
            )

    # --- Messages ---

    def save_message(self, msg: ChatMessage) -> ChatMessage:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO messages (room_id, sender_id, sender_name, content, message_type, timestamp)"
                " VALUES (?,?,?,?,?,?)",
                (msg.room_id, msg.sender_id, msg.sender_name,
                 msg.content, msg.message_type.value, msg.timestamp.isoformat()),
            )
            msg.message_id = cur.lastrowid
        return msg

    def get_messages(self, room_id: str, since_id: int = 0) -> list[ChatMessage]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM messages WHERE room_id=? AND message_id>? ORDER BY message_id",
                (room_id, since_id),
            ).fetchall()
        return [
            ChatMessage(
                message_id=r["message_id"],
                room_id=r["room_id"],
                sender_id=r["sender_id"],
                sender_name=r["sender_name"],
                content=r["content"],
                message_type=MessageType(r["message_type"]),
                timestamp=_dt(r["timestamp"]),
            )
            for r in rows
        ]

    # --- Agreements ---

    def save_agreement(self, agreement: Agreement) -> Agreement:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO agreements"
                " (room_id, proposer_id, description, party_ids, accepted_by, rejected_by,"
                "  status, linked_game_action, created_at, resolved_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    agreement.room_id,
                    agreement.proposer_id,
                    agreement.description,
                    json.dumps(agreement.party_ids),
                    json.dumps(agreement.accepted_by),
                    json.dumps(agreement.rejected_by),
                    agreement.status.value,
                    agreement.linked_game_action,
                    agreement.created_at.isoformat(),
                    agreement.resolved_at.isoformat() if agreement.resolved_at else None,
                ),
            )
            agreement.agreement_id = cur.lastrowid
        return agreement

    def update_agreement(self, agreement: Agreement) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE agreements SET accepted_by=?, rejected_by=?, status=?, resolved_at=?"
                " WHERE agreement_id=?",
                (
                    json.dumps(agreement.accepted_by),
                    json.dumps(agreement.rejected_by),
                    agreement.status.value,
                    agreement.resolved_at.isoformat() if agreement.resolved_at else None,
                    agreement.agreement_id,
                ),
            )

    def get_agreement(self, agreement_id: int) -> Agreement | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM agreements WHERE agreement_id=?", (agreement_id,)
            ).fetchone()
        if not row:
            return None
        return self._row_to_agreement(row)

    def list_pending_for_player(self, player_id: int) -> list[Agreement]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM agreements WHERE status='pending' ORDER BY agreement_id"
            ).fetchall()
        result = []
        for row in rows:
            ag = self._row_to_agreement(row)
            if player_id in ag.pending_parties:
                result.append(ag)
        return result

    def list_ratified(self) -> list[Agreement]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM agreements WHERE status='ratified' ORDER BY resolved_at DESC"
            ).fetchall()
        return [self._row_to_agreement(r) for r in rows]

    @staticmethod
    def _row_to_agreement(row: sqlite3.Row) -> Agreement:
        return Agreement(
            agreement_id=row["agreement_id"],
            room_id=row["room_id"],
            proposer_id=row["proposer_id"],
            description=row["description"],
            party_ids=json.loads(row["party_ids"]),
            accepted_by=json.loads(row["accepted_by"]),
            rejected_by=json.loads(row["rejected_by"]),
            status=AgreementStatus(row["status"]),
            linked_game_action=row["linked_game_action"],
            created_at=_dt(row["created_at"]),
            resolved_at=_dt(row["resolved_at"]) if row["resolved_at"] else None,
        )
