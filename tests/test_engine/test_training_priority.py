from __future__ import annotations

from island_traders.cli.prompts import FakeIOAdapter
from island_traders.engine.production import ProductionEngine
from island_traders.engine.trading import TradingEngine
from island_traders.engine.turn import TurnManager, TurnResult
from island_traders.models.deal import DealLedger
from island_traders.models.market import Market
from island_traders.models.player import Player
from island_traders.models.role import ROLES
from island_traders.models.training import TrainingRegistry


def _player(pid: int, role: str, name: str | None = None) -> Player:
    return Player(pid, name or role, [ROLES[role]], 100.0, is_human=True)


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


def _request(reg: TrainingRegistry, requester: Player, educator: Player, prof: str):
    return reg.propose(
        requester_id=requester.player_id,
        worker_ids=[requester.player_id * 10 + reg._next_id],
        educator_id=educator.player_id,
        dollops_to_educator=0.0,
        target_profession=prof,
        year=0,
        season=0,
        transport_mode="air_ticket",
    )


def test_pending_requests_sort_by_priority_then_batch_id():
    reg = TrainingRegistry()
    educator = _player(1, "Educator")
    farmer = _player(2, "Farmer")
    req0 = _request(reg, farmer, educator, "Farmer")
    req1 = _request(reg, farmer, educator, "Mechanic")
    req2 = _request(reg, farmer, educator, "Horticulturalist")

    req2.priority = -1
    req1.priority = 2

    assert [
        req.batch_id for req in reg.sorted_pending_for_educator(educator.player_id)
    ] == [req2.batch_id, req0.batch_id, req1.batch_id]


class ReorderIO(FakeIOAdapter):
    def __init__(self, order):
        super().__init__()
        self.order = order

    def choose_training_queue_order(self, queue):
        return self.order


def test_reorder_training_queue_action_preserves_order_across_seasons():
    reg = TrainingRegistry()
    educator = _player(1, "Educator")
    farmer = _player(2, "Farmer")
    req0 = _request(reg, farmer, educator, "Farmer")
    req1 = _request(reg, farmer, educator, "Mechanic")
    req2 = _request(reg, farmer, educator, "Horticulturalist")
    manager = _manager([educator, farmer], reg, ReorderIO([req2.batch_id, req0.batch_id, req1.batch_id]))

    manager._action_reorder_training_queue(
        educator, TurnResult(educator.player_id, season=0, year=0)
    )

    assert [
        req.batch_id for req in reg.sorted_pending_for_educator(educator.player_id)
    ] == [req2.batch_id, req0.batch_id, req1.batch_id]
    assert [
        req.batch_id for req in reg.sorted_pending_for_educator(educator.player_id)
    ] == [req2.batch_id, req0.batch_id, req1.batch_id]


def test_ai_educator_processes_sorted_queue_order():
    reg = TrainingRegistry()
    educator = _player(1, "Educator")
    educator.is_human = False
    farmer = _player(2, "Farmer")
    req0 = _request(reg, farmer, educator, "Farmer")
    req1 = _request(reg, farmer, educator, "Mechanic")
    req1.priority = -1
    result = TurnResult(educator.player_id, season=0, year=0)
    manager = _manager([educator, farmer], reg)

    manager._ai_review_training_queue(educator, result, "Spring", 0)

    assert result.actions_taken == [
        f"ai_training_review:batch#{req1.batch_id}:rejected",
        f"ai_training_review:batch#{req0.batch_id}:rejected",
    ]


def test_new_request_defaults_to_priority_zero():
    reg = TrainingRegistry()
    educator = _player(1, "Educator")
    farmer = _player(2, "Farmer")

    req = _request(reg, farmer, educator, "Farmer")

    assert req.priority == 0
