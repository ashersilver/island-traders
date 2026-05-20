"""Economy Lifecycle Phase D1 — Banker capital-reserve / MBA leverage."""
from __future__ import annotations

from island_traders.constants import (
    MBA_RESERVE_RATIO_BASE, MBA_RESERVE_RATIO_QUALIFIED, MBA_QUALIFIED_THRESHOLD,
)
from island_traders.models.player import Player
from island_traders.models.profession import Profession
from island_traders.models.role import ROLES
from island_traders.models.workforce import Worker


def test_reserve_constants_match_spec():
    """50% base reserve; 20% with >=3 MBA Banker Managers."""
    assert MBA_RESERVE_RATIO_BASE == 0.50
    assert MBA_RESERVE_RATIO_QUALIFIED == 0.20
    assert MBA_QUALIFIED_THRESHOLD == 3


def test_worker_has_mba_defaults_false():
    w = Worker(worker_id=0)
    assert w.has_mba is False


def test_worker_has_mba_can_be_set():
    w = Worker(worker_id=0, profession=Profession.BANKER.value,
               training_level=1, has_mba=True)
    assert w.has_mba is True


# ---------------------------------------------------------------------------
# TurnManager helpers
# ---------------------------------------------------------------------------

def _bare_tm(players):
    from island_traders.cli.prompts import FakeIOAdapter
    from island_traders.engine.production import ProductionEngine
    from island_traders.engine.trading import TradingEngine
    from island_traders.engine.turn import TurnManager
    from island_traders.models.deal import DealLedger
    from island_traders.models.market import Market
    market = Market()
    return TurnManager(
        players=players,
        production_engine=ProductionEngine(),
        trading_engine=TradingEngine(market, DealLedger()),
        market=market,
        io_adapter=FakeIOAdapter(),
    )


def _banker(name="Bank", dollops=1000.0) -> Player:
    return Player(player_id=0, name=name, roles=[ROLES["Banker"]],
                  dollops=dollops, is_human=True)


def test_mba_banker_count_only_counts_banker_profession_with_mba_flag():
    banker = _banker()
    # Mix: 2 MBA Bankers, 1 non-MBA Banker, 1 MBA Banking Analyst (wrong profession).
    banker.workforce.add_workers(2, training_level=1, profession=Profession.BANKER.value)
    banker.workforce.add_workers(1, training_level=1, profession=Profession.BANKER.value)
    banker.workforce.add_workers(1, training_level=1,
                                  profession=Profession.BANKING_ANALYST.value)
    workers = banker.workforce.workers
    workers[0].has_mba = True
    workers[1].has_mba = True
    workers[3].has_mba = True   # Banking Analyst — should NOT count
    tm = _bare_tm([banker])
    assert tm._mba_banker_count(banker) == 2


def test_reserve_ratio_base_when_below_threshold():
    banker = _banker()
    banker.workforce.add_workers(2, training_level=1, profession=Profession.BANKER.value)
    for w in banker.workforce.workers:
        w.has_mba = True   # only 2 MBAs (< 3)
    tm = _bare_tm([banker])
    assert tm._banker_reserve_ratio(banker) == MBA_RESERVE_RATIO_BASE


def test_reserve_ratio_qualified_at_threshold():
    banker = _banker()
    banker.workforce.add_workers(3, training_level=1, profession=Profession.BANKER.value)
    for w in banker.workforce.workers:
        w.has_mba = True   # exactly 3 MBAs
    tm = _bare_tm([banker])
    assert tm._banker_reserve_ratio(banker) == MBA_RESERVE_RATIO_QUALIFIED


def test_reserve_ratio_stays_qualified_above_threshold():
    banker = _banker()
    banker.workforce.add_workers(5, training_level=1, profession=Profession.BANKER.value)
    for w in banker.workforce.workers:
        w.has_mba = True   # 5 MBAs (> 3)
    tm = _bare_tm([banker])
    assert tm._banker_reserve_ratio(banker) == MBA_RESERVE_RATIO_QUALIFIED


def test_in_training_banker_mba_does_not_count():
    """Only ACTIVE workers count toward MBA depth (workers away at
    training are out of the workforce that season)."""
    banker = _banker()
    banker.workforce.add_workers(3, training_level=1, profession=Profession.BANKER.value)
    for w in banker.workforce.workers:
        w.has_mba = True
    # Send one away — only 2 active MBAs remain → r should be base.
    away_id = banker.workforce.workers[0].worker_id
    banker.workforce.dispatch_for_training([away_id])
    tm = _bare_tm([banker])
    assert tm._mba_banker_count(banker) == 2
    assert tm._banker_reserve_ratio(banker) == MBA_RESERVE_RATIO_BASE
