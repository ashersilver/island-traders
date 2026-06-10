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


def _manager_training_ready(educator: Player, courses: int = 1, expertise: int = 3) -> None:
    educator.receive_resources(ResourceType.COURSES, courses)
    educator.receive_resources(ResourceType.EXPERTISE, expertise)
    educator.receive_resources(ResourceType.REAGENTS, 20)
    educator.workforce.add_workers(1, training_level=1, profession="Professor")
    educator.workforce.add_workers(1, training_level=1, profession="Lecturer")


class TrainingReviewIO(FakeIOAdapter):
    """Fake IO adapter for testing the Educator's training review flow.

    `confirms` is a list of booleans (True=Approve, False=Counter/Reject)
    that drive the choose_option prompt in _action_review_training.
    Internally this converts True → "approve" and False → "counter" to
    match the new three-option picker (approve / counter / skip).
    """

    def __init__(self, confirms=None, amounts=None, texts=None):
        super().__init__()
        self.confirms = list(confirms or [])
        self.amounts = list(amounts or [])
        self.texts = list(texts or [])

    def choose_option(self, prompt, options, request_summary=None):
        """Pop from confirms:
        - str  → returned as-is (explicit option value)
        - True → first option value
        - False → 'reject' if options include it, else 'counter'
        - None → 'skip'

        Handles both Educator review (approve/counter/skip) and requester
        counter-offer review (approve/counter/reject) by checking option values.
        """
        self.printed.append(prompt)
        if not self.confirms:
            return options[0]["value"] if options else None
        raw = self.confirms.pop(0)
        if isinstance(raw, str):
            return raw
        if raw is True:
            return options[0]["value"] if options else "approve"
        if raw is False:
            vals = [o["value"] for o in options if isinstance(o, dict)]
            return "reject" if "reject" in vals else "counter"
        return "skip"

    def confirm(self, prompt, request_summary=None):
        """Used by sub-prompts (e.g. requester accepting counter-offer)."""
        self.printed.append(prompt)
        if not self.confirms:
            return True
        return self.confirms.pop(0)

    def ask_dollop_amount(self, prompt, max_dollops, prefill=0.0):
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


def test_review_training_still_lists_request_with_absent_pinned_workers():
    farmer = _player(0, "Farmer", "Farmer")
    farmer.workforce.workers.clear()
    farmer.workforce._next_id = 0
    farmer.workforce.add_workers(3, profession="Unskilled")
    educator = _player(1, "Educator", "Educator")
    training = TrainingRegistry()
    req = training.propose(
        requester_id=farmer.player_id,
        worker_ids=[0],
        educator_id=educator.player_id,
        dollops_to_educator=40.0,
        target_profession="FarmingTechnician",
        year=0,
        season=0,
        transport_mode="air_ticket",
    )
    farmer.workforce.dispatch_for_training([0])

    io = TrainingReviewIO(confirms=[None])
    manager = _turn_manager([farmer, educator], training, io)
    manager._action_review_training(
        educator,
        TurnResult(educator.player_id, season=0, year=0),
        season_name="Spring",
        year=0,
    )

    output = "\n".join(io.printed)
    assert f"TrainingRequest #{req.batch_id}" in output
    assert "No training requests awaiting your approval." not in output


def test_educator_approval_consumes_air_tickets_and_dispatches_training():
    farmer = _player(0, "Farmer", "Farmer")
    educator = _player(1, "Educator", "Educator")
    workers = farmer.workforce.add_workers(2)
    educator.receive_resources(ResourceType.PASSENGER_SEATS, 2)
    _manager_training_ready(educator)
    training = TrainingRegistry()
    req = training.propose(
        requester_id=farmer.player_id,
        worker_ids=[w.worker_id for w in workers],
        educator_id=educator.player_id,
        dollops_to_educator=70.0,
        target_profession="Nurse",  # Manager-tier → Course-gated (Phase 3)
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
    # 100 + 70 fee − 16 student medical cover (2 × 8) = 154 (2026-06-02).
    assert educator.dollops == 154.0
    assert farmer.dollops == 30.0
    assert farmer.workforce.training_count == 2


def test_training_approval_does_not_consume_expertise_per_attendee():
    farmer = _player(0, "Farmer", "Farmer")
    educator = _player(1, "Educator", "Educator")
    workers = farmer.workforce.add_workers(2)
    educator.receive_resources(ResourceType.PASSENGER_SEATS, 2)
    _manager_training_ready(educator, expertise=3)
    training = TrainingRegistry()
    training.propose(
        requester_id=farmer.player_id,
        worker_ids=[w.worker_id for w in workers],
        educator_id=educator.player_id,
        dollops_to_educator=70.0,
        target_profession="Nurse",  # Manager-tier → Course-gated (Phase 3)
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
    assert educator.inventory.get(ResourceType.EXPERTISE) == 1


def test_educator_cannot_approve_training_without_air_tickets():
    farmer = _player(0, "Farmer", "Farmer")
    educator = _player(1, "Educator", "Educator")
    workers = farmer.workforce.add_workers(2)
    # Give staffing, Courses, and Expertise so the capacity peek passes and
    # the test still exercises the air-ticket gate.
    _manager_training_ready(educator)
    training = TrainingRegistry()
    req = training.propose(
        requester_id=farmer.player_id,
        worker_ids=[w.worker_id for w in workers],
        educator_id=educator.player_id,
        dollops_to_educator=70.0,
        target_profession="Nurse",  # Manager-tier → Course-gated (Phase 3)
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
    _manager_training_ready(educator)
    training = TrainingRegistry()
    req = training.propose(
        requester_id=farmer.player_id,
        worker_ids=[w.worker_id for w in workers],
        educator_id=educator.player_id,
        dollops_to_educator=50.0,
        target_profession="Nurse",  # Manager-tier → Course-gated (Phase 3)
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
    # Educator receives the 90 fee but pays student medical cover at dispatch
    # (2 students × MEDICAL_PREMIUM_PER_HEAD 8 = 16; no Banker here so it's an
    # external insurer): 100 + 90 − 16 = 174 (2026-06-02 student insurance).
    assert educator.dollops == 174.0
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


def test_requester_can_counter_counter_offer():
    """Requester sends a counter-counter, putting the request back to AWAITING_EDUCATOR."""
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

    # "counter" passed as str → returned as-is; amounts provides the new fee; texts provides message
    io = TrainingReviewIO(confirms=["counter"], amounts=[32.0], texts=["How about 32?"])
    manager = _turn_manager([farmer, educator], training, io)
    result = TurnResult(farmer.player_id, season=0, year=0)
    manager._review_training_counteroffers(
        farmer, result, season_name="Spring", year=0
    )

    # Request goes back to the Educator with requester's new fee
    assert req.status == TrainingStatus.AWAITING_EDUCATOR
    assert req.dollops_to_educator == 32.0
    assert "[Requester]" in req.counter_message
    # No money changes hands yet
    assert farmer.dollops == 100.0
    assert educator.dollops == 100.0
    assert result.actions_taken == ["requester_counter:batch#0"]
