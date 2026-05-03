"""Tests for ChatService using an in-memory SQLite database."""
import pytest
from island_traders.chat.store import SQLiteChatStore
from island_traders.chat.service import ChatService, ChatError
from island_traders.chat.models import AgreementStatus, MessageType


@pytest.fixture
def svc(tmp_path):
    store = SQLiteChatStore(db_path=str(tmp_path / "test_chat.db"))
    return ChatService(store)


def test_create_room(svc):
    room = svc.create_room("Trade Talk", creator_id=1, participant_ids=[2, 3])
    assert room.room_id
    assert 1 in room.participant_ids
    assert 2 in room.participant_ids
    assert room.is_private is True


def test_send_and_retrieve_messages(svc):
    room = svc.create_room("Negotiation", creator_id=1, participant_ids=[2])
    svc.send_message(room.room_id, 1, "Alice", "I offer 3 Oil for 2 Freight")
    svc.send_message(room.room_id, 2, "Bob",   "Counter: 3 Oil for 3 Freight")
    msgs = svc.get_messages(room.room_id, player_id=1)
    chat_msgs = [m for m in msgs if m.message_type == MessageType.CHAT]
    assert len(chat_msgs) == 2
    assert "3 Oil" in chat_msgs[0].content


def test_get_messages_since_id(svc):
    room = svc.create_room("Room", creator_id=1, participant_ids=[2])
    m1 = svc.send_message(room.room_id, 1, "Alice", "first")
    svc.send_message(room.room_id, 2, "Bob", "second")
    msgs = svc.get_messages(room.room_id, player_id=1, since_id=m1.message_id)
    contents = [m.content for m in msgs]
    assert "first" not in contents
    assert "second" in contents


def test_non_participant_cannot_send(svc):
    room = svc.create_room("Private", creator_id=1)
    with pytest.raises(ChatError):
        svc.send_message(room.room_id, 99, "Outsider", "hello")


def test_private_room_join_blocked(svc):
    room = svc.create_room("Private", creator_id=1, is_private=True)
    with pytest.raises(ChatError):
        svc.join_room(room.room_id, 99, "Stranger")


def test_invite_then_join(svc):
    room = svc.create_room("Invite Room", creator_id=1)
    svc.invite_to_room(room.room_id, inviter_id=1, invitee_id=2, invitee_name="Bob")
    refreshed = svc.get_rooms_for_player(2)
    assert any(r.room_id == room.room_id for r in refreshed)


def test_propose_agreement_proposer_auto_accepts(svc):
    room = svc.create_room("Deal", creator_id=1, participant_ids=[2])
    ag = svc.propose_agreement(
        room.room_id, proposer_id=1, proposer_name="Alice",
        description="Alice gives 3 Oil; Bob gives 2 Freight",
        party_ids=[1, 2],
    )
    assert ag.status == AgreementStatus.PENDING
    assert 1 in ag.accepted_by   # proposer auto-accepts


def test_agreement_ratified_when_all_accept(svc):
    room = svc.create_room("Deal", creator_id=1, participant_ids=[2])
    ag = svc.propose_agreement(
        room.room_id, 1, "Alice",
        "Alice gives 3 Oil; Bob gives 2 Freight",
        party_ids=[1, 2],
    )
    ag = svc.accept_agreement(ag.agreement_id, player_id=2, player_name="Bob")
    assert ag.status == AgreementStatus.RATIFIED
    assert ag.resolved_at is not None


def test_agreement_rejected(svc):
    room = svc.create_room("Deal", creator_id=1, participant_ids=[2])
    ag = svc.propose_agreement(
        room.room_id, 1, "Alice", "Bad deal", party_ids=[1, 2]
    )
    ag = svc.reject_agreement(ag.agreement_id, player_id=2, player_name="Bob")
    assert ag.status == AgreementStatus.REJECTED


def test_chat_board_shows_ratified(svc):
    room = svc.create_room("Deal", creator_id=1, participant_ids=[2])
    ag = svc.propose_agreement(
        room.room_id, 1, "Alice", "Ratified deal", party_ids=[1, 2]
    )
    svc.accept_agreement(ag.agreement_id, player_id=2, player_name="Bob")
    board = svc.get_chat_board()
    assert len(board) == 1
    assert board[0].description == "Ratified deal"


def test_pending_agreements_for_player(svc):
    room = svc.create_room("Room", creator_id=1, participant_ids=[2, 3])
    ag = svc.propose_agreement(
        room.room_id, 1, "Alice", "Terms", party_ids=[1, 2, 3]
    )
    # Player 2 has not responded yet
    pending = svc.get_pending_agreements_for_player(2)
    assert any(a.agreement_id == ag.agreement_id for a in pending)
    # Player 1 already accepted (proposer auto-accept), not in pending
    pending1 = svc.get_pending_agreements_for_player(1)
    assert not any(a.agreement_id == ag.agreement_id for a in pending1)


def test_expire_agreement(svc):
    room = svc.create_room("Room", creator_id=1, participant_ids=[2])
    ag = svc.propose_agreement(
        room.room_id, 1, "Alice", "Will expire", party_ids=[1, 2]
    )
    expired = svc.expire_pending_agreements([ag.agreement_id])
    assert len(expired) == 1
    assert expired[0].status == AgreementStatus.EXPIRED


def test_linked_game_action_recorded(svc):
    room = svc.create_room("Training Negotiation", creator_id=1, participant_ids=[2])
    ag = svc.propose_agreement(
        room.room_id, 1, "Farmer",
        "Send 2 workers to Education Island. Farmer pays 40g to Educator.",
        party_ids=[1, 2],
        linked_game_action="training_request:0",
    )
    svc.accept_agreement(ag.agreement_id, 2, "Educator")
    board = svc.get_chat_board()
    assert board[0].linked_game_action == "training_request:0"


def test_rooms_listed_for_player(svc):
    r1 = svc.create_room("Room A", creator_id=1, participant_ids=[2])
    r2 = svc.create_room("Room B", creator_id=2, participant_ids=[3])
    rooms_for_1 = svc.get_rooms_for_player(1)
    ids = [r.room_id for r in rooms_for_1]
    assert r1.room_id in ids
    assert r2.room_id not in ids
