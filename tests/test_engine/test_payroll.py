from island_traders.cli.prompts import FakeIOAdapter
from island_traders.engine.game import Game, GameConfig
from island_traders.models.player import Player
from island_traders.models.profession import Profession
from island_traders.models.role import ROLES


def _payroll_game(player: Player) -> Game:
    game = Game(GameConfig([]), FakeIOAdapter())
    game.players = [player]
    return game


def test_payroll_charges_active_workers_by_band():
    player = Player(0, "Payroll Island", [ROLES["Manufacturer"]], 20.0, is_human=False)
    player.workforce.add_workers(1, profession=Profession.UNSKILLED.value)
    player.workforce.add_workers(1, profession=Profession.TRADESMAN.value)
    player.workforce.add_workers(1, profession=Profession.ENGINEER.value)
    game = _payroll_game(player)

    game._process_payroll(0, 0)

    assert player.dollops == 18.25
    assert player.household_cash == 1.75
    assert game.io.printed == [
        "[PAYROLL] Payroll Island: paid Dp1.75 to household wages."
    ]


def test_payroll_excludes_trainees_and_contracted_staff():
    player = Player(0, "Slim Payroll", [ROLES["Educator"]], 20.0, is_human=False)
    active_worker = player.workforce.add_workers(1, profession=Profession.UNSKILLED.value)[0]
    trainee = player.workforce.add_workers(1, profession=Profession.PROFESSOR.value)[0]
    contractor = player.workforce.add_workers(1, profession=Profession.INSTRUCTOR.value)[0]
    assert active_worker is not None
    trainee.in_training = True
    contractor.on_contract = True
    game = _payroll_game(player)

    game._process_payroll(0, 0)

    assert player.dollops == 19.75
    assert player.household_cash == 0.25


def test_payroll_shortfall_pays_available_cash_without_removing_workers():
    player = Player(0, "Broke Island", [ROLES["Banker"]], 0.5, is_human=False)
    player.workforce.add_workers(1, profession=Profession.BANKER.value)
    game = _payroll_game(player)

    game._process_payroll(0, 0)

    assert player.dollops == 0.0
    assert player.household_cash == 0.5
    assert player.workforce.count == 1
    assert game.io.printed == [
        "[PAYROLL SHORTFALL] Broke Island: paid Dp0.50 of Dp1.00; Dp0.50 unpaid."
    ]
