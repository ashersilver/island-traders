from __future__ import annotations

from island_traders.cli.prompts import FakeIOAdapter
from island_traders.engine.game import Game, GameConfig, PlayerSpec
from island_traders.models.loan import Loan
from island_traders.models.resource import ResourceType


def _game() -> Game:
    game = Game(
        GameConfig([PlayerSpec("Farmer", ["Farmer"])]),
        FakeIOAdapter(),
    )
    game.setup()
    return game


def test_season_pl_history_accumulates_caps_and_resets():
    game = _game()
    player = game.players[0]
    player.receive_dollops(10.0)
    player.spend_dollops(4.0)

    for idx, season in enumerate(["Spring", "Summer", "Autumn", "Winter", "Spring"]):
        if idx:
            player.receive_dollops(idx)
        game.record_season_pl(season)
        game.reset_season_pl()

    assert len(player._pl_history) == 4
    assert player._pl_history[-1]["season"] == "Spring"
    assert player._season_revenue == 0.0
    assert player._season_costs == 0.0


def test_island_report_balance_deficiencies_and_manpower():
    game = _game()
    player = game.players[0]
    player.dollops = 100.0
    player.receive_resources(ResourceType.FOOD, 2)
    player.add_capital("farmer.tractor")
    player.mark_capital_failed("farmer.tractor")
    game.loan_ledger.loans.append(Loan(
        loan_id=1,
        borrower_id=player.player_id,
        lender_id=99,
        principal=25.0,
        interest_rate=0.1,
        issued_year=0,
        issued_season=0,
        maturity_year=1,
        maturity_season=0,
    ))

    report = game.island_report_for_player(player, game.market.current_prices(), 0)

    sheet = report["balance_sheet"]
    assert sheet["net_worth"] == round(
        sheet["treasury"] + sheet["inventory_value"] + sheet["capital_value"] - sheet["loans"],
        2,
    )
    assert report["deficiencies"][0]["item_id"] == "farmer.tractor"
    assert report["manpower"]["vacancies"] == (
        report["manpower"]["capacity"] - report["manpower"]["employed"]
    )
