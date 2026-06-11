from island_traders.models.loan import LoanLedger
from island_traders.models.player import Player
from island_traders.models.resource import ResourceType
from island_traders.models.role import ROLES
from island_traders.constants_capacity import CAPITAL_CATALOGUE


def _player(player_id: int, dollops: float) -> Player:
    return Player(
        player_id=player_id,
        name=f"P{player_id}",
        roles=[ROLES["Farmer"]],
        dollops=dollops,
    )


def test_total_wealth_is_net_of_loans_and_receivables():
    borrower = _player(1, 100.0)
    lender = _player(2, 50.0)
    borrower.receive_resources(ResourceType.FOOD, 2)
    prices = {ResourceType.FOOD: 10.0}

    loans = LoanLedger()
    loans.create_loan(
        borrower_id=borrower.player_id,
        lender_id=lender.player_id,
        principal=40.0,
        interest_rate=0.25,
        issued_year=0,
        issued_season=0,
    )

    assert borrower.total_wealth(prices, loans) == 70.0
    assert lender.total_wealth(prices, loans) == 100.0


def test_wealth_breakdown_components_sum_to_total_wealth():
    # Exercise every signed driver: cash, inventory, a bank loan (debt on the
    # borrower, receivable on the lender), and a shareholder loan.
    borrower = _player(1, 100.0)
    lender = _player(2, 50.0)
    borrower.receive_resources(ResourceType.FOOD, 3)
    borrower.shareholder_loans["9"] = 15.0
    prices = {ResourceType.FOOD: 10.0}

    loans = LoanLedger()
    loans.create_loan(
        borrower_id=borrower.player_id,
        lender_id=lender.player_id,
        principal=40.0,
        interest_rate=0.25,
        issued_year=0,
        issued_season=0,
    )

    for p in (borrower, lender):
        bd = p.wealth_breakdown(prices, loans, CAPITAL_CATALOGUE)
        assert sum(bd["components"].values()) == bd["total"]
        assert bd["total"] == p.total_wealth(prices, loans, CAPITAL_CATALOGUE)

    bd = borrower.wealth_breakdown(prices, loans, CAPITAL_CATALOGUE)
    assert bd["components"]["bank_debt"] < 0
    assert bd["components"]["shareholder_debt"] == -15.0
    # Receivable is the repayment amount (principal + interest = 40 × 1.25).
    assert lender.wealth_breakdown(prices, loans)["components"]["loans_receivable"] == 50.0


def test_inventory_report_labels_net_wealth():
    player = _player(1, 100.0)
    report = player.inventory_report({}, LoanLedger())

    assert "Net Wealth:" in report
    assert "Total Wealth:" not in report


def test_total_wealth_includes_depreciated_capital_equipment_book_value():
    player = _player(1, 100.0)
    player.add_capital("farmer.tractor", acquired_tick=0)

    assert player.capital_book_value(CAPITAL_CATALOGUE, current_tick=0) == 60.0
    assert player.capital_book_value(CAPITAL_CATALOGUE, current_tick=10) == 30.0
    assert player.capital_book_value(CAPITAL_CATALOGUE, current_tick=20) == 0.0
    assert player.total_wealth({}, LoanLedger(), CAPITAL_CATALOGUE, current_tick=10) == 130.0
