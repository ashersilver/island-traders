"""Regression coverage for trainees actually re-joining the home workforce.

Bug observed in playtest 2026-05-24: workers dispatched for training stay in
the `dispatched` state past their `return_year` / `return_season` and never
come back as upgraded staff.

These tests pin down the contract on both sides of the integration:

- The registry-side ``process_returns`` flip already had per-method coverage
  (see ``test_educator_self_training``).
- The workforce-side flip already had per-method coverage (see
  ``test_education_phase3``).
- What was missing — and what this file adds — is the end-to-end seam:
  ``Game._process_training_returns`` is the per-season hook that wires the
  two together; if either side is out of sync it silently fails to mint
  the upgraded worker.
"""
from __future__ import annotations

from island_traders.cli.prompts import FakeIOAdapter
from island_traders.engine.game import Game, GameConfig, PlayerSpec
from island_traders.models.profession import Profession


def _farmer_educator_game() -> Game:
    """Two-island game (Farmer requester + Educator trainer) for end-to-end
    training-return coverage. Single year is enough — every test here
    dispatches at Y0/S0 and the longest course (Doctor, 3 seasons) returns
    at Y0/S3 — still within the year."""
    config = GameConfig(
        num_years=1,
        player_specs=[
            PlayerSpec(name="Farmer", role_names=["Farmer"], is_human=False),
            PlayerSpec(name="Educator", role_names=["Educator"], is_human=False),
        ],
    )
    game = Game(config, FakeIOAdapter())
    game.setup()
    return game


# ---------------------------------------------------------------------------
# Cross-island training round-trip
# ---------------------------------------------------------------------------

def _pick_unskilled_worker(player):
    """Pick an Unskilled worker if available, else any active worker.
    Starting workforces vary by role (Farmers seed some Farmer-tier
    workers); the round-trip behaviour is the same either way."""
    for w in player.workforce.active_workers:
        if w.profession == Profession.UNSKILLED.value:
            return w
    return player.workforce.active_workers[0]


def test_cross_island_trainee_returns_at_return_season_with_upgraded_profession():
    game = _farmer_educator_game()
    farmer, educator = game.players

    target = _pick_unskilled_worker(farmer)
    worker_id = target.worker_id
    starting_level = target.training_level
    assert not target.in_training

    # Nurse is Manager-band, EDUCATION_SEASONS[Nurse] = 1 season away.
    req = game.training.propose(
        requester_id=farmer.player_id, worker_ids=[worker_id],
        educator_id=educator.player_id, dollops_to_educator=10.0,
        target_profession=Profession.NURSE.value,
        year=0, season=0, transport_mode="air_ticket",
    )
    game.training.educator_approve(req.batch_id)
    game.training.arrange_transport(req.batch_id, transporter_id=educator.player_id)
    game.training.dispatch(req.batch_id, year=0, season=0, num_seasons=4)
    farmer.workforce.dispatch_for_training([worker_id])
    assert target.in_training
    assert req.return_year == 0 and req.return_season == 1

    # Wrong season — nothing happens.
    game._process_training_returns(year=0, season=0)
    assert target.in_training

    # Right season — worker rejoins the workforce.
    game._process_training_returns(year=0, season=1)
    worker = next(w for w in farmer.workforce.workers if w.worker_id == worker_id)
    assert not worker.in_training, (
        "Worker should be active again after their return tick"
    )
    # If the worker was Unskilled, they graduate into Nurse at level 1;
    # if they were already in a profession, they advance one level within
    # it (per Worker.train semantics).
    if target.profession == Profession.NURSE.value or worker.profession == Profession.NURSE.value:
        assert worker.training_level == 1
    else:
        assert worker.training_level == starting_level + 1


def test_cross_island_doctor_three_season_round_trip():
    """Doctor is Manager-tier with EDUCATION_SEASONS[Doctor] = 3.
    Verifies the longer course still releases the worker cleanly within
    the same year."""
    game = _farmer_educator_game()
    farmer, educator = game.players
    worker_id = _pick_unskilled_worker(farmer).worker_id

    req = game.training.propose(
        requester_id=farmer.player_id, worker_ids=[worker_id],
        educator_id=educator.player_id, dollops_to_educator=15.0,
        target_profession=Profession.DOCTOR.value,
        year=0, season=0, transport_mode="air_ticket",
    )
    game.training.educator_approve(req.batch_id)
    game.training.arrange_transport(req.batch_id, transporter_id=educator.player_id)
    game.training.dispatch(req.batch_id, year=0, season=0, num_seasons=4)
    farmer.workforce.dispatch_for_training([worker_id])
    assert req.return_year == 0 and req.return_season == 3

    # Walk the seasons; only S3 should release the worker.
    for s in (0, 1, 2):
        game._process_training_returns(year=0, season=s)
        worker = next(w for w in farmer.workforce.workers if w.worker_id == worker_id)
        assert worker.in_training, f"Doctor course should still be active at season {s}"

    game._process_training_returns(year=0, season=3)
    worker = next(w for w in farmer.workforce.workers if w.worker_id == worker_id)
    assert not worker.in_training


def test_three_trainees_return_home_with_new_profession():
    game = _farmer_educator_game()
    farmer, educator = game.players
    workers = farmer.workforce.add_workers(3)
    worker_ids = [worker.worker_id for worker in workers]

    req = game.training.propose(
        requester_id=farmer.player_id,
        worker_ids=worker_ids,
        educator_id=educator.player_id,
        dollops_to_educator=60.0,
        target_profession=Profession.NURSE.value,
        year=0,
        season=0,
        transport_mode="air_ticket",
    )
    game.training.educator_approve(req.batch_id)
    game.training.dispatch(req.batch_id, year=0, season=0, num_seasons=4)
    farmer.workforce.dispatch_for_training(worker_ids)

    game._process_training_returns(year=0, season=1)

    returned = [
        worker for worker in farmer.workforce.workers
        if worker.worker_id in worker_ids
    ]
    assert len(returned) == 3
    assert all(not worker.in_training for worker in returned)
    assert all(worker.profession == Profession.NURSE.value for worker in returned)
    assert all(worker.training_level == 1 for worker in returned)


def test_training_reconcile_clears_orphaned_in_training_flag_when_batch_removed():
    game = _farmer_educator_game()
    farmer, educator = game.players
    worker = _pick_unskilled_worker(farmer)
    worker_id = worker.worker_id

    req = game.training.propose(
        requester_id=farmer.player_id,
        worker_ids=[worker_id],
        educator_id=educator.player_id,
        dollops_to_educator=20.0,
        target_profession=Profession.NURSE.value,
        year=0,
        season=0,
        transport_mode="air_ticket",
    )
    game.training.educator_approve(req.batch_id)
    game.training.dispatch(req.batch_id, year=0, season=0, num_seasons=4)
    farmer.workforce.dispatch_for_training([worker_id])

    assert farmer.workforce.training_count == 1

    game.training.drop_worker(worker_id)
    assert worker.in_training

    game._reconcile_training_flags()

    assert not worker.in_training
    assert farmer.workforce.training_count == 0
    assert farmer.workforce.training_count == len(
        game.training.dispatched_worker_ids(farmer.player_id)
    )


def test_return_hook_repairs_missing_dispatched_flag_before_return():
    game = _farmer_educator_game()
    farmer, educator = game.players
    worker = _pick_unskilled_worker(farmer)
    req = game.training.propose(
        requester_id=farmer.player_id,
        worker_ids=[worker.worker_id],
        educator_id=educator.player_id,
        dollops_to_educator=20.0,
        target_profession=Profession.NURSE.value,
        year=0,
        season=0,
        transport_mode="air_ticket",
    )
    game.training.educator_approve(req.batch_id)
    game.training.dispatch(req.batch_id, year=0, season=0, num_seasons=4)
    assert not worker.in_training

    game._process_training_returns(year=0, season=1)

    output = "\n".join(game.io.printed)
    assert "Request #0 complete" in output
    assert "Return warning for request #0" not in output
    assert not worker.in_training
    assert worker.profession == Profession.NURSE.value


def test_dispatched_trainees_eat_on_campus_not_at_home():
    from island_traders.engine.turn import TurnManager
    from island_traders.engine.production import ProductionEngine
    from island_traders.engine.trading import TradingEngine
    from island_traders.models.deal import DealLedger
    from island_traders.models.market import Market
    from island_traders.models.resource import ResourceType

    game = _farmer_educator_game()
    farmer, educator = game.players
    farmer.receive_resources(ResourceType.FOOD, 20)
    educator.receive_resources(ResourceType.FOOD, 20)
    workers = farmer.workforce.add_workers(10)
    worker_ids = [worker.worker_id for worker in workers]
    req = game.training.propose(
        requester_id=farmer.player_id,
        worker_ids=worker_ids,
        educator_id=educator.player_id,
        dollops_to_educator=200.0,
        target_profession=Profession.NURSE.value,
        year=0,
        season=0,
        transport_mode="air_ticket",
    )
    game.training.educator_approve(req.batch_id)
    game.training.dispatch(req.batch_id, year=0, season=0, num_seasons=4)
    farmer.workforce.dispatch_for_training(worker_ids)

    market = Market()
    tm = TurnManager(
        players=[farmer, educator],
        production_engine=ProductionEngine(),
        trading_engine=TradingEngine(market, DealLedger()),
        market=market,
        io_adapter=FakeIOAdapter(),
        training=game.training,
    )
    tm._consume_and_post_sustenance()

    # Each island starts with STARTING_POPULATION = 50 residents. 10 of the
    # farmer's residents are away at training, so the farmer feeds 40. Campus
    # trainees consume 0.2 Food each, so 10 trainees add 20 resident-equivalents
    # to the Education island's basket demand: ceil((50 + 20) / 10) = 7 meals.
    assert farmer.inventory.get(ResourceType.FOOD) == 31  # 35 - ceil((50 - 10) / 10)
    assert educator.inventory.get(ResourceType.FOOD) == 13  # 20 - ceil((50 + 20) / 10)


# ---------------------------------------------------------------------------
# Self-training round-trip
# ---------------------------------------------------------------------------
#
# Bug: the self-training shortcut in turn.py::_action_request_training calls
# ``training.dispatch`` (registry side) but never calls
# ``workforce.dispatch_for_training`` (worker side).  At the return tick the
# registry flips to COMPLETED, but ``workforce.return_from_training`` is a
# no-op because it requires ``w.in_training == True``.  Net effect: a
# self-trained worker's ``training_level`` never advances.

def test_self_training_round_trip_advances_worker_training_level():
    """Exercises the actual _action_request_training self-training shortcut
    (the path turn.py takes when an Educator picks REQUEST_TRAINING) so the
    in_training marking + workforce return are wired end-to-end."""
    from island_traders.engine.turn import TurnResult
    from tests.test_engine.test_educator_self_training import (
        _educator, _turn_manager, SelfTrainingIO,
    )

    educator = _educator(num_workers=4, courses=5)
    # Snapshot the worker that the IO script will pick (count=1, first
    # Unskilled). turn.py's selection logic prefers eligible non-trained
    # workers; this matches that.
    target = next(w for w in educator.workforce.workers
                  if w.profession == Profession.UNSKILLED.value)
    starting_level = target.training_level

    from island_traders.models.training import TrainingRegistry
    training = TrainingRegistry()
    io = SelfTrainingIO(profession="Nurse", count=1)
    tm = _turn_manager([educator], training, io)

    # 1. Submit + auto-dispatch a self-training batch.  The fix makes this
    #    also mark the worker(s) in_training on the workforce side.
    tm._action_request_training(
        educator, TurnResult(educator.player_id, season=0, year=0),
        season_name="Spring", year=0,
    )
    req = training.all_requests()[0]
    assert req.transport_mode == "self_training"
    # The chosen worker should now be flagged in_training so the return
    # hook can find them.
    assert any(
        w.in_training for w in educator.workforce.workers
        if w.worker_id in req.worker_ids
    ), "Self-trained workers should be marked in_training during their course"

    # 2. Walk the Game-level return hook at the scheduled return tick.
    #    Nurse is Manager-tier with EDUCATION_SEASONS[Nurse]=1, so a course
    #    dispatched in Y0/S0 returns in Y0/S1.
    from island_traders.engine.game import Game, GameConfig, PlayerSpec
    config = GameConfig(num_years=1, player_specs=[
        PlayerSpec(name="X", role_names=["Educator"], is_human=False),
    ])
    standalone = Game(config, FakeIOAdapter())
    # Reuse our prepared registry and educator to keep state consistent.
    standalone.training = training
    standalone.players = [educator]

    standalone._process_training_returns(year=0, season=1)

    # 3. Worker should have graduated.
    worker = next(w for w in educator.workforce.workers if w.worker_id == target.worker_id)
    assert not worker.in_training, (
        "Self-trained worker should be back active after return tick"
    )
    assert worker.profession == Profession.NURSE.value, (
        "Self-trained Unskilled worker should graduate into Nurse"
    )
    assert worker.training_level == starting_level + 1
