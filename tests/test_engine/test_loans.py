from __future__ import annotations

from island_traders.cli.prompts import FakeIOAdapter
from island_traders.engine.production import ProductionEngine
from island_traders.engine.trading import TradingEngine
from island_traders.engine.turn import TurnManager, TurnResult
from island_traders.models.deal import DealLedger
from island_traders.models.loan import LoanLedger, LoanStatus, posted_funding_rates
from island_traders.models.market import Market
from island_traders.models.player import Player
from island_traders.models.role import ROLES


class LoanIO(FakeIOAdapter):
    def __init__(self, amounts: list[float], quantities: list[int] | None = None):
        super().__init__()
        self.amounts = list(amounts)
        self.quantities = list(quantities or [])

    def ask_dollop_amount(self, prompt, max_dollops):
        return self.amounts.pop(0)

    def confirm(self, prompt):
        return True

    def choose_quantity(self, prompt, min_qty, max_qty):
        if self.quantities:
            return self.quantities.pop(0)
        return min_qty


def _turn_manager(players, loan_ledger, io):
    market = Market()
    return TurnManager(
        players=players,
        production_engine=ProductionEngine(),
        trading_engine=TradingEngine(market, DealLedger()),
        market=market,
        io_adapter=io,
        loan_ledger=loan_ledger,
    )


def test_multi_role_banker_can_take_loan_for_their_other_island():
    player = Player(
        player_id=0,
        name="Farmer Banker",
        roles=[ROLES["Farmer"], ROLES["Banker"]],
        dollops=100.0,
        is_human=True,
    )
    loans = LoanLedger()
    tm = _turn_manager([player], loans, LoanIO([50.0], quantities=[1]))
    result = TurnResult(player_id=player.player_id, season=0, year=0)

    tm._action_take_loan(player, result, year=0, season_index=0)

    loan = loans.all_loans()[0]
    assert loan.borrower_id == player.player_id
    assert loan.lender_id == player.player_id
    assert loan.term_years == 1
    assert loan.interest_rate == 0.065
    assert player.dollops == 150.0
    assert loans.outstanding_debt(player.player_id) == 53.2
    assert loans.loans_receivable(player.player_id) == 0.0
    assert player.total_wealth({}, loans) == 96.8
    assert result.actions_taken == ["loan:taken:50.0"]


def test_self_bank_loan_repayment_burns_cash_instead_of_round_tripping_to_self():
    player = Player(
        player_id=0,
        name="Farmer Banker",
        roles=[ROLES["Farmer"], ROLES["Banker"]],
        dollops=100.0,
        is_human=True,
    )
    loans = LoanLedger()
    tm = _turn_manager([player], loans, LoanIO([50.0], quantities=[1]))

    tm._action_take_loan(
        player,
        TurnResult(player_id=player.player_id, season=0, year=0),
        year=0,
        season_index=0,
    )
    tm._process_loan_repayments(year=1, season=0)

    loan = loans.all_loans()[0]
    assert loan.status == LoanStatus.REPAID
    assert player.dollops == 96.8


def test_external_depositor_loan_repayment_burns_cash_without_player_lender():
    banker = Player(
        player_id=0,
        name="Banker",
        roles=[ROLES["Banker"]],
        dollops=100.0,
        is_human=True,
    )
    loans = LoanLedger()
    loan = loans.create_loan(
        borrower_id=banker.player_id,
        lender_id=-1,
        principal=50.0,
        interest_rate=0.05,
        issued_year=0,
        issued_season=0,
        term_years=1,
    )
    io = LoanIO([])
    tm = _turn_manager([banker], loans, io)

    tm._process_loan_repayments(year=1, season=0)

    assert loan.status == LoanStatus.REPAID
    assert banker.dollops == 47.5
    assert "external depositors" in "\n".join(io.printed)


def test_banker_quote_uses_posted_term_rate_plus_minimum_spread():
    player = Player(
        player_id=0,
        name="Farmer Banker",
        roles=[ROLES["Farmer"], ROLES["Banker"]],
        dollops=100.0,
        is_human=True,
    )
    loans = LoanLedger()
    tm = _turn_manager([player], loans, LoanIO([50.0], quantities=[3]))

    tm._action_take_loan(
        player,
        TurnResult(player_id=player.player_id, season=0, year=0),
        year=0,
        season_index=0,
    )

    loan = loans.all_loans()[0]
    assert loan.term_years == 3
    assert loan.maturity_year == 3
    assert loan.interest_rate == posted_funding_rates(0, 0)[3] + 0.02


def test_loan_split_into_own_and_external_per_reserve_ratio():
    """Phase D: bank ALWAYS funds r·P from own capital and (1−r)·P
    externally — not just on shortfall. With no MBA-qualified Banker
    Managers, r = 0.05 → own=5 / external=95 on a 100 Dp loan."""
    banker = Player(
        player_id=0, name="Banker", roles=[ROLES["Banker"]],
        dollops=50.0, is_human=True,
    )
    farmer = Player(
        player_id=1, name="Farmer", roles=[ROLES["Farmer"]],
        dollops=100.0, is_human=True,
    )
    loans = LoanLedger()
    tm = _turn_manager([farmer, banker], loans, LoanIO([100.0], quantities=[2]))

    tm._action_take_loan(
        farmer,
        TurnResult(player_id=farmer.player_id, season=0, year=0),
        year=0, season_index=0,
    )

    customer_loan, funding_loan = loans.all_loans()
    assert customer_loan.borrower_id == farmer.player_id
    assert customer_loan.lender_id == banker.player_id
    assert customer_loan.term_years == 2
    assert customer_loan.interest_rate == posted_funding_rates(0, 0)[2] + 0.02
    # Phase D bookkeeping populated on the customer loan.
    assert customer_loan.own_committed == 5.0
    assert customer_loan.external_funded == 95.0
    assert customer_loan.reserve_ratio_at_issue == 0.05
    assert customer_loan.posted_at_issue == posted_funding_rates(0, 0)[2]
    # External depositor loan exists at the posted rate.
    assert funding_loan.borrower_id == banker.player_id
    assert funding_loan.lender_id == -1
    assert funding_loan.principal == 95.0
    assert funding_loan.interest_rate == posted_funding_rates(0, 0)[2]
    # Bank ends holding only its locked own share (50 + 95 external − 100 to farmer).
    assert banker.dollops == 45.0
    assert farmer.dollops == 200.0


def test_bank_refuses_loan_when_own_capital_below_reserve():
    """With r=0.05 and only 1 Dp on hand, the bank cannot back a 50 Dp
    loan (would need 2.5 Dp of own capital) — request is refused, no
    loans created, no cash moves."""
    banker = Player(
        player_id=0, name="Banker", roles=[ROLES["Banker"]],
        dollops=1.0, is_human=True,
    )
    farmer = Player(
        player_id=1, name="Farmer", roles=[ROLES["Farmer"]],
        dollops=100.0, is_human=True,
    )
    loans = LoanLedger()
    io = LoanIO([50.0], quantities=[2])
    tm = _turn_manager([farmer, banker], loans, io)

    tm._action_take_loan(
        farmer,
        TurnResult(player_id=farmer.player_id, season=0, year=0),
        year=0, season_index=0,
    )

    assert loans.all_loans() == []
    assert banker.dollops == 1.0
    assert farmer.dollops == 100.0
    log = "\n".join(io.printed)
    assert "reserve" in log.lower()


def test_three_mbas_drop_reserve_to_two_percent():
    """≥3 MBA Banker Managers → r = 0.02: own=2 / external=98 on 100 Dp."""
    banker = Player(
        player_id=0, name="Banker", roles=[ROLES["Banker"]],
        dollops=50.0, is_human=True,
    )
    # Seed 3 Banker-profession Manager workers with MBAs.
    banker.workforce.add_workers(3, training_level=1, profession="Banker")
    for w in banker.workforce.workers:
        w.has_mba = True
    farmer = Player(
        player_id=1, name="Farmer", roles=[ROLES["Farmer"]],
        dollops=100.0, is_human=True,
    )
    loans = LoanLedger()
    tm = _turn_manager([farmer, banker], loans, LoanIO([100.0], quantities=[2]))

    tm._action_take_loan(
        farmer,
        TurnResult(player_id=farmer.player_id, season=0, year=0),
        year=0, season_index=0,
    )

    customer_loan, funding_loan = loans.all_loans()
    assert customer_loan.own_committed == 2.0
    assert customer_loan.external_funded == 98.0
    assert customer_loan.reserve_ratio_at_issue == 0.02
    assert funding_loan.principal == 98.0
    assert banker.dollops == 48.0   # 50 + 98 external − 100 to farmer


def test_banker_active_loan_cap_blocks_third_customer_loan():
    banker = Player(
        player_id=0, name="Banker", roles=[ROLES["Banker"]],
        dollops=100.0, is_human=True,
    )
    banker.workforce.add_workers(1, training_level=1, profession="Banker")
    farmer = Player(
        player_id=1, name="Farmer", roles=[ROLES["Farmer"]],
        dollops=100.0, is_human=True,
    )
    miner = Player(
        player_id=2, name="Miner", roles=[ROLES["Miner"]],
        dollops=100.0, is_human=True,
    )
    loans = LoanLedger()
    io = LoanIO([20.0, 20.0, 20.0], quantities=[1, 1, 1])
    tm = _turn_manager([farmer, miner, banker], loans, io)

    tm._action_offer_loan(banker, TurnResult(banker.player_id, 0, 0), 0, 0)
    tm._action_offer_loan(banker, TurnResult(banker.player_id, 0, 0), 0, 0)
    tm._action_offer_loan(banker, TurnResult(banker.player_id, 0, 0), 0, 0)

    customer_loans = [
        loan for loan in loans.all_loans()
        if loan.lender_id == banker.player_id
        and loan.status == LoanStatus.ACTIVE
    ]
    assert len(customer_loans) == 2
    assert "active-loan cap (2/2)" in "\n".join(io.printed)


def test_banker_with_no_manager_gets_one_starter_loan_slot():
    banker = Player(
        player_id=0, name="Banker", roles=[ROLES["Banker"]],
        dollops=100.0, is_human=True,
    )
    banker.workforce.add_workers(1, training_level=1, profession="Banker")
    banker.workforce.workers = []
    farmer = Player(
        player_id=1, name="Farmer", roles=[ROLES["Farmer"]],
        dollops=100.0, is_human=True,
    )
    loans = LoanLedger()
    io = LoanIO([20.0, 20.0], quantities=[1, 1])
    tm = _turn_manager([farmer, banker], loans, io)

    tm._action_take_loan(farmer, TurnResult(farmer.player_id, 0, 0), 0, 0)
    tm._action_take_loan(farmer, TurnResult(farmer.player_id, 0, 0), 0, 0)

    customer_loans = [
        loan for loan in loans.all_loans()
        if loan.lender_id == banker.player_id
        and loan.status == LoanStatus.ACTIVE
    ]
    assert len(customer_loans) == 1
    assert "active-loan cap (1/1)" in "\n".join(io.printed)


def test_repaid_or_defaulted_loans_free_banker_cap_slot():
    banker = Player(
        player_id=0, name="Banker", roles=[ROLES["Banker"]],
        dollops=100.0, is_human=True,
    )
    banker.workforce.add_workers(1, training_level=1, profession="Banker")
    farmer = Player(
        player_id=1, name="Farmer", roles=[ROLES["Farmer"]],
        dollops=100.0, is_human=True,
    )
    loans = LoanLedger()
    loans.create_loan(farmer.player_id, banker.player_id, 10.0, 0.05, 0, 0).status = LoanStatus.REPAID
    loans.create_loan(farmer.player_id, banker.player_id, 10.0, 0.05, 0, 0).status = LoanStatus.DEFAULTED
    loans.create_loan(farmer.player_id, banker.player_id, 10.0, 0.05, 0, 0)
    io = LoanIO([20.0], quantities=[1])
    tm = _turn_manager([farmer, banker], loans, io)

    tm._action_take_loan(farmer, TurnResult(farmer.player_id, 0, 0), 0, 0)

    active_customer_loans = [
        loan for loan in loans.all_loans()
        if loan.lender_id == banker.player_id
        and loan.status == LoanStatus.ACTIVE
    ]
    assert len(active_customer_loans) == 2


def test_depositor_loans_do_not_count_against_banker_cap():
    banker = Player(
        player_id=0, name="Banker", roles=[ROLES["Banker"]],
        dollops=100.0, is_human=True,
    )
    banker.workforce.add_workers(1, training_level=1, profession="Banker")
    farmer = Player(
        player_id=1, name="Farmer", roles=[ROLES["Farmer"]],
        dollops=100.0, is_human=True,
    )
    loans = LoanLedger()
    loans.create_loan(banker.player_id, -1, 95.0, 0.05, 0, 0)
    loans.create_loan(banker.player_id, -1, 95.0, 0.05, 0, 0)
    io = LoanIO([20.0, 20.0], quantities=[1, 1])
    tm = _turn_manager([farmer, banker], loans, io)

    tm._action_take_loan(farmer, TurnResult(farmer.player_id, 0, 0), 0, 0)
    tm._action_take_loan(farmer, TurnResult(farmer.player_id, 0, 0), 0, 0)

    customer_loans = [
        loan for loan in loans.all_loans()
        if loan.lender_id == banker.player_id
        and loan.borrower_id == farmer.player_id
    ]
    assert len(customer_loans) == 2
