from __future__ import annotations

from island_traders.cli.prompts import FakeIOAdapter
from island_traders.engine.production import ProductionEngine
from island_traders.engine.trading import TradingEngine
from island_traders.engine.turn import TurnManager, TurnResult
from island_traders.models.deal import DealLedger
from island_traders.models.loan import (
    AI_BANKER_ACCEPT_SPREAD,
    AI_BANKER_COUNTER_FLOOR,
    CAPITAL_FINANCE_PREMIUM_PTS,
    LOAN_COUNTER_FLOOR_SPREAD,
    LoanLedger,
    LoanStatus,
    ai_banker_accept_rate,
    ai_banker_counter_rate,
    capital_finance_rate,
    posted_funding_rates,
)
from island_traders.models.market import Market
from island_traders.models.player import Player
from island_traders.models.role import ROLES


class LoanIO(FakeIOAdapter):
    def __init__(
        self,
        amounts: list[float],
        quantities: list[int] | None = None,
        options: list[object] | None = None,
        confirms: list[bool] | None = None,
    ):
        super().__init__()
        self.amounts = list(amounts)
        self.quantities = list(quantities or [])
        self.options = list(options or [])
        self.confirms = list(confirms or [])

    def ask_dollop_amount(self, prompt, max_dollops, prefill=0.0):
        return self.amounts.pop(0)

    def confirm(self, prompt, request_summary=None):
        if self.confirms:
            return self.confirms.pop(0)
        return True

    def choose_quantity(self, prompt, min_qty, max_qty):
        if self.quantities:
            return self.quantities.pop(0)
        return min_qty

    def choose_option(self, prompt, options, request_summary=None):
        if self.options:
            return self.options.pop(0)
        return options[0]["value"]


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


def test_ai_banker_accept_and_counter_helpers_use_boundary_spreads():
    posted = posted_funding_rates(0, 0)[2]
    risk = 0.01

    assert ai_banker_accept_rate(posted, risk) == round(
        posted + AI_BANKER_ACCEPT_SPREAD + risk, 4
    )
    assert ai_banker_counter_rate(0.06, 0.10, posted) == 0.08
    assert ai_banker_counter_rate(0.051, 0.052, posted) == round(
        posted + AI_BANKER_COUNTER_FLOOR, 4
    )


def test_take_loan_rejects_borrower_counter_below_floor():
    banker = Player(0, "Banker", [ROLES["Banker"]], 500.0, is_human=False)
    banker.workforce.add_workers(1, training_level=1, profession="Banker")
    farmer = Player(1, "Farmer", [ROLES["Farmer"]], 100.0, is_human=True)
    loans = LoanLedger()
    floor_pct = (posted_funding_rates(0, 0)[1] + LOAN_COUNTER_FLOOR_SPREAD) * 100
    io = LoanIO([50.0, floor_pct - 0.1], quantities=[1], options=["counter"])
    tm = _turn_manager([farmer, banker], loans, io)

    tm._action_take_loan(farmer, TurnResult(farmer.player_id, 0, 0), 0, 0)

    assert loans.all_loans() == []
    assert "Counter rejected" in "\n".join(io.printed)


def test_take_loan_ai_banker_accepts_valid_counter_at_threshold():
    banker = Player(0, "Banker", [ROLES["Banker"]], 500.0, is_human=False)
    banker.workforce.add_workers(1, training_level=1, profession="Banker")
    farmer = Player(1, "Farmer", [ROLES["Farmer"]], 100.0, is_human=True)
    loans = LoanLedger()
    posted = posted_funding_rates(0, 0)[1]
    counter_rate = posted + AI_BANKER_ACCEPT_SPREAD
    io = LoanIO([50.0, counter_rate * 100], quantities=[1], options=["counter"])
    tm = _turn_manager([farmer, banker], loans, io)

    tm._action_take_loan(farmer, TurnResult(farmer.player_id, 0, 0), 0, 0)

    customer_loan, _funding_loan = loans.all_loans()
    assert customer_loan.interest_rate == round(counter_rate, 4)


def test_take_loan_human_banker_decline_creates_no_loan():
    banker = Player(0, "Banker", [ROLES["Banker"]], 500.0, is_human=True)
    banker.workforce.add_workers(1, training_level=1, profession="Banker")
    farmer = Player(1, "Farmer", [ROLES["Farmer"]], 100.0, is_human=True)
    loans = LoanLedger()
    posted = posted_funding_rates(0, 0)[1]
    io = LoanIO(
        [50.0, (posted + LOAN_COUNTER_FLOOR_SPREAD) * 100],
        quantities=[1],
        options=["counter", "decline"],
    )
    tm = _turn_manager([farmer, banker], loans, io)

    tm._action_take_loan(farmer, TurnResult(farmer.player_id, 0, 0), 0, 0)

    assert loans.all_loans() == []
    assert "declined" in "\n".join(io.printed)


def test_capital_finance_rate_uses_three_year_posted_plus_premium():
    assert capital_finance_rate(0, 0) == round(
        posted_funding_rates(0, 0)[3] + CAPITAL_FINANCE_PREMIUM_PTS,
        4,
    )


def test_secured_loan_default_repossesses_collateral_and_credits_lender():
    # #189: a secured loan that defaults must seize the pledged capital item
    # from the borrower and credit the lender its book value (capped at the
    # shortfall). Borrower can't repay; lender is a distinct player.
    borrower = Player(
        player_id=0, name="Miner", roles=[ROLES["Miner"]], dollops=0.0, is_human=True,
    )
    borrower.add_capital("miner.crusher", 1)  # cost 50.0
    lender = Player(
        player_id=1, name="Banker", roles=[ROLES["Banker"]], dollops=100.0, is_human=True,
    )
    loans = LoanLedger()
    loans.create_loan(
        borrower_id=borrower.player_id,
        lender_id=lender.player_id,
        principal=200.0,
        interest_rate=0.05,
        issued_year=0,
        issued_season=0,
        term_years=1,
        collateral_item_id="miner.crusher",
        secured=True,
    )
    tm = _turn_manager([borrower, lender], loans, LoanIO([]))

    tm._process_loan_repayments(year=1, season=0)

    loan = loans.all_loans()[0]
    assert loan.status == LoanStatus.DEFAULTED
    # collateral seized from the borrower
    assert borrower.capital_inventory.get("miner.crusher", 0) == 0
    # lender recovers book value (50), capped at the 210 shortfall -> full 50
    assert lender.dollops == 150.0


def test_unsecured_loan_default_does_not_touch_capital():
    borrower = Player(
        player_id=0, name="Miner", roles=[ROLES["Miner"]], dollops=0.0, is_human=True,
    )
    borrower.add_capital("miner.crusher", 1)
    lender = Player(
        player_id=1, name="Banker", roles=[ROLES["Banker"]], dollops=100.0, is_human=True,
    )
    loans = LoanLedger()
    loans.create_loan(
        borrower_id=borrower.player_id, lender_id=lender.player_id, principal=200.0,
        interest_rate=0.05, issued_year=0, issued_season=0, term_years=1,
    )  # secured defaults False
    tm = _turn_manager([borrower, lender], loans, LoanIO([]))

    tm._process_loan_repayments(year=1, season=0)

    assert loans.all_loans()[0].status == LoanStatus.DEFAULTED
    assert borrower.capital_inventory.get("miner.crusher", 0) == 1  # untouched
    assert lender.dollops == 100.0  # no recovery credit
