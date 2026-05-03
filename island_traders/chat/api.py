"""
ChatAPI — transport-agnostic request/response interface.

All methods accept plain Python dicts (JSON-serialisable) and return
response dicts with a standard envelope:

    {"ok": True,  "data": {...}}
    {"ok": False, "error": "message"}

This makes it trivial to wire up a WebSocket or REST transport later:
each WS message or HTTP request maps to one handle_* call.

Current usage: called directly by the CLI session layer.
Future usage:  WebSocket handler calls these methods and sends the
               returned dict back over the socket.

WebSocket event names (for reference when adding the network layer):
  Client → Server:
    "chat.create_room"        payload: {name, participant_ids, is_private}
    "chat.join_room"          payload: {room_id}
    "chat.invite"             payload: {room_id, invitee_id}
    "chat.send"               payload: {room_id, content}
    "chat.messages"           payload: {room_id, since_id}
    "chat.rooms"              payload: {}
    "chat.propose_agreement"  payload: {room_id, description, party_ids, linked_game_action}
    "chat.accept_agreement"   payload: {agreement_id}
    "chat.reject_agreement"   payload: {agreement_id}
    "chat.board"              payload: {}
    "chat.pending"            payload: {}

  Server → all room participants (broadcast):
    "chat.message"            payload: ChatMessage.to_dict()
    "chat.agreement_update"   payload: Agreement.to_dict()
"""
from __future__ import annotations
from .service import ChatService, ChatError
from .models import MessageType


class ChatAPI:
    def __init__(self, service: ChatService) -> None:
        self._svc = service

    # ------------------------------------------------------------------
    # Rooms
    # ------------------------------------------------------------------

    def handle_create_room(
        self,
        creator_id: int,
        creator_name: str,
        name: str,
        participant_ids: list[int] | None = None,
        is_private: bool = True,
    ) -> dict:
        try:
            room = self._svc.create_room(name, creator_id, participant_ids, is_private)
            return {"ok": True, "data": room.to_dict()}
        except ChatError as e:
            return {"ok": False, "error": str(e)}

    def handle_join_room(
        self, room_id: str, player_id: int, player_name: str
    ) -> dict:
        try:
            room = self._svc.join_room(room_id, player_id, player_name)
            return {"ok": True, "data": room.to_dict()}
        except ChatError as e:
            return {"ok": False, "error": str(e)}

    def handle_invite(
        self,
        room_id: str,
        inviter_id: int,
        invitee_id: int,
        invitee_name: str,
    ) -> dict:
        try:
            self._svc.invite_to_room(room_id, inviter_id, invitee_id, invitee_name)
            return {"ok": True, "data": {"room_id": room_id, "invitee_id": invitee_id}}
        except ChatError as e:
            return {"ok": False, "error": str(e)}

    def handle_leave_room(
        self, room_id: str, player_id: int, player_name: str
    ) -> dict:
        try:
            self._svc.leave_room(room_id, player_id, player_name)
            return {"ok": True, "data": {"room_id": room_id}}
        except ChatError as e:
            return {"ok": False, "error": str(e)}

    def handle_get_rooms(self, player_id: int) -> dict:
        rooms = self._svc.get_rooms_for_player(player_id)
        return {"ok": True, "data": {"rooms": [r.to_dict() for r in rooms]}}

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    def handle_send_message(
        self,
        room_id: str,
        sender_id: int,
        sender_name: str,
        content: str,
    ) -> dict:
        try:
            msg = self._svc.send_message(room_id, sender_id, sender_name, content)
            return {"ok": True, "data": msg.to_dict()}
        except ChatError as e:
            return {"ok": False, "error": str(e)}

    def handle_get_messages(
        self, room_id: str, player_id: int, since_id: int = 0
    ) -> dict:
        try:
            msgs = self._svc.get_messages(room_id, player_id, since_id)
            return {"ok": True, "data": {"messages": [m.to_dict() for m in msgs]}}
        except ChatError as e:
            return {"ok": False, "error": str(e)}

    # ------------------------------------------------------------------
    # Agreements
    # ------------------------------------------------------------------

    def handle_propose_agreement(
        self,
        room_id: str,
        proposer_id: int,
        proposer_name: str,
        description: str,
        party_ids: list[int],
        linked_game_action: str | None = None,
    ) -> dict:
        try:
            ag = self._svc.propose_agreement(
                room_id, proposer_id, proposer_name, description, party_ids, linked_game_action
            )
            return {"ok": True, "data": ag.to_dict()}
        except ChatError as e:
            return {"ok": False, "error": str(e)}

    def handle_accept_agreement(
        self, agreement_id: int, player_id: int, player_name: str
    ) -> dict:
        try:
            ag = self._svc.accept_agreement(agreement_id, player_id, player_name)
            return {"ok": True, "data": ag.to_dict()}
        except ChatError as e:
            return {"ok": False, "error": str(e)}

    def handle_reject_agreement(
        self, agreement_id: int, player_id: int, player_name: str
    ) -> dict:
        try:
            ag = self._svc.reject_agreement(agreement_id, player_id, player_name)
            return {"ok": True, "data": ag.to_dict()}
        except ChatError as e:
            return {"ok": False, "error": str(e)}

    def handle_get_pending(self, player_id: int) -> dict:
        pending = self._svc.get_pending_agreements_for_player(player_id)
        return {"ok": True, "data": {"agreements": [a.to_dict() for a in pending]}}

    def handle_get_board(self) -> dict:
        board_text = self._svc.format_chat_board()
        ratified = self._svc.get_chat_board()
        return {
            "ok": True,
            "data": {
                "formatted": board_text,
                "agreements": [a.to_dict() for a in ratified],
            },
        }
