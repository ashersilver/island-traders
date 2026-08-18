"""Engine-level tests for the buy_float action (primary equity issuance).

buy_float — the controlling owner buys the island's unissued shares: personal
cash becomes island treasury cash and ownership rises, with no debt created
(contrast lend_to_island, which records a shareholder-loan liability). The
per-share price is a live fair value, so these tests pin the accounting/cap-
table invariants rather than an exact price.
"""
from __future__ import annotations

from island_traders.cli.prompts import FakeIOAdapter
from island_traders.engine.game import Game, GameConfig, PlayerSpec
from island_traders.engine.turn import TurnResult
from island_traders.models.equity import UNISSUED_HOLDER


class _BuyIO(FakeIOAdapter):
    def __init__(self, shares):
        super().__init__()
        self._shares = shares

    def ask_dollop_amount(self, prompt, max_dollops, prefill=0.0):
        return self._shares


def _game():
    cfg = GameConfig(num_years=1, player_specs=[
        PlayerSpec(name="Farmer", role_names=["Farmer"], is_human=True),
    ])
    g = Game(cfg, FakeIOAdapter())
    g.setup()
    return g


def _use_io(g, io):
    g.io = io
    g.turn_manager.io = io


def test_buy_float_moves_personal_cash_to_treasury_and_shares_to_owner():
    g = _game()
    p = g.players[0]
    assert p.cap_table is not None
    owner = str(p.player_id)
    p.personal_cash = 1000.0
    unissued_before = p.cap_table.unissued()
    held_before = p.cap_table.held_by(owner)
    liquid_before = round(p.personal_cash + p.dollops, 1)
    assert unissued_before >= 5

    _use_io(g, _BuyIO(5))
    res = TurnResult(player_id=p.player_id, season="Spring", year=0)
    g.turn_manager._action_buy_float(p, res, 0, 0)

    # Shares moved unissued -> owner; float shrank by exactly the amount bought.
    assert p.cap_table.unissued() == unissued_before - 5
    assert p.cap_table.held_by(owner) == held_before + 5
    assert p.holdings.get(owner, 0) >= 5
    # Equity raise: total liquid conserved (personal cash -> treasury), owner paid.
    assert round(p.personal_cash + p.dollops, 1) == liquid_before
    assert p.personal_cash < 1000.0
    assert p.dollops > 0
    assert any(a == "buy_float:5" for a in res.actions_taken)


def test_buy_float_clamps_to_available_float():
    g = _game()
    p = g.players[0]
    owner = str(p.player_id)
    p.personal_cash = 1_000_000.0  # effectively unlimited cash
    available = p.cap_table.unissued()

    _use_io(g, _BuyIO(available + 50))  # ask for more than exists
    res = TurnResult(player_id=p.player_id, season="Spring", year=0)
    g.turn_manager._action_buy_float(p, res, 0, 0)

    assert p.cap_table.unissued() == 0
    assert any(a == f"buy_float:{available}" for a in res.actions_taken)


def test_buy_float_with_no_cash_is_a_noop():
    g = _game()
    p = g.players[0]
    p.personal_cash = 0.0
    unissued_before = p.cap_table.unissued()

    _use_io(g, _BuyIO(5))
    res = TurnResult(player_id=p.player_id, season="Spring", year=0)
    g.turn_manager._action_buy_float(p, res, 0, 0)

    assert p.cap_table.unissued() == unissued_before
    assert not res.actions_taken


def test_buy_float_with_no_unissued_is_a_noop():
    g = _game()
    p = g.players[0]
    owner = str(p.player_id)
    p.personal_cash = 1000.0
    # Drain the float so nothing is left to issue.
    p.cap_table.transfer(UNISSUED_HOLDER, owner, p.cap_table.unissued())
    treasury_before = p.dollops

    _use_io(g, _BuyIO(5))
    res = TurnResult(player_id=p.player_id, season="Spring", year=0)
    g.turn_manager._action_buy_float(p, res, 0, 0)

    assert p.dollops == treasury_before
    assert p.personal_cash == 1000.0
    assert not res.actions_taken
