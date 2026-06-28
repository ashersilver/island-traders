from __future__ import annotations

from types import SimpleNamespace

from island_traders.cli.prompts import FakeIOAdapter
from island_traders.engine.production import ProductionEngine
from island_traders.engine.trading import TradingEngine
from island_traders.engine.turn import TurnManager, TurnResult
from island_traders.models.deal import DealLedger
from island_traders.models.market import Market
from island_traders.models.player import Player
from island_traders.models.role import ROLES
from island_traders.models.training import TrainingRegistry, TrainingStatus
from island_traders.server.app import GameManager


def _player(pid: int, role: str, name: str | None = None) -> Player:
    return Player(pid, name or role, [ROLES[role]], 100.0, is_human=True)


def _request(reg: TrainingRegistry, requester: Player, educator: Player):
    return reg.propose(
        requester_id=requester.player_id,
        worker_ids=[requester.player_id * 100 + reg._next_id],
        educator_id=educator.player_id,
        dollops_to_educator=10.0,
        target_profession="Mechanic",
        year=0,
        season=0,
        transport_mode="air_ticket",
    )


def _manager(players, training, io=None) -> TurnManager:
    market = Market()
    return TurnManager(
        players=players,
        production_engine=ProductionEngine(),
        trading_engine=TradingEngine(market, DealLedger()),
        market=market,
        io_adapter=io or FakeIOAdapter(),
        training=training,
    )


class QueueActionIO(FakeIOAdapter):
    def __init__(self, batch_id, amount=0.0, reason="Needs a stronger bid"):
        super().__init__()
        self.batch_id = batch_id
        self.amount = amount
        self.reason = reason

    def choose_option(self, prompt, options, request_summary=None):
        return self.batch_id

    def ask_text(self, prompt, default=""):
        return self.reason

    def ask_dollop_amount(self, prompt, max_dollops, prefill=0.0):
        return self.amount


def test_reject_training_request_from_queue_stores_decline_reason():
    reg = TrainingRegistry()
    educator = _player(1, "Educator")
    farmer = _player(2, "Farmer")
    req = _request(reg, farmer, educator)
    manager = _manager([educator, farmer], reg, QueueActionIO(req.batch_id, reason="No seats"))

    manager._action_reject_training_request(
        educator, TurnResult(educator.player_id, 0, 0), year=0, season_index=1
    )

    assert req.status == TrainingStatus.REJECTED
    assert req.decline_reason == "No seats"
    assert req.decline_year == 0
    assert req.decline_season == 1


def test_counter_training_request_from_queue_updates_offer_values():
    reg = TrainingRegistry()
    educator = _player(1, "Educator")
    farmer = _player(2, "Farmer")
    req = _request(reg, farmer, educator)
    manager = _manager([educator, farmer], reg, QueueActionIO(req.batch_id, amount=75.0, reason="75 Dp works"))

    manager._action_counter_training_request(
        educator, TurnResult(educator.player_id, 0, 0), year=0, season_index=2
    )

    assert req.status == TrainingStatus.COUNTERED
    assert req.original_dollops_to_educator == 10.0
    assert req.dollops_to_educator == 75.0
    assert req.counter_message == "75 Dp works"
    assert req.decline_reason == "75 Dp works"


def test_training_decisions_payload_and_ack():
    reg = TrainingRegistry()
    educator = _player(1, "Educator", "Education")
    farmer = _player(2, "Farmer", "Agriculture")
    req = _request(reg, farmer, educator)
    reg.educator_counter(req.batch_id, 80.0, "More please", "More please", 0, 0)
    game = SimpleNamespace(players=[educator, farmer], training=reg)
    gm = GameManager()

    decisions = gm._training_decisions_for_player(game, farmer.player_id, 0, 0)

    assert decisions == [{
        "batch_id": req.batch_id,
        "status": "countered",
        "decline_reason": "More please",
        "decline_year": 1,
        "decline_season": "Spring",
        "original_offer": 10.0,
        "suggested_offer_if_any": 80.0,
        "target_profession": "Mechanic",
        "n_workers": 1,
        "student_loan_requested": False,
    }]
    manager = _manager([educator, farmer], reg, QueueActionIO(req.batch_id))
    manager._action_ack_training_decision(
        farmer, TurnResult(farmer.player_id, 0, 0)
    )
    assert gm._training_decisions_for_player(game, farmer.player_id, 0, 0) == []


def test_non_educator_cannot_reject_queue_request():
    reg = TrainingRegistry()
    educator = _player(1, "Educator")
    farmer = _player(2, "Farmer")
    req = _request(reg, farmer, educator)
    manager = _manager([educator, farmer], reg, QueueActionIO(req.batch_id))

    manager._action_reject_training_request(
        farmer, TurnResult(farmer.player_id, 0, 0), year=0, season_index=0
    )

    assert req.status == TrainingStatus.AWAITING_EDUCATOR


def test_ai_educator_rejection_populates_decline_reason():
    reg = TrainingRegistry()
    educator = _player(1, "Educator")
    educator.is_human = False
    farmer = _player(2, "Farmer")
    req = _request(reg, farmer, educator)
    manager = _manager([educator, farmer], reg)

    manager._ai_educator_respond(educator, farmer, req, "Spring", 0)

    assert req.status == TrainingStatus.REJECTED
    assert "AI fair-rate threshold" in req.decline_reason
