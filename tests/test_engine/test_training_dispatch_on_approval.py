"""Workers must only depart for training once it is approved.

Playtest 2026-05-29: requesting training made the workers vanish from the
requester's island the instant they clicked "Request Training" — before any
approval. Root cause: an AI Educator approved AND dispatched inside the
*requester's* turn. They must instead stay home (producing) until the Educator
approves on the Educator's own turn.
"""
from __future__ import annotations

from island_traders.cli.prompts import FakeIOAdapter
from island_traders.engine.game import Game, GameConfig, PlayerSpec
from island_traders.engine.production import ProductionEngine
from island_traders.engine.trading import TradingEngine
from island_traders.engine.turn import TurnManager, TurnResult
from island_traders.models.deal import DealLedger
from island_traders.models.market import Market
from island_traders.models.player import Player
from island_traders.models.profession import Profession
from island_traders.models.resource import ResourceType
from island_traders.models.role import ROLES
from island_traders.models.training import TrainingRegistry


class _AutoIO(FakeIOAdapter):
    def choose_profession(self, prompt, available):
        return available[0]

    def choose_quantity(self, prompt, mn, mx):
        return 1

    def choose_player(self, prompt, players):
        return players[0]

    def ask_dollop_amount(self, prompt, mx, prefill=0.0):
        return 50.0

    def confirm(self, prompt, request_summary=None):
        return True

    def choose_option(self, prompt, options, request_summary=None):
        return options[0]["value"]


def _game(educator_human: bool) -> Game:
    cfg = GameConfig(num_years=1, player_specs=[
        PlayerSpec(name="Farmer", role_names=["Farmer"], is_human=True),
        PlayerSpec(name="Educator", role_names=["Educator"], is_human=educator_human),
    ])
    g = Game(cfg, _AutoIO())
    g.setup()
    return g


def test_request_does_not_dispatch_workers_with_ai_educator():
    g = _game(educator_human=False)
    farmer, educator = g.players
    educator.receive_resources(ResourceType.REAGENTS, 2)
    res = TurnResult(player_id=farmer.player_id, season="Spring", year=0)

    g.turn_manager._action_request_training(farmer, res, "Spring", 0)

    reqs = g.training.active_for_player(farmer.player_id)
    assert reqs, "a training request should have been created"
    # Workers stay home until approval — none in training yet.
    assert farmer.workforce.training_count == 0
    assert all(r.status.value == "awaiting_educator" for r in reqs)


def test_ai_educator_approves_and_dispatches_on_its_own_turn():
    g = _game(educator_human=False)
    farmer, educator = g.players
    educator.receive_resources(ResourceType.REAGENTS, 2)
    res = TurnResult(player_id=farmer.player_id, season="Spring", year=0)
    g.turn_manager._action_request_training(farmer, res, "Spring", 0)
    assert farmer.workforce.training_count == 0

    # The AI Educator processes its queue on its OWN turn -> approve + dispatch.
    res2 = TurnResult(player_id=educator.player_id, season="Spring", year=0)
    g.turn_manager._ai_review_training_queue(educator, res2, "Spring", 0)

    assert farmer.workforce.training_count == 1
    reqs = g.training.active_for_player(farmer.player_id)
    assert any(r.status.value == "dispatched" for r in reqs)


def test_request_does_not_dispatch_workers_with_human_educator():
    g = _game(educator_human=True)
    farmer, educator = g.players
    res = TurnResult(player_id=farmer.player_id, season="Spring", year=0)

    g.turn_manager._action_request_training(farmer, res, "Spring", 0)

    assert farmer.workforce.training_count == 0
    reqs = g.training.active_for_player(farmer.player_id)
    assert all(r.status.value == "awaiting_educator" for r in reqs)


def test_dispatch_rebinds_training_request_to_active_eligible_workers():
    farmer = Player(0, "Agricola", [ROLES["Farmer"]], 100.0, is_human=True)
    farmer.workforce.workers.clear()
    farmer.workforce._next_id = 0
    farmer.workforce.add_workers(4, profession=Profession.UNSKILLED.value)
    training = TrainingRegistry()
    req = training.propose(
        requester_id=farmer.player_id,
        worker_ids=[0, 1],
        educator_id=999,
        dollops_to_educator=40.0,
        target_profession=Profession.FARMING_TECHNICIAN.value,
        year=0,
        season=0,
        transport_mode="air_ticket",
    )
    training.educator_approve(req.batch_id)
    # Workplace injuries reuse in-training absence. The originally pinned
    # workers are unavailable, but two equivalent unskilled workers remain.
    farmer.workforce.dispatch_for_training([0, 1])

    market = Market()
    tm = TurnManager(
        players=[farmer],
        production_engine=ProductionEngine(),
        trading_engine=TradingEngine(market, DealLedger()),
        market=market,
        io_adapter=FakeIOAdapter(),
        training=training,
    )

    assert tm._dispatch_training(farmer, req, "Spring", 0) is True
    assert req.worker_ids == [2, 3]
    assert {w.worker_id for w in farmer.workforce.active_workers} == set()
