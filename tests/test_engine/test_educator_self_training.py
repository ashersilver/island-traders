"""Tests for Educator self-training (playtest 2026-05-15).

When the Educator player requests training of their own workforce, the
action should skip the educator-picker prompt, charge no fee, consume no
PassengerSeats / air ticket, and auto-approve + auto-dispatch the batch
immediately (1-season transit).
"""
from __future__ import annotations

from island_traders.cli.prompts import FakeIOAdapter
from island_traders.engine.production import ProductionEngine
from island_traders.engine.trading import TradingEngine
from island_traders.engine.turn import TurnManager, TurnResult
from island_traders.models.deal import DealLedger
from island_traders.models.market import Market
from island_traders.models.player import Player
from island_traders.models.resource import ResourceType
from island_traders.models.role import ROLES
from island_traders.models.training import TrainingRegistry, TrainingStatus


def _educator(num_workers: int = 4) -> Player:
    """Educator with `num_workers` unskilled workers ready to train."""
    p = Player(0, "Education Island", [ROLES["Educator"]], 100.0, is_human=True)
    # Add some unskilled workforce so there's something to train
    p.workforce.add_workers(num_workers, profession="Unskilled")
    return p


class SelfTrainingIO(FakeIOAdapter):
    """Scripts the prompt chain for _action_request_training.

    Sequence the engine asks for:
      1. choose_profession(target_profession)
      2. choose_quantity(count of workers to train)

    Self-training should NOT ask for choose_player (educator) or
    ask_dollop_amount (fee).
    """
    def __init__(self, profession: str, count: int):
        super().__init__()
        self.profession = profession
        self.count = count
        self.educator_picker_called = False
        self.dollop_amount_called = False

    def choose_profession(self, prompt, available):
        return self.profession if self.profession in available else available[0]

    def choose_quantity(self, prompt, min_qty, max_qty):
        return min(self.count, max_qty)

    def choose_player(self, prompt, players):
        # If we ever hit this on a self-training run, that's the bug we're fixing.
        self.educator_picker_called = True
        return players[0]

    def ask_dollop_amount(self, prompt, max_dollops):
        self.dollop_amount_called = True
        return 0.0


def _turn_manager(players, training, io):
    market = Market()
    return TurnManager(
        players=players,
        production_engine=ProductionEngine(),
        trading_engine=TradingEngine(market, DealLedger()),
        market=market,
        io_adapter=io,
        training=training,
    )


def test_self_training_skips_educator_picker_and_fee():
    educator = _educator()
    training = TrainingRegistry()
    io = SelfTrainingIO(profession="Professor", count=1)
    tm = _turn_manager([educator], training, io)

    result = TurnResult(educator.player_id, season=0, year=0)
    tm._action_request_training(educator, result, season_name="Spring", year=0)

    assert io.educator_picker_called is False, "self-training should skip the educator picker"
    assert io.dollop_amount_called is False, "self-training should not prompt for a fee"


def test_self_training_does_not_consume_passenger_seats():
    educator = _educator()
    # Deliberately give the Educator zero PassengerSeats.
    assert educator.inventory.get(ResourceType.PASSENGER_SEATS) == 0

    training = TrainingRegistry()
    io = SelfTrainingIO(profession="Professor", count=1)
    tm = _turn_manager([educator], training, io)

    result = TurnResult(educator.player_id, season=0, year=0)
    tm._action_request_training(educator, result, season_name="Spring", year=0)

    # The request should exist and be DISPATCHED (auto-approved + dispatched)
    requests = training.all_requests()
    assert len(requests) == 1
    req = requests[0]
    assert req.transport_mode == "self_training"
    assert req.dollops_to_educator == 0.0
    assert req.status == TrainingStatus.DISPATCHED
    # And no PassengerSeats were drained
    assert educator.inventory.get(ResourceType.PASSENGER_SEATS) == 0


def test_self_training_returns_after_one_season():
    educator = _educator()
    training = TrainingRegistry()
    io = SelfTrainingIO(profession="Professor", count=1)
    tm = _turn_manager([educator], training, io)

    # Submit in year 0 Spring (season_index 0)
    tm._action_request_training(
        educator, TurnResult(educator.player_id, season=0, year=0),
        season_name="Spring", year=0,
    )

    req = training.all_requests()[0]
    # Dispatched in Spring (season=0); return season = 0 + 1 = 1 (Summer)
    assert req.dispatched_year == 0
    assert req.dispatched_season == 0
    assert req.return_year == 0
    assert req.return_season == 1

    # Run process_returns at year 0 Summer — the batch should complete.
    completed = training.process_returns(year=0, season=1)
    assert len(completed) == 1
    assert completed[0].batch_id == req.batch_id
    assert completed[0].status == TrainingStatus.COMPLETED


def test_self_training_still_counts_against_university_capacity():
    """Self-training is on-island but should NOT bypass University capacity.
    After a self-training batch is submitted, the registry's
    `capacity_remaining` for that profession must drop."""
    educator = _educator(num_workers=8)
    training = TrainingRegistry()
    io = SelfTrainingIO(profession="Professor", count=1)
    tm = _turn_manager([educator], training, io)

    before = training.capacity_remaining(year=0, season=0, profession="Professor")
    tm._action_request_training(
        educator, TurnResult(educator.player_id, season=0, year=0),
        season_name="Spring", year=0,
    )
    after = training.capacity_remaining(year=0, season=0, profession="Professor")
    # One slot must have been consumed — proves self-training is NOT bypassing
    # the University cap.
    assert after == before - 1


def test_self_training_with_no_other_players_does_not_fail():
    """Solo-game / single-Educator scenario.  Before the fix, the action
    would print 'No Educator player in this game' and return — even though
    the Educator IS the player.  The fix should let self-training proceed."""
    educator = _educator()
    training = TrainingRegistry()
    io = SelfTrainingIO(profession="Professor", count=1)
    tm = _turn_manager([educator], training, io)

    tm._action_request_training(
        educator, TurnResult(educator.player_id, season=0, year=0),
        season_name="Spring", year=0,
    )
    assert len(training.all_requests()) == 1
