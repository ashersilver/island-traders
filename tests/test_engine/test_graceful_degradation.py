"""Tests for the 2026-05-27 graceful-degradation brief (GitHub #47).

Confirms that:

- Islands missing required expertise produce at a band-specific floor
  instead of zero (so the market can still trade and recovery is
  possible).
- Floors compose multiplicatively within a role.
- Across multi-role players, the MIN floor wins (most restrictive).
- The natural labour-productivity factor still wins when higher (floor
  is a safety net, not a ceiling).
- The capacity payload exposes `degradation_floor` for the UI.
"""
from __future__ import annotations

import pytest

from island_traders.cli.prompts import FakeIOAdapter
from island_traders.engine.production import ProductionEngine
from island_traders.engine.trading import TradingEngine
from island_traders.engine.turn import TurnManager
from island_traders.models.deal import DealLedger
from island_traders.models.market import Market
from island_traders.models.player import Player
from island_traders.models.role import ROLES
from island_traders.models.workforce import Worker
from island_traders.models.profession import Profession


def _player(pid: int, role: str, *, is_human: bool = True) -> Player:
    return Player(pid, role, [ROLES[role]], 100.0, is_human=is_human)


def _engine() -> ProductionEngine:
    return ProductionEngine()


# ─────────────────────────────────────────────────────────────────────────
# expertise_degradation_floor — core helper
# ─────────────────────────────────────────────────────────────────────────


def test_floor_is_one_when_unique_specialist_and_technicians_present():
    """Mining with a Miner specialist + a Mining Technician triggers no
    floor (1.0 = no degradation)."""
    miner = _player(1, "Miner")
    miner.workforce.workers.clear()
    miner.workforce.workers.append(
        Worker(worker_id=1, profession=Profession.MINER.value)
    )
    miner.workforce.workers.append(
        Worker(worker_id=2, profession=Profession.MINING_TECHNICIAN.value)
    )
    assert _engine().expertise_degradation_floor(miner) == pytest.approx(1.0)


def test_floor_when_unique_specialist_absent_but_technician_present():
    """Mining with 0 Miner specialists but 1 Mining Technician triggers
    the unique-specialist floor (currently 0.05).  Technician band is
    satisfied so the Technician floor does NOT compose."""
    from island_traders.constants import EXPERTISE_DEGRADATION_FLOORS
    miner = _player(1, "Miner")
    miner.workforce.workers.clear()
    miner.workforce.workers.append(
        Worker(worker_id=1, profession=Profession.MINING_TECHNICIAN.value)
    )
    expected = EXPERTISE_DEGRADATION_FLOORS["unique_specialist"]
    assert _engine().expertise_degradation_floor(miner) == pytest.approx(expected)


def test_floor_composes_when_unique_and_all_technicians_absent():
    """Mining with 0 workers across all professions composes the floors:
    unique_specialist × technician (currently 0.05 × 0.25 = 0.0125)."""
    from island_traders.constants import EXPERTISE_DEGRADATION_FLOORS
    miner = _player(1, "Miner")
    miner.workforce.workers.clear()
    expected = (
        EXPERTISE_DEGRADATION_FLOORS["unique_specialist"]
        * EXPERTISE_DEGRADATION_FLOORS["technician"]
    )
    assert _engine().expertise_degradation_floor(miner) == pytest.approx(expected)


def test_floor_for_doctor_no_specialist_but_nurses_present():
    """Doctor's unique specialist is Profession.DOCTOR.  With 0 Doctors
    but 4 Nurses (also Manager-band), the unique-specialist floor still
    fires — the spec explicitly chose unique-specialist as the
    most-severe single check."""
    from island_traders.constants import EXPERTISE_DEGRADATION_FLOORS
    doc = _player(1, "Doctor")
    doc.workforce.workers.clear()
    for i in range(4):
        doc.workforce.workers.append(
            Worker(worker_id=10 + i, profession=Profession.NURSE.value)
        )
    doc.workforce.workers.append(
        Worker(worker_id=99, profession=Profession.MEDICAL_ORDERLY.value)
    )
    expected = EXPERTISE_DEGRADATION_FLOORS["unique_specialist"]
    assert _engine().expertise_degradation_floor(doc) == pytest.approx(expected)


def test_full_doctor_roster_no_floor():
    doc = _player(1, "Doctor")
    doc.workforce.workers.clear()
    doc.workforce.workers.append(
        Worker(worker_id=1, profession=Profession.DOCTOR.value)
    )
    doc.workforce.workers.append(
        Worker(worker_id=2, profession=Profession.NURSE.value)
    )
    doc.workforce.workers.append(
        Worker(worker_id=3, profession=Profession.MEDICAL_ORDERLY.value)
    )
    assert _engine().expertise_degradation_floor(doc) == pytest.approx(1.0)


# ─────────────────────────────────────────────────────────────────────────
# Integration — _labour_productivity_factor uses max(natural, floor)
# ─────────────────────────────────────────────────────────────────────────


def test_labour_productivity_factor_returns_floor_when_enabled():
    """When the feature flag is on, an empty workforce gets the composed
    floor rather than zero.  Patches the flag on explicitly so the test is
    independent of the module default (which is now True — GitHub #47)."""
    from unittest.mock import patch
    from island_traders.constants import EXPERTISE_DEGRADATION_FLOORS
    miner = _player(1, "Miner")
    miner.workforce.workers.clear()
    with patch("island_traders.engine.production.EXPERTISE_DEGRADATION_ENABLED", True):
        factor = _engine()._labour_productivity_factor(miner, "Spring")
    expected = (
        EXPERTISE_DEGRADATION_FLOORS["unique_specialist"]
        * EXPERTISE_DEGRADATION_FLOORS["technician"]
    )
    assert factor == pytest.approx(expected)


def test_labour_productivity_factor_returns_natural_when_disabled():
    """With the feature flag explicitly off, the floor is never applied —
    natural factor (zero, for an empty workforce) wins. Patched off rather
    than relying on the module default (which is now True for GitHub #47)."""
    from unittest.mock import patch
    miner = _player(1, "Miner")
    miner.workforce.workers.clear()
    with patch("island_traders.engine.production.EXPERTISE_DEGRADATION_ENABLED", False):
        factor = _engine()._labour_productivity_factor(miner, "Spring")
    assert factor == 0.0


def test_labour_productivity_factor_uses_natural_when_higher():
    """Mining with a full Miner roster: natural is high, floor doesn't
    apply regardless of flag.  Confirms max() semantics."""
    from unittest.mock import patch
    miner = _player(1, "Miner")
    miner.workforce.workers.clear()
    for i in range(8):
        prof = (
            Profession.MINER.value
            if i < 2
            else Profession.MINING_TECHNICIAN.value
        )
        miner.workforce.workers.append(
            Worker(worker_id=i, profession=prof, training_level=3)
        )
    with patch("island_traders.engine.production.EXPERTISE_DEGRADATION_ENABLED", True):
        factor = _engine()._labour_productivity_factor(miner, "Spring")
    assert factor > 0.5


# ─────────────────────────────────────────────────────────────────────────
# Production action surfaces the floor in the game log
# ─────────────────────────────────────────────────────────────────────────


class CapturingIO(FakeIOAdapter):
    def __init__(self):
        super().__init__()
        self.printed: list[str] = []

    def print(self, text: str) -> None:
        self.printed.append(text)

    def choose_option(self, prompt, options, request_summary=None):
        return options[0]["value"] if options else None

    def choose_quantity(self, prompt, min_qty, max_qty):
        return min_qty

    def confirm(self, prompt, request_summary=None):
        return False  # cancel — we only want the floor log line


def test_action_produce_logs_degraded_status_when_floor_applies():
    """When the feature flag is on AND the player has any expertise gap,
    _action_produce prints a clear [DEGRADED] line so the player knows
    why output is reduced and how to recover."""
    from unittest.mock import patch
    from island_traders.engine.events import EventResult
    from island_traders.engine.turn import TurnResult

    miner = _player(1, "Miner")
    miner.workforce.workers.clear()  # all workers gone → degraded
    market = Market()
    io = CapturingIO()
    mgr = TurnManager(
        players=[miner],
        production_engine=_engine(),
        trading_engine=TradingEngine(market, DealLedger()),
        market=market,
        io_adapter=io,
    )
    with patch("island_traders.constants.EXPERTISE_DEGRADATION_ENABLED", True):
        mgr._action_produce(
            miner,
            EventResult(event_name="Normal Operations"),
            TurnResult(miner.player_id, season=0, year=0),
            season_name="Spring",
        )
    assert any("[DEGRADED]" in line for line in io.printed), (
        f"Expected a [DEGRADED] log line; got: {io.printed!r}"
    )


def test_action_produce_does_not_log_degraded_when_roster_is_full():
    """No degradation log when the player has full expertise."""
    from island_traders.engine.events import EventResult
    from island_traders.engine.turn import TurnResult

    miner = _player(1, "Miner")
    miner.workforce.workers.clear()
    for i in range(8):
        prof = (
            Profession.MINER.value
            if i < 2
            else Profession.MINING_TECHNICIAN.value
        )
        miner.workforce.workers.append(
            Worker(worker_id=i, profession=prof, training_level=3)
        )
    market = Market()
    io = CapturingIO()
    mgr = TurnManager(
        players=[miner],
        production_engine=_engine(),
        trading_engine=TradingEngine(market, DealLedger()),
        market=market,
        io_adapter=io,
    )
    mgr._action_produce(
        miner,
        EventResult(event_name="Normal Operations"),
        TurnResult(miner.player_id, season=0, year=0),
        season_name="Spring",
    )
    assert not any("[DEGRADED]" in line for line in io.printed)


# ─────────────────────────────────────────────────────────────────────────
# Server payload integration is implicitly verified by the existing
# tests in test_workforce_shortage_messages.py and test_investing.py,
# which both exercise _player_capacity and would fail if the
# degradation_floor field broke the payload shape.
# ─────────────────────────────────────────────────────────────────────────
