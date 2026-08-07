"""One Actuary per line of insurance business (#196).

> "The rule should be that the bank needs an actuary for each line of
> insurance business."

A *line* is a policy type — life, medical — not an individual policy. Writing
more of a line already running is free; opening a new one needs a spare
Actuary. Only in-force policies count, so a line that runs off frees its
Actuary again.
"""
from __future__ import annotations

from island_traders.cli.prompts import FakeIOAdapter
from island_traders.constants import INSURANCE_DURATION_SEASONS
from island_traders.engine.production import ProductionEngine
from island_traders.engine.trading import TradingEngine
from island_traders.engine.turn import TurnManager
from island_traders.models.deal import DealLedger
from island_traders.models.insurance import InsurancePolicy
from island_traders.models.market import Market
from island_traders.models.player import Player
from island_traders.models.profession import Profession
from island_traders.models.role import ROLES


def _banker(actuaries: int = 1) -> Player:
    banker = Player(0, "Bank", [ROLES["Banker"]], 5_000.0, is_human=True)
    if actuaries:
        banker.workforce.add_workers(actuaries, profession=Profession.ACTUARY.value)
    return banker


def _client(pid: int = 1, role: str = "Miner") -> Player:
    return Player(pid, f"Client{pid}", [ROLES[role]], 1_000.0, is_human=False)


def _tm(players) -> TurnManager:
    market = Market()
    return TurnManager(
        players=players,
        production_engine=ProductionEngine(),
        trading_engine=TradingEngine(market, DealLedger()),
        market=market,
        io_adapter=FakeIOAdapter(),
    )


def _write(holder: Player, banker: Player, policy_type: str, tick: int = 0) -> None:
    holder.add_insurance_policy(InsurancePolicy(
        policy_id=len(holder.insurance_policies) + 1,
        policy_type=policy_type,
        holder_player_id=holder.player_id,
        banker_player_id=banker.player_id,
        premium_paid=50.0,
        purchased_tick=tick,
        expires_at_tick=tick + INSURANCE_DURATION_SEASONS,
    ))


def test_a_bank_with_no_actuary_cannot_write_anything():
    banker, client = _banker(actuaries=0), _client()
    tm = _tm([banker, client])

    allowed, reason = tm._banker_can_write_line(banker, "life", 0, 0)

    assert not allowed
    assert "no Actuary" in reason


def test_one_actuary_covers_one_line():
    banker, client = _banker(actuaries=1), _client()
    tm = _tm([banker, client])

    assert tm._banker_can_write_line(banker, "life", 0, 0)[0]
    _write(client, banker, "life")

    # More of the same line is fine — the Actuary is already on it.
    assert tm._banker_can_write_line(banker, "life", 0, 0)[0]


def test_one_actuary_cannot_open_a_second_line():
    banker, client = _banker(actuaries=1), _client()
    tm = _tm([banker, client])
    _write(client, banker, "life")

    allowed, reason = tm._banker_can_write_line(banker, "medical", 0, 0)

    assert not allowed
    assert "medical" in reason
    assert "Train another Actuary" in reason


def test_a_second_actuary_opens_the_second_line():
    banker, client = _banker(actuaries=2), _client()
    tm = _tm([banker, client])
    _write(client, banker, "life")

    assert tm._banker_can_write_line(banker, "medical", 0, 0)[0]


def test_lines_are_counted_across_all_clients():
    """Two clients on the same line is still one line."""
    banker = _banker(actuaries=1)
    a, b = _client(1), _client(2)
    tm = _tm([banker, a, b])
    _write(a, banker, "life")
    _write(b, banker, "life")

    assert tm._banker_open_lines(banker, 0, 0) == {"life"}
    assert tm._banker_can_write_line(banker, "life", 0, 0)[0]
    assert not tm._banker_can_write_line(banker, "medical", 0, 0)[0]


def test_a_lapsed_line_frees_its_actuary():
    banker, client = _banker(actuaries=1), _client()
    tm = _tm([banker, client])
    _write(client, banker, "life", tick=0)

    # Past expiry, the life book is run off.
    later = INSURANCE_DURATION_SEASONS + 1
    assert tm._banker_open_lines(banker, later // 4, later % 4) == set()
    assert tm._banker_can_write_line(banker, "medical", later // 4, later % 4)[0]


def test_another_banks_policies_do_not_occupy_your_actuary():
    ours, theirs = _banker(actuaries=1), Player(9, "Rival", [ROLES["Banker"]], 500.0)
    client = _client()
    tm = _tm([ours, theirs, client])
    _write(client, theirs, "life")

    assert tm._banker_open_lines(ours, 0, 0) == set()
    assert tm._banker_can_write_line(ours, "medical", 0, 0)[0]
