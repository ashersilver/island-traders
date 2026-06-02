"""Engine-level tests for the mid-game shareholder loan actions.

The two actions:
  lend_to_island     — owner moves personal_cash → treasury (records a loan)
  repay_shareholder_loan — owner moves treasury → personal_cash (reduces loan)

Net-worth-neutral by construction (total_wealth subtracts the loan; net_worth
adds the receivable), so the tests pin the accounting invariants, not wealth.
"""
from __future__ import annotations

from island_traders.cli.prompts import FakeIOAdapter
from island_traders.engine.game import Game, GameConfig, PlayerSpec
from island_traders.engine.turn import TurnResult
from island_traders.models import shareholder_loans as sh_loans


class _LendIO(FakeIOAdapter):
    def __init__(self, amount):
        super().__init__()
        self._amount = amount

    def ask_dollop_amount(self, prompt, max_dollops, prefill=0.0):
        return self._amount


def _game():
    cfg = GameConfig(num_years=1, player_specs=[
        PlayerSpec(name="Farmer", role_names=["Farmer"], is_human=True),
    ])
    g = Game(cfg, FakeIOAdapter())
    g.setup()
    return g


# ---- lend_to_island --------------------------------------------------------

def test_lend_moves_cash_to_treasury_and_records_loan():
    g = _game()
    p = g.players[0]
    p.personal_cash = 200.0
    p.dollops = 500.0
    io = _LendIO(100.0)
    g.io = io
    g.turn_manager.io = io
    res = TurnResult(player_id=p.player_id, season="Spring", year=0)

    g.turn_manager._action_lend_to_island(p, res)

    assert p.personal_cash == 100.0
    assert p.dollops == 600.0
    assert sh_loans.total_owed(p.shareholder_loans) == 100.0
    assert "lend_to_island:100.0" in res.actions_taken


def test_lend_clamps_to_available_cash():
    g = _game()
    p = g.players[0]
    p.personal_cash = 50.0
    p.dollops = 100.0
    io = _LendIO(999.0)   # ask more than available
    g.io = io
    g.turn_manager.io = io
    res = TurnResult(player_id=p.player_id, season="Spring", year=0)

    g.turn_manager._action_lend_to_island(p, res)

    assert p.personal_cash == 0.0
    assert p.dollops == 150.0
    assert sh_loans.total_owed(p.shareholder_loans) == 50.0


def test_lend_with_no_cash_is_a_noop():
    g = _game()
    p = g.players[0]
    p.personal_cash = 0.0
    p.dollops = 200.0
    io = _LendIO(50.0)
    g.io = io
    g.turn_manager.io = io
    res = TurnResult(player_id=p.player_id, season="Spring", year=0)

    g.turn_manager._action_lend_to_island(p, res)

    assert p.dollops == 200.0
    assert sh_loans.total_owed(p.shareholder_loans) == 0.0
    assert not res.actions_taken


# ---- repay_shareholder_loan ------------------------------------------------

def test_repay_moves_treasury_to_personal_cash():
    g = _game()
    p = g.players[0]
    p.personal_cash = 0.0
    p.dollops = 600.0
    sh_loans.lend(p.shareholder_loans, str(p.player_id), 100.0)
    io = _LendIO(100.0)
    g.io = io
    g.turn_manager.io = io
    res = TurnResult(player_id=p.player_id, season="Spring", year=0)

    g.turn_manager._action_repay_shareholder_loan(p, res)

    assert p.personal_cash == 100.0
    assert p.dollops == 500.0
    assert sh_loans.total_owed(p.shareholder_loans) == 0.0
    assert "repay_shareholder_loan:100.0" in res.actions_taken


def test_repay_clamps_to_min_of_owed_and_treasury():
    g = _game()
    p = g.players[0]
    p.personal_cash = 0.0
    p.dollops = 40.0          # less than the loan
    sh_loans.lend(p.shareholder_loans, str(p.player_id), 200.0)
    io = _LendIO(999.0)
    g.io = io
    g.turn_manager.io = io
    res = TurnResult(player_id=p.player_id, season="Spring", year=0)

    g.turn_manager._action_repay_shareholder_loan(p, res)

    assert p.personal_cash == 40.0
    assert p.dollops == 0.0
    assert sh_loans.total_owed(p.shareholder_loans) == 160.0  # 200 - 40


def test_lend_then_full_repay_restores_original_state():
    g = _game()
    p = g.players[0]
    p.personal_cash = 300.0
    p.dollops = 500.0
    lend_io = _LendIO(150.0)
    g.io = lend_io; g.turn_manager.io = lend_io
    g.turn_manager._action_lend_to_island(
        p, TurnResult(player_id=p.player_id, season="Spring", year=0)
    )
    repay_io = _LendIO(150.0)
    g.io = repay_io; g.turn_manager.io = repay_io
    g.turn_manager._action_repay_shareholder_loan(
        p, TurnResult(player_id=p.player_id, season="Spring", year=0)
    )

    assert p.personal_cash == 300.0
    assert p.dollops == 500.0
    assert sh_loans.total_owed(p.shareholder_loans) == 0.0
