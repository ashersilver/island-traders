from __future__ import annotations

from island_traders.cli.prompts import FakeIOAdapter
from island_traders.engine.game import Game, GameConfig, PlayerSpec
from island_traders.engine.production import ProductionEngine
from island_traders.engine.turn import TurnManager
from island_traders.models.market import Market
from island_traders.models.profession import Profession
from island_traders.models.training import TrainingRegistry, TrainingStatus


def _game() -> Game:
    game = Game(
        GameConfig([
            PlayerSpec("Farmer", ["Farmer"]),
            PlayerSpec("Doctor", ["Doctor"]),
        ]),
        FakeIOAdapter(),
    )
    game.setup()
    return game


def test_cancel_training_request_removes_pending_and_refunds_fee():
    game = _game()
    requester, educator = game.players
    worker = requester.workforce.active_workers[0]
    training = TrainingRegistry()
    req = training.propose(
        requester_id=requester.player_id,
        worker_ids=[worker.worker_id],
        educator_id=educator.player_id,
        dollops_to_educator=25.0,
        target_profession=Profession.FARMER.value,
        student_loan_requested=False,
    )
    req.loan_financed = False
    before = requester.dollops
    manager = TurnManager(
        [requester, educator],
        ProductionEngine(),
        None,
        Market(),
        FakeIOAdapter(),
        training,
    )

    result = manager.cancel_training_request(requester, req.batch_id)

    assert result == {"ok": True, "training_id": req.batch_id, "refunded": 25.0}
    assert req.status == TrainingStatus.REJECTED
    assert requester.dollops == before + 25.0


def test_cancel_training_started_request_fails():
    game = _game()
    requester, educator = game.players
    worker = requester.workforce.active_workers[0]
    training = TrainingRegistry()
    req = training.propose(
        requester_id=requester.player_id,
        worker_ids=[worker.worker_id],
        educator_id=educator.player_id,
        dollops_to_educator=25.0,
        target_profession=Profession.FARMER.value,
    )
    training.educator_approve(req.batch_id)
    manager = TurnManager(
        [requester, educator],
        ProductionEngine(),
        None,
        Market(),
        FakeIOAdapter(),
        training,
    )

    result = manager.cancel_training_request(requester, req.batch_id)

    assert result["ok"] is False
    assert req.status == TrainingStatus.AWAITING_TRANSPORT


def test_worker_transfer_accept_decline_validation_and_expiry():
    game = _game()
    sender, receiver = game.players
    sender.dollops = 100.0
    receiver.dollops = 500.0
    sender.workforce.add_workers(
        2,
        training_level=1,
        profession=Profession.FARMER.value,
    )

    offer = game.create_transfer_offer(
        from_player=sender,
        to_player=receiver,
        profession=Profession.FARMER.value,
        count=2,
        fee_per_head=20.0,
        direction="offer",
        expires_season=2,
    )
    assert game.transfer_offers == [offer]

    result = game.resolve_transfer_offer(receiver, offer.offer_id, True)

    assert result["ok"] is True
    assert result["workers_moved"] == 2
    assert sender.dollops == 140.0
    assert receiver.dollops == 460.0
    assert receiver.count_workers(Profession.FARMER.value) >= 2

    decline = game.create_transfer_offer(
        from_player=sender,
        to_player=receiver,
        profession=Profession.FARMER.value,
        count=1,
        fee_per_head=1.0,
        direction="offer",
        expires_season=2,
    )
    declined = game.resolve_transfer_offer(receiver, decline.offer_id, False)
    assert declined == {"ok": True, "accepted": False, "offer_id": decline.offer_id}
    assert decline.status == "declined"

    too_many = game.create_transfer_offer(
        from_player=sender,
        to_player=receiver,
        profession=Profession.DOCTOR.value,
        count=999,
        fee_per_head=1.0,
        direction="offer",
        expires_season=2,
    )
    assert game.resolve_transfer_offer(receiver, too_many.offer_id, True)["ok"] is False

    unaffordable = game.create_transfer_offer(
        from_player=receiver,
        to_player=sender,
        profession=Profession.FARMER.value,
        count=1,
        fee_per_head=9999.0,
        direction="offer",
        expires_season=2,
    )
    assert game.resolve_transfer_offer(sender, unaffordable.offer_id, True)["ok"] is False

    expiring = game.create_transfer_offer(
        from_player=sender,
        to_player=receiver,
        profession=Profession.UNSKILLED.value,
        count=1,
        fee_per_head=1.0,
        direction="offer",
        expires_season=0,
    )
    game.expire_transfer_offers(1)
    assert expiring.status == "expired"


def test_count_workers_unskilled_uses_population_minus_workforce():
    game = _game()
    player = game.players[0]
    player.population = 75
    assert player.count_workers(Profession.UNSKILLED.value) == 75 - player.workforce.count
