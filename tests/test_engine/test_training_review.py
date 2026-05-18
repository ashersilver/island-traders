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


def _player(player_id: int, name: str, role_name: str) -> Player:
    return Player(player_id, name, [ROLES[role_name]], 100.0, is_human=True)


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


class TrainingReviewIO(FakeIOAdapter):
    def __init__(self, confirms=None, amounts=None, texts=None):
        super().__init__()
        self.confirms = list(confirms or [])
        self.amounts = list(amounts or [])
        self.texts = list(texts or [])

    def confirm(self, prompt):
        self.printed.append(prompt)
        return self.confirms.pop(0)

    def ask_dollop_amount(self, prompt, max_dollops):
        self.printed.append(prompt)
        return self.amounts.pop(0)

    def ask_text(self, prompt, default=""):
        self.printed.append(prompt)
        return self.texts.pop(0)


def test_non_educator_review_training_shows_personal_pipeline():
    farmer = _player(0, "Farmer", "Farmer")
    educator = _player(1, "Educator", "Educator")
    training = TrainingRegistry()
    req = training.propose(
        requester_id=farmer.player_id,
        worker_ids=[101, 102],
        educator_id=educator.player_id,
        dollops_to_educator=40.0,
        target_profession="FarmingTechnician",
        year=0,
        season=0,
        transport_mode="cargo",
    )
    training.educator_approve(req.batch_id)
    training.arrange_transport(req.batch_id, transporter_id=educator.player_id)
    training.dispatch(req.batch_id, year=0, season=0, num_seasons=4)

    io = FakeIOAdapter()
    manager = _turn_manager([farmer, educator], training, io)
    manager._action_review_training(
        farmer,
        TurnResult(farmer.player_id, season=0, year=0),
        season_name="Spring",
        year=0,
    )

    output = "\n".join(io.printed)
    assert "Current training pipeline" in output
    assert "Farming Technician" in output
    assert "2 worker(s)" in output
    assert "Year 1, Autumn" in output


def test_educator_approval_consumes_air_tickets_and_dispatches_training():
    farmer = _player(0, "Farmer", "Farmer")
    educator = _player(1, "Educator", "Educator")
    workers = farmer.workforce.add_workers(2)
    educator.receive_resources(ResourceType.PASSENGER_SEATS, 2)
    educator.receive_resources(ResourceType.COURSES, 1)  # 1 class slot (Phase 2)
    training = TrainingRegistry()
    req = training.propose(
        requester_id=farmer.player_id,
        worker_ids=[w.worker_id for w in workers],
        educator_id=educator.player_id,
        dollops_to_educator=70.0,
        target_profession="FarmingTechnician",
        year=0,
        season=0,
        transport_mode="air_ticket",
    )

    io = FakeIOAdapter()
    manager = _turn_manager([farmer, educator], training, io)
    manager._action_review_training(
        educator,
        TurnResult(educator.player_id, season=0, year=0),
        season_name="Spring",
        year=0,
    )

    assert req.status == TrainingStatus.DISPATCHED
    assert educator.inventory.get(ResourceType.PASSENGER_SEATS) == 0
    assert educator.inventory.get(ResourceType.COURSES) == 0  # 1 Course consumed
    assert educator.dollops == 170.0
    assert farmer.dollops == 30.0
    assert farmer.workforce.training_count == 2


def test_training_approval_does_not_consume_expertise_per_attendee():
    farmer = _player(0, "Farmer", "Farmer")
    educator = _player(1, "Educator", "Educator")
    workers = farmer.workforce.add_workers(2)
    educator.receive_resources(ResourceType.PASSENGER_SEATS, 2)
    educator.receive_resources(ResourceType.COURSES, 1)
    educator.receive_resources(ResourceType.EXPERTISE, 3)
    training = TrainingRegistry()
    training.propose(
        requester_id=farmer.player_id,
        worker_ids=[w.worker_id for w in workers],
        educator_id=educator.player_id,
        dollops_to_educator=70.0,
        target_profession="FarmingTechnician",
        year=0,
        season=0,
        transport_mode="air_ticket",
    )

    manager = _turn_manager([farmer, educator], training, FakeIOAdapter())
    manager._action_review_training(
        educator,
        TurnResult(educator.player_id, season=0, year=0),
        season_name="Spring",
        year=0,
    )

    assert educator.inventory.get(ResourceType.COURSES) == 0
    assert educator.inventory.get(ResourceType.EXPERTISE) == 3


def test_educator_cannot_approve_training_without_air_tickets():
    farmer = _player(0, "Farmer", "Farmer")
    educator = _player(1, "Educator", "Educator")
    workers = farmer.workforce.add_workers(2)
    # Give Courses so the Course peek passes and the test still exercises
    # the air-ticket gate (the Course peek doesn't consume on ticket failure).
    educator.receive_resources(ResourceType.COURSES, 1)
    training = TrainingRegistry()
    req = training.propose(
        requester_id=farmer.player_id,
        worker_ids=[w.worker_id for w in workers],
        educator_id=educator.player_id,
        dollops_to_educator=70.0,
        target_profession="FarmingTechnician",
        year=0,
        season=0,
        transport_mode="air_ticket",
    )

    io = FakeIOAdapter()
    manager = _turn_manager([farmer, educator], training, io)
    manager._action_review_training(
        educator,
        TurnResult(educator.player_id, season=0, year=0),
        season_name="Spring",
        year=0,
    )

    assert req.status == TrainingStatus.AWAITING_EDUCATOR
    assert farmer.dollops == 100.0
    assert educator.dollops == 100.0
    assert farmer.workforce.training_count == 0
    assert "needs 2 more PassengerSeats" in "\n".join(io.printed)
    # No-leak: a ticket shortfall must NOT consume the Course slot.
    assert educator.inventory.get(ResourceType.COURSES) == 1


def test_educator_can_counter_training_request_with_price_and_message():
    farmer = _player(0, "Farmer", "Farmer")
    educator = _player(1, "Educator", "Educator")
    workers = farmer.workforce.add_workers(2)
    training = TrainingRegistry()
    req = training.propose(
        requester_id=farmer.player_id,
        worker_ids=[w.worker_id for w in workers],
        educator_id=educator.player_id,
        dollops_to_educator=50.0,
        target_profession="FarmingTechnician",
        year=0,
        season=0,
        transport_mode="air_ticket",
    )

    io = TrainingReviewIO(
        confirms=[False],
        amounts=[90.0],
        texts=["Need to cover two air tickets."],
    )
    manager = _turn_manager([farmer, educator], training, io)
    result = TurnResult(educator.player_id, season=0, year=0)
    manager._action_review_training(educator, result, season_name="Spring", year=0)

    output = "\n".join(io.printed)
    assert "Workers: 2" in output
    assert "Offered educator fee: 50.0 Dp" in output
    assert "requester cash: 100.0 Dp" in output
    assert req.status == TrainingStatus.COUNTERED
    assert req.dollops_to_educator == 90.0
    assert req.counter_message == "Need to cover two air tickets."
    assert result.actions_taken == ["countered_training:batch#0"]


def test_requester_can_accept_training_counter_offer_and_dispatch():
    farmer = _player(0, "Farmer", "Farmer")
    educator = _player(1, "Educator", "Educator")
    workers = farmer.workforce.add_workers(2)
    educator.receive_resources(ResourceType.PASSENGER_SEATS, 2)
    educator.receive_resources(ResourceType.COURSES, 1)  # class slot (Phase 2)
    training = TrainingRegistry()
    req = training.propose(
        requester_id=farmer.player_id,
        worker_ids=[w.worker_id for w in workers],
        educator_id=educator.player_id,
        dollops_to_educator=50.0,
        target_profession="FarmingTechnician",
        year=0,
        season=0,
        transport_mode="air_ticket",
    )
    training.educator_counter(
        req.batch_id, 90.0, "Need to cover two air tickets."
    )

    io = TrainingReviewIO(confirms=[True])
    manager = _turn_manager([farmer, educator], training, io)
    result = TurnResult(farmer.player_id, season=0, year=0)
    manager._review_training_counteroffers(
        farmer, result, season_name="Spring", year=0
    )

    assert req.status == TrainingStatus.DISPATCHED
    assert farmer.dollops == 10.0
    assert educator.dollops == 190.0
    assert educator.inventory.get(ResourceType.PASSENGER_SEATS) == 0
    assert farmer.workforce.training_count == 2
    assert result.actions_taken == ["approved_training:batch#0"]


def test_requester_can_reject_training_counter_offer():
    farmer = _player(0, "Farmer", "Farmer")
    educator = _player(1, "Educator", "Educator")
    workers = farmer.workforce.add_workers(1)
    training = TrainingRegistry()
    req = training.propose(
        requester_id=farmer.player_id,
        worker_ids=[w.worker_id for w in workers],
        educator_id=educator.player_id,
        dollops_to_educator=20.0,
        target_profession="FarmingTechnician",
        year=0,
        season=0,
        transport_mode="air_ticket",
    )
    training.educator_counter(req.batch_id, 45.0, "Premium slot.")

    io = TrainingReviewIO(confirms=[False])
    manager = _turn_manager([farmer, educator], training, io)
    result = TurnResult(farmer.player_id, season=0, year=0)
    manager._review_training_counteroffers(
        farmer, result, season_name="Spring", year=0
    )

    assert req.status == TrainingStatus.REJECTED
    assert farmer.dollops == 100.0
    assert educator.dollops == 100.0
    assert result.actions_taken == ["rejected_training_counter:batch#0"]
