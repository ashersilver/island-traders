from __future__ import annotations

import pytest

from island_traders.cli.prompts import FakeIOAdapter
from island_traders.constants_capacity import CAPITAL_CATALOGUE
from island_traders.engine.production import ProductionEngine
from island_traders.engine.trading import TradingEngine
from island_traders.engine.turn import TurnManager, TurnAction, TurnResult
from island_traders.models.capacity import find_item
from island_traders.models.deal import DealLedger
from island_traders.models.lease import LeaseLedger, LeaseStatus, lease_quote
from island_traders.models.loan import LoanLedger, LoanStatus, posted_funding_rates, banker_quote_rate
from island_traders.models.market import Market
from island_traders.models.player import Player
from island_traders.models.profession import Profession
from island_traders.models.role import ROLES


WORKSHOP_ID = "educator.technical_workshop"


def _player(pid: int, name: str, role: str, dollops: float = 500.0, human: bool = True) -> Player:
    return Player(pid, name, [ROLES[role]], dollops, is_human=human)


def _tm(players, leases=None, loans=None, io=None) -> TurnManager:
    market = Market()
    return TurnManager(
        players=players,
        production_engine=ProductionEngine(),
        trading_engine=TradingEngine(market, DealLedger()),
        market=market,
        io_adapter=io or FakeIOAdapter(),
        loan_ledger=loans or LoanLedger(),
        lease_ledger=leases or LeaseLedger(),
    )


def _workshop():
    item = find_item(CAPITAL_CATALOGUE, WORKSHOP_ID)
    assert item is not None
    return item


def _start_lease(tm: TurnManager, educator: Player, banker: Player | None = None, year=0, season=0):
    return tm._create_equipment_lease(
        educator, _workshop(), year, season, lessor=banker, immediate_delivery=True
    )


def test_lease_creation_at_investing_phase():
    educator = _player(0, "Educator", "Educator", dollops=100.0)
    banker = _player(1, "Banker", "Banker", dollops=50.0)
    leases = LeaseLedger()
    tm = _tm([educator, banker], leases)
    quote = lease_quote(_workshop(), 0, 0)

    lease = _start_lease(tm, educator, banker)

    assert educator.capital_inventory[WORKSHOP_ID] == 1
    assert educator.dollops == round(100.0 - quote["annual_payment"], 1)
    assert banker.dollops == round(50.0 + quote["annual_payment"], 1)
    assert lease.payments_made == 1
    assert lease.status == LeaseStatus.ACTIVE


class LeaseIO(FakeIOAdapter):
    def __init__(self, chosen_item_id=WORKSHOP_ID, confirm=True):
        super().__init__()
        self.chosen_item_id = chosen_item_id
        self.confirm_value = confirm

    def choose_option(self, prompt, options):
        for option in options:
            if option["value"] == self.chosen_item_id:
                return option["value"]
        return options[0]["value"]

    def confirm(self, prompt):
        return self.confirm_value


def test_lease_creation_mid_game_via_lease_capital_action():
    educator = _player(0, "Educator", "Educator", dollops=100.0)
    banker = _player(1, "Banker", "Banker", dollops=50.0)
    # Writing a new lease mid-game needs counsel on the roster (#44); this
    # test is about rate locking, so give the Educator a Lawyer and let it
    # through.  The gate itself is covered in test_lease_lawyer_gate.py.
    educator.workforce.add_workers(1, profession=Profession.LAWYER.value)
    leases = LeaseLedger()
    tm = _tm([educator, banker], leases, io=LeaseIO())

    tm._action_lease_capital(educator, TurnResult(0, 2, 1), year=1, season_index=2)

    lease = leases.all_leases()[0]
    assert lease.started_year == 1
    assert lease.started_season == 2
    assert lease.locked_lease_rate == posted_funding_rates(1, 2)[3] + 0.02
    assert educator.capital_inventory[WORKSHOP_ID] == 1


def test_annual_payment_in_advance_at_year_start():
    educator = _player(0, "Educator", "Educator", dollops=100.0, human=False)
    banker = _player(1, "Banker", "Banker", dollops=0.0)
    leases = LeaseLedger()
    tm = _tm([educator, banker], leases)
    lease = _start_lease(tm, educator, banker)
    before = educator.dollops

    tm._process_lease_payments(year=1, season=0)

    assert lease.last_payment_year == 1
    assert lease.payments_made == 2
    assert educator.dollops == round(before - lease.annual_payment, 1)


def test_missed_annual_payment_triggers_repossession():
    educator = _player(0, "Educator", "Educator", dollops=20.0, human=False)
    banker = _player(1, "Banker", "Banker")
    leases = LeaseLedger()
    tm = _tm([educator, banker], leases)
    lease = _start_lease(tm, educator, banker)
    educator.dollops = 0.0

    tm._process_lease_payments(year=1, season=0)

    assert lease.status == LeaseStatus.REPOSSESSED
    assert lease.repossessed_year == 1
    assert lease.repossessed_season == 0
    assert WORKSHOP_ID not in educator.capital_inventory


def test_repossession_return_one_season_after_catchup_payment():
    educator = _player(0, "Educator", "Educator", dollops=100.0)
    banker = _player(1, "Banker", "Banker")
    leases = LeaseLedger()
    tm = _tm([educator, banker], leases, io=LeaseIO())
    lease = _start_lease(tm, educator, banker)
    educator.remove_capital(WORKSHOP_ID, 1)
    leases.repossess(lease.lease_id, 1, 0)

    tm._action_pay_lease(educator, TurnResult(0, 1, 1), year=1, season_index=1)
    assert lease.status == LeaseStatus.REPOSSESSED
    assert WORKSHOP_ID not in educator.capital_inventory

    tm._process_lease_reinstatements(year=1, season=2)
    assert lease.status == LeaseStatus.ACTIVE
    assert educator.capital_inventory[WORKSHOP_ID] == 1


def test_final_annual_payment_flips_to_awaiting_buyout_not_completed():
    educator = _player(0, "Educator", "Educator", dollops=100.0, human=False)
    banker = _player(1, "Banker", "Banker")
    leases = LeaseLedger()
    tm = _tm([educator, banker], leases)
    lease = _start_lease(tm, educator, banker)
    lease.payments_made = 2
    lease.last_payment_year = 1

    tm._process_lease_payments(year=2, season=0)

    assert lease.status == LeaseStatus.AWAITING_BUYOUT
    assert lease.status != LeaseStatus.COMPLETED
    assert educator.capital_inventory[WORKSHOP_ID] == 1


def test_buyout_payment_completes_lease_with_ownership_transfer():
    educator = _player(0, "Educator", "Educator", dollops=100.0, human=False)
    banker = _player(1, "Banker", "Banker")
    leases = LeaseLedger()
    tm = _tm([educator, banker], leases)
    lease = _start_lease(tm, educator, banker)
    lease.payments_made = lease.term_years
    lease.status = LeaseStatus.AWAITING_BUYOUT

    tm._process_lease_payments(year=3, season=0)

    assert lease.buyout_payment == 15.0
    assert lease.status == LeaseStatus.COMPLETED
    assert educator.capital_inventory[WORKSHOP_ID] == 1


def test_buyout_default_terminally_removes_item():
    educator = _player(0, "Educator", "Educator", dollops=0.0, human=False)
    banker = _player(1, "Banker", "Banker")
    leases = LeaseLedger()
    tm = _tm([educator, banker], leases)
    educator.add_capital(WORKSHOP_ID, 1)
    quote = lease_quote(_workshop(), 0, 0)
    lease = leases.create_lease(
        WORKSHOP_ID, educator.player_id, banker.player_id, 0, 0,
        quote["term_years"], quote["annual_payment"], quote["buyout_payment"],
        quote["locked_lease_rate"], payments_made=3, last_payment_year=2,
    )

    tm._process_lease_payments(year=3, season=0)

    assert lease.status == LeaseStatus.BUYOUT_DEFAULTED
    assert WORKSHOP_ID not in educator.capital_inventory
    assert leases.repossessed_leases_for(educator.player_id) == []


def test_lease_rate_locked_at_inception_independent_of_later_posted_rates():
    quote = lease_quote(_workshop(), 0, 0)
    educator = _player(0, "Educator", "Educator", dollops=100.0, human=False)
    banker = _player(1, "Banker", "Banker")
    leases = LeaseLedger()
    tm = _tm([educator, banker], leases)
    lease = _start_lease(tm, educator, banker, year=0, season=0)

    tm._process_lease_payments(year=1, season=0)

    assert posted_funding_rates(1, 0)[3] != posted_funding_rates(0, 0)[3]
    assert lease.locked_lease_rate == quote["locked_lease_rate"]
    assert lease.annual_payment == quote["annual_payment"]


def test_lease_rate_uses_posted_3yr_funding_plus_2pct_margin():
    item = _workshop()
    quote = lease_quote(item, 0, 0)

    assert quote["locked_lease_rate"] == posted_funding_rates(0, 0)[3] + 0.02
    assert quote["buyout_payment"] == round(item.cost * 0.25, 1)
    assert quote["annual_payment"] == round((item.cost - quote["buyout_payment"]) / 3 * (1 + quote["locked_lease_rate"]), 1)


def test_due_leases_filters_by_year_and_season():
    leases = LeaseLedger()
    quote = lease_quote(_workshop(), 0, 0)
    active = leases.create_lease(WORKSHOP_ID, 0, 1, 0, 0, quote["term_years"], quote["annual_payment"], quote["buyout_payment"], quote["locked_lease_rate"], payments_made=1, last_payment_year=0)
    buyout = leases.create_lease(WORKSHOP_ID, 2, 1, 0, 0, quote["term_years"], quote["annual_payment"], quote["buyout_payment"], quote["locked_lease_rate"], payments_made=3, last_payment_year=2)
    buyout.status = LeaseStatus.AWAITING_BUYOUT

    assert leases.due_leases(1, 1) == []
    assert active in leases.due_leases(1, 0)
    assert buyout in leases.due_leases(3, 0)


def test_ai_lessee_auto_pays_when_solvent():
    educator = _player(0, "Educator", "Educator", dollops=200.0, human=False)
    banker = _player(1, "Banker", "Banker", dollops=0.0)
    leases = LeaseLedger()
    tm = _tm([educator, banker], leases)
    lease = _start_lease(tm, educator, banker)

    tm._process_lease_payments(year=1, season=0)

    assert lease.status == LeaseStatus.ACTIVE
    assert lease.payments_made == 2
    assert banker.dollops > 0


def test_ai_lessee_defaults_when_insolvent():
    educator = _player(0, "Educator", "Educator", dollops=20.0, human=False)
    banker = _player(1, "Banker", "Banker")
    leases = LeaseLedger()
    tm = _tm([educator, banker], leases)
    annual = _start_lease(tm, educator, banker)
    educator.dollops = 0.0
    tm._process_lease_payments(year=1, season=0)
    assert annual.status == LeaseStatus.REPOSSESSED

    educator.add_capital(WORKSHOP_ID, 1)
    quote = lease_quote(_workshop(), 0, 0)
    buyout = leases.create_lease(WORKSHOP_ID, educator.player_id, banker.player_id, 0, 0, quote["term_years"], quote["annual_payment"], quote["buyout_payment"], quote["locked_lease_rate"], payments_made=3, last_payment_year=2)
    buyout.status = LeaseStatus.AWAITING_BUYOUT
    tm._process_lease_payments(year=3, season=0)
    assert buyout.status == LeaseStatus.BUYOUT_DEFAULTED


def test_leases_detail_payload_shape():
    pytest.importorskip("fastapi")
    from island_traders.engine.game import Game, GameConfig, PlayerSpec
    from island_traders.server.app import GameManager, GameRoom, LobbyPlayer

    mgr = GameManager()
    room = GameRoom("r1", "Test", 2, 1, True, "GS0001", "p0")
    room.players = [
        LobbyPlayer("p0", "Educator", role_names=["Educator"]),
        LobbyPlayer("p1", "Banker", role_names=["Banker"]),
    ]
    room.status = "running"
    mgr.rooms[room.room_id] = room
    game = Game(GameConfig([
        PlayerSpec("Educator", ["Educator"], True),
        PlayerSpec("Banker", ["Banker"], True),
    ]), FakeIOAdapter())
    game.setup()
    room.game = game
    room.lobby_to_engine_id = {"p0": 0, "p1": 1}
    educator, banker = game.players
    _start_lease(game.turn_manager, educator, banker)

    state = mgr.get_game_state(room.room_id, "p0")
    detail = next(p for p in state["players"] if p["player_id"] == 0)["leases_detail"][0]

    assert set(detail) == {
        "lease_id", "item_id", "item_name", "role", "counterparty_id",
        "annual_payment", "buyout_payment", "payments_made", "term_years",
        "seasons_to_next_payment", "status", "next_payment_year",
        "next_payment_season", "next_payment_type",
    }
    assert detail["buyout_payment"] == 15.0
    assert detail["next_payment_type"] == "annual"


def test_investing_phase_lease_choice_creates_lease_not_purchase():
    pytest.importorskip("fastapi")
    from island_traders.server.app import GameManager, GameRoom, LobbyPlayer

    mgr = GameManager()
    room = GameRoom("r2", "Test", 2, 1, True, "GS0002", "p0", starting_capital=100.0)
    room.players = [
        LobbyPlayer("p0", "Educator", role_names=["Educator"]),
        LobbyPlayer("p1", "Banker", role_names=["Banker"]),
    ]
    mgr.rooms[room.room_id] = room
    room.status = "investing"
    from island_traders.server.app import InvestingState
    room.investing = InvestingState()
    mgr.submit_investment(room.room_id, "p0", [f"lease:{WORKSHOP_ID}"], ready=False)
    mgr.submit_investment(room.room_id, "p1", [], ready=False)

    mgr._resolve_investing(room.room_id)

    educator = room.game.players[0]
    lease = room.game.lease_ledger.all_leases()[0]
    assert educator.capital_inventory[WORKSHOP_ID] == 1
    assert lease.item_id == WORKSHOP_ID
    assert lease.payments_made == 1
    assert educator.dollops > 100.0 - _workshop().cost


def test_legacy_loan_path_unaffected_by_lease_subsystem():
    borrower = _player(0, "Borrower", "Farmer", dollops=100.0)
    banker = _player(1, "Banker", "Banker", dollops=500.0)
    loans = LoanLedger()
    tm = _tm([borrower, banker], leases=LeaseLedger(), loans=loans)
    rate = banker_quote_rate(borrower, loans, 50.0, 1, 0, 0)
    loan = loans.create_loan(borrower.player_id, banker.player_id, 50.0, rate, 0, 0, term_years=1)

    tm._process_loan_repayments(year=1, season=0)

    assert loan.status == LoanStatus.REPAID
    assert loans.outstanding_debt(borrower.player_id) == 0
