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


def test_bank_can_fund_external_shortfall_at_posted_rate():
    banker = Player(
        player_id=0,
        name="Banker",
        roles=[ROLES["Banker"]],
        dollops=10.0,
        is_human=True,
    )
    farmer = Player(
        player_id=1,
        name="Farmer",
        roles=[ROLES["Farmer"]],
        dollops=100.0,
        is_human=True,
    )
    loans = LoanLedger()
    tm = _turn_manager([farmer, banker], loans, LoanIO([50.0], quantities=[2]))

    tm._action_take_loan(
        farmer,
        TurnResult(player_id=farmer.player_id, season=0, year=0),
        year=0,
        season_index=0,
    )

    customer_loan, funding_loan = loans.all_loans()
    assert customer_loan.borrower_id == farmer.player_id
    assert customer_loan.lender_id == banker.player_id
    assert customer_loan.term_years == 2
    assert customer_loan.interest_rate == posted_funding_rates(0, 0)[2] + 0.02
    assert funding_loan.borrower_id == banker.player_id
    assert funding_loan.lender_id == -1
    assert funding_loan.principal == 40.0
    assert funding_loan.interest_rate == posted_funding_rates(0, 0)[2]
    assert banker.dollops == 0.0
    assert farmer.dollops == 150.0
