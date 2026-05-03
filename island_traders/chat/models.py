"""
Chat and agreement data models for Island Traders online play.

Architecture note:
  These models are transport-agnostic. The ChatService operates on them
  directly; a future WebSocket or REST layer serialises them to JSON.
  All datetimes are UTC ISO-8601 strings when stored; datetime objects here.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


def _now() -> datetime:
    return datetime.now(timezone.utc)


class MessageType(str, Enum):
    CHAT      = "chat"       # free-form negotiation text
    PROPOSAL  = "proposal"   # formal agreement proposal posted in room
    SYSTEM    = "system"     # automated game notifications


class AgreementStatus(str, Enum):
    PENDING  = "pending"   # waiting for all parties to respond
    RATIFIED = "ratified"  # all parties accepted
    REJECTED = "rejected"  # at least one party rejected
    EXPIRED  = "expired"   # not resolved within the allowed turn window


@dataclass
class ChatMessage:
    message_id: int
    room_id: str
    sender_id: int
    sender_name: str
    content: str
    message_type: MessageType
    timestamp: datetime = field(default_factory=_now)

    def to_dict(self) -> dict:
        return {
            "message_id":   self.message_id,
            "room_id":      self.room_id,
            "sender_id":    self.sender_id,
            "sender_name":  self.sender_name,
            "content":      self.content,
            "message_type": self.message_type.value,
            "timestamp":    self.timestamp.isoformat(),
        }


@dataclass
class ChatRoom:
    room_id: str
    name: str
    created_by: int            # player_id of creator
    participant_ids: list[int] # all players with access
    is_private: bool = True    # False = any player can join
    created_at: datetime = field(default_factory=_now)

    def has_participant(self, player_id: int) -> bool:
        return player_id in self.participant_ids

    def to_dict(self) -> dict:
        return {
            "room_id":         self.room_id,
            "name":            self.name,
            "created_by":      self.created_by,
            "participant_ids": self.participant_ids,
            "is_private":      self.is_private,
            "created_at":      self.created_at.isoformat(),
        }


@dataclass
class Agreement:
    """
    A formal agreement proposed in a chat room.

    Lifecycle:
      PENDING → all party_ids have one turn to respond.
      If any party rejects → REJECTED.
      If all accept → RATIFIED and posted to the public ChatBoard.
      If the turn window passes without a response → EXPIRED.
    """
    agreement_id: int
    room_id: str
    proposer_id: int
    description: str            # free-text terms agreed in chat
    party_ids: list[int]        # all players who must ratify (includes proposer)
    accepted_by: list[int] = field(default_factory=list)
    rejected_by: list[int] = field(default_factory=list)
    status: AgreementStatus = AgreementStatus.PENDING
    # Optional link to a game engine action that gets triggered on ratification
    linked_game_action: str | None = None   # e.g. "training_request:5", "deal:12"
    created_at: datetime = field(default_factory=_now)
    resolved_at: datetime | None = None

    @property
    def pending_parties(self) -> list[int]:
        responded = set(self.accepted_by) | set(self.rejected_by)
        return [p for p in self.party_ids if p not in responded]

    def is_fully_ratified(self) -> bool:
        return set(self.party_ids).issubset(set(self.accepted_by))

    def to_dict(self) -> dict:
        return {
            "agreement_id":       self.agreement_id,
            "room_id":            self.room_id,
            "proposer_id":        self.proposer_id,
            "description":        self.description,
            "party_ids":          self.party_ids,
            "accepted_by":        self.accepted_by,
            "rejected_by":        self.rejected_by,
            "status":             self.status.value,
            "linked_game_action": self.linked_game_action,
            "created_at":         self.created_at.isoformat(),
            "resolved_at":        self.resolved_at.isoformat() if self.resolved_at else None,
        }
