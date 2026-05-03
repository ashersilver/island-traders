"""
ChatService — all chat business logic.

Sits between the API layer (CLI or future WebSocket) and the ChatStore.
Never touches the network directly; callers handle I/O and serialisation.
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone

from .models import (
    Agreement, AgreementStatus, ChatMessage, ChatRoom, MessageType,
)
from .store import ChatStore


class ChatError(Exception):
    pass


class ChatService:
    def __init__(self, store: ChatStore) -> None:
        self._store = store

    # ------------------------------------------------------------------
    # Rooms
    # ------------------------------------------------------------------

    def create_room(
        self,
        name: str,
        creator_id: int,
        participant_ids: list[int] | None = None,
        is_private: bool = True,
    ) -> ChatRoom:
        """
        Create a new chat room. The creator is always included as a participant.
        Private rooms require an explicit invite; public rooms anyone can join.
        """
        participants = list({creator_id} | set(participant_ids or []))
        room = ChatRoom(
            room_id=str(uuid.uuid4()),
            name=name,
            created_by=creator_id,
            participant_ids=participants,
            is_private=is_private,
        )
        self._store.save_room(room)
        self._system(room.room_id, f"Room '{name}' created.")
        return room

    def join_room(self, room_id: str, player_id: int, player_name: str) -> ChatRoom:
        room = self._require_room(room_id)
        if room.is_private and player_id not in room.participant_ids:
            raise ChatError(f"Room '{room.name}' is private — you need an invitation.")
        if player_id not in room.participant_ids:
            room.participant_ids.append(player_id)
            self._store.add_participant(room_id, player_id)
            self._system(room_id, f"{player_name} joined the room.")
        return room

    def invite_to_room(
        self, room_id: str, inviter_id: int, invitee_id: int, invitee_name: str
    ) -> None:
        room = self._require_room(room_id)
        if inviter_id not in room.participant_ids:
            raise ChatError("Only participants can invite others.")
        if invitee_id not in room.participant_ids:
            room.participant_ids.append(invitee_id)
            self._store.add_participant(room_id, invitee_id)
            self._system(room_id, f"{invitee_name} was invited to the room.")

    def leave_room(self, room_id: str, player_id: int, player_name: str) -> None:
        self._require_participant(room_id, player_id)
        self._store.remove_participant(room_id, player_id)
        self._system(room_id, f"{player_name} left the room.")

    def get_rooms_for_player(self, player_id: int) -> list[ChatRoom]:
        return self._store.list_rooms_for_player(player_id)

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    def send_message(
        self,
        room_id: str,
        sender_id: int,
        sender_name: str,
        content: str,
        message_type: MessageType = MessageType.CHAT,
    ) -> ChatMessage:
        self._require_participant(room_id, sender_id)
        msg = ChatMessage(
            message_id=0,   # assigned by store
            room_id=room_id,
            sender_id=sender_id,
            sender_name=sender_name,
            content=content,
            message_type=message_type,
        )
        return self._store.save_message(msg)

    def get_messages(
        self, room_id: str, player_id: int, since_id: int = 0
    ) -> list[ChatMessage]:
        self._require_participant(room_id, player_id)
        return self._store.get_messages(room_id, since_id)

    # ------------------------------------------------------------------
    # Agreements (one-turn accept/reject)
    # ------------------------------------------------------------------

    def propose_agreement(
        self,
        room_id: str,
        proposer_id: int,
        proposer_name: str,
        description: str,
        party_ids: list[int],       # all players who must respond (include proposer if desired)
        linked_game_action: str | None = None,
    ) -> Agreement:
        """
        Post a formal agreement proposal to the room.
        The proposer auto-accepts. All other parties must respond on their next turn.
        """
        self._require_participant(room_id, proposer_id)
        all_parties = list({proposer_id} | set(party_ids))
        ag = Agreement(
            agreement_id=0,
            room_id=room_id,
            proposer_id=proposer_id,
            description=description,
            party_ids=all_parties,
            accepted_by=[proposer_id],   # proposer implicitly accepts their own proposal
            linked_game_action=linked_game_action,
        )
        ag = self._store.save_agreement(ag)

        # Post a PROPOSAL message to the room so everyone sees it
        notice = (
            f"📋 AGREEMENT PROPOSED by {proposer_name} [#{ag.agreement_id}]\n"
            f"Terms: {description}\n"
            f"Parties: {party_ids}\n"
            f"Respond with accept or reject on your turn."
        )
        self._store.save_message(ChatMessage(
            message_id=0,
            room_id=room_id,
            sender_id=proposer_id,
            sender_name=proposer_name,
            content=notice,
            message_type=MessageType.PROPOSAL,
        ))
        return ag

    def accept_agreement(
        self, agreement_id: int, player_id: int, player_name: str
    ) -> Agreement:
        ag = self._require_agreement(agreement_id)
        if ag.status != AgreementStatus.PENDING:
            raise ChatError(f"Agreement #{agreement_id} is already {ag.status.value}.")
        if player_id not in ag.party_ids:
            raise ChatError("You are not a party to this agreement.")
        if player_id in ag.accepted_by or player_id in ag.rejected_by:
            raise ChatError("You have already responded to this agreement.")

        ag.accepted_by.append(player_id)
        if ag.is_fully_ratified():
            ag.status = AgreementStatus.RATIFIED
            ag.resolved_at = datetime.now(timezone.utc)
            self._system(
                ag.room_id,
                f"✅ Agreement #{agreement_id} RATIFIED — all parties accepted.\n"
                f"Terms: {ag.description}"
            )
        self._store.update_agreement(ag)
        return ag

    def reject_agreement(
        self, agreement_id: int, player_id: int, player_name: str
    ) -> Agreement:
        ag = self._require_agreement(agreement_id)
        if ag.status != AgreementStatus.PENDING:
            raise ChatError(f"Agreement #{agreement_id} is already {ag.status.value}.")
        if player_id not in ag.party_ids:
            raise ChatError("You are not a party to this agreement.")
        if player_id in ag.accepted_by or player_id in ag.rejected_by:
            raise ChatError("You have already responded to this agreement.")

        ag.rejected_by.append(player_id)
        ag.status = AgreementStatus.REJECTED
        ag.resolved_at = datetime.now(timezone.utc)
        self._store.update_agreement(ag)
        self._system(
            ag.room_id,
            f"❌ Agreement #{agreement_id} REJECTED by {player_name}.\n"
            f"Terms were: {ag.description}"
        )
        return ag

    def expire_pending_agreements(self, agreement_ids: list[int]) -> list[Agreement]:
        """Mark specific agreements as expired (called by game engine at season/turn end)."""
        expired = []
        for aid in agreement_ids:
            ag = self._store.get_agreement(aid)
            if ag and ag.status == AgreementStatus.PENDING:
                ag.status = AgreementStatus.EXPIRED
                ag.resolved_at = datetime.now(timezone.utc)
                self._store.update_agreement(ag)
                self._system(ag.room_id, f"⏰ Agreement #{aid} expired without full ratification.")
                expired.append(ag)
        return expired

    def get_pending_agreements_for_player(self, player_id: int) -> list[Agreement]:
        return self._store.list_pending_for_player(player_id)

    # ------------------------------------------------------------------
    # Chat Board — public record of all ratified agreements
    # ------------------------------------------------------------------

    def get_chat_board(self) -> list[Agreement]:
        """Return all ratified agreements (the shared public board)."""
        return self._store.list_ratified()

    def format_chat_board(self) -> str:
        ratified = self.get_chat_board()
        if not ratified:
            return "Chat Board: no agreements ratified yet."
        lines = ["=" * 56, "  ISLAND TRADERS — AGREEMENT BOARD", "=" * 56]
        for ag in ratified:
            ts = ag.resolved_at.strftime("%Y-%m-%d %H:%M") if ag.resolved_at else "?"
            lines.append(
                f"  #{ag.agreement_id:>3}  [{ts}]  Room: {ag.room_id[:8]}…"
            )
            lines.append(f"         {ag.description}")
            if ag.linked_game_action:
                lines.append(f"         → Game action: {ag.linked_game_action}")
            lines.append("")
        lines.append("=" * 56)
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_room(self, room_id: str) -> ChatRoom:
        room = self._store.get_room(room_id)
        if not room:
            raise ChatError(f"Room '{room_id}' not found.")
        return room

    def _require_participant(self, room_id: str, player_id: int) -> None:
        room = self._require_room(room_id)
        if player_id not in room.participant_ids:
            raise ChatError(f"Player {player_id} is not in room '{room.name}'.")

    def _require_agreement(self, agreement_id: int) -> Agreement:
        ag = self._store.get_agreement(agreement_id)
        if not ag:
            raise ChatError(f"Agreement #{agreement_id} not found.")
        return ag

    def _system(self, room_id: str, content: str) -> None:
        """Post a system notification into a room."""
        self._store.save_message(ChatMessage(
            message_id=0,
            room_id=room_id,
            sender_id=-1,
            sender_name="System",
            content=content,
            message_type=MessageType.SYSTEM,
        ))
