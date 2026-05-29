"""Tests for the Request Training menu UX (Bug fix: 'Banker option disappeared').

Two related fixes:
  1. UNIVERSITY_CAPACITY now includes training caps for the new professions
     introduced with the workforce ≥1M+2T rule (LogisticsManager, FlightCrew,
     Seaman, WarehouseManager, Lecturer, Instructor, BankingAnalyst, BankingClerk,
     MedicalOrderly) plus later playtest titles (FactoryForeman, MiningForeman)
     so they can actually be trained into.
  2. The Request Training menu prints exhausted professions with their cap
     status (so the player sees WHY an option isn't selectable, instead of it
     just vanishing from the list).
"""
from __future__ import annotations

import pytest

from island_traders.constants import UNIVERSITY_CAPACITY
from island_traders.models.profession import Profession, PROFESSION_BAND, WorkerBand
from island_traders.models.training import TrainingRegistry


def test_new_professions_have_training_caps():
    """The new professions added with the workforce baseline/playtest passes must all have
    UNIVERSITY_CAPACITY entries so they can be trained into."""
    new_professions = [
        "LogisticsManager", "FlightCrew", "Seaman", "WarehouseManager",
        "Lecturer", "Instructor",   # Tutor consolidated into Instructor (Phase 2)
        "BankingAnalyst", "BankingClerk",
        "MedicalOrderly",
        "FactoryForeman", "MiningForeman",
    ]
    for prof in new_professions:
        assert prof in UNIVERSITY_CAPACITY, (
            f"{prof} missing from UNIVERSITY_CAPACITY — cannot be trained into"
        )
        assert UNIVERSITY_CAPACITY[prof] > 0, (
            f"{prof}: training cap must be positive"
        )


def test_every_profession_with_a_band_is_trainable_or_unskilled():
    """Every profession (other than Unskilled) should have a training cap.
    Otherwise the menu won't surface it and the player can't grow that role."""
    untrainable = []
    for prof, band in PROFESSION_BAND.items():
        if prof == Profession.UNSKILLED:
            continue
        if prof.value not in UNIVERSITY_CAPACITY:
            untrainable.append(prof.value)
    assert not untrainable, (
        f"These professions have no training cap (cannot be sent to college): "
        f"{untrainable}"
    )


def test_capacity_summary_includes_new_professions():
    """A fresh registry should report capacity_summary entries for every
    profession in UNIVERSITY_CAPACITY."""
    reg = TrainingRegistry()
    summary = reg.capacity_summary(year=0, season=0)
    for prof in UNIVERSITY_CAPACITY:
        assert prof in summary
        info = summary[prof]
        assert info["annual_cap"] == UNIVERSITY_CAPACITY[prof]
        assert info["trained"] == 0
        # remaining may be lower than the annual cap when a seasonal cap
        # applies (e.g. Professor is 4/year but 1/season).  At minimum it
        # should be > 0 (fresh registry) and ≤ annual_cap.
        assert 0 < info["remaining"] <= UNIVERSITY_CAPACITY[prof]


def test_banker_has_at_least_two_slots_to_match_starting_workforce_needs():
    """Banker is the most-asked-about profession — keep the cap >= 2 so a
    new Banker can train at least one extra Banker manager per year without
    immediately exhausting the cap (the original playtest bug was the user
    feeling like the option disappeared too quickly)."""
    assert UNIVERSITY_CAPACITY["Banker"] >= 2


def test_request_training_menu_shows_exhausted_professions(monkeypatch):
    """After Banker's annual cap is exhausted, the menu should still print a
    line for Banker showing it's FULL — not silently omit it."""
    from island_traders.engine.production import ProductionEngine
    from island_traders.engine.trading import TradingEngine
    from island_traders.engine.turn import TurnManager, TurnResult
    from island_traders.cli.prompts import FakeIOAdapter
    from island_traders.cli.signals import ActionCancelled
    from island_traders.models.deal import DealLedger
    from island_traders.models.market import Market
    from island_traders.models.player import Player
    from island_traders.models.role import ROLES

    # IO that captures print output and cancels at the profession picker.
    class CapturingIO(FakeIOAdapter):
        def __init__(self):
            super().__init__()
            self.log = []
        def print(self, text):
            self.log.append(text)
        def choose_profession(self, prompt, available):
            raise ActionCancelled()
        def choose_quantity(self, prompt, min_qty, max_qty):
            return 1

    player = Player(player_id=0, name="P", roles=[ROLES["Farmer"]],
                    dollops=100.0, is_human=True)
    educator = Player(player_id=1, name="E", roles=[ROLES["Educator"]],
                      dollops=100.0, is_human=True)
    market = Market()
    io = CapturingIO()
    tm = TurnManager(
        players=[player, educator],
        production_engine=ProductionEngine(),
        trading_engine=TradingEngine(market, DealLedger()),
        market=market,
        io_adapter=io,
    )

    # Force Banker's annual cap to be exhausted by inserting a fake completed
    # batch.  Use registry's propose() to keep state consistent.
    banker_cap = UNIVERSITY_CAPACITY["Banker"]
    worker_ids = list(range(banker_cap))
    tm.training.propose(
        requester_id=player.player_id,
        worker_ids=worker_ids,
        educator_id=educator.player_id,
        dollops_to_educator=0.0,
        target_profession="Banker",
        year=0, season=0,
    )

    result = TurnResult(player_id=player.player_id, season=0, year=0)
    try:
        tm._action_request_training(player, result, season_name="Spring", year=0)
    except ActionCancelled:
        pass

    log = "\n".join(io.log)
    # The menu must show "Banker" FULL — even though it has 0 remaining.
    assert "Banker" in log
    assert "FULL" in log


def test_request_training_menu_shows_skill_deficits_and_can_bundle_them():
    from island_traders.engine.production import ProductionEngine
    from island_traders.engine.trading import TradingEngine
    from island_traders.engine.turn import TurnManager, TurnResult
    from island_traders.cli.prompts import FakeIOAdapter
    from island_traders.models.deal import DealLedger
    from island_traders.models.market import Market
    from island_traders.models.player import Player
    from island_traders.models.profession import Profession
    from island_traders.models.role import ROLES

    class BundleIO(FakeIOAdapter):
        def choose_profession(self, prompt, available):
            assert "All visible skill deficits" in available
            return "All visible skill deficits"
        def ask_dollop_amount(self, prompt, max_dollops):
            return 100.0

    player = Player(player_id=0, name="P", roles=[ROLES["Doctor"]],
                    dollops=200.0, is_human=True)
    player.workforce.add_workers(4, profession=Profession.UNSKILLED.value)
    educator = Player(player_id=1, name="E", roles=[ROLES["Educator"]],
                      dollops=100.0, is_human=True)
    market = Market()
    io = BundleIO()
    tm = TurnManager(
        players=[player, educator],
        production_engine=ProductionEngine(),
        trading_engine=TradingEngine(market, DealLedger()),
        market=market,
        io_adapter=io,
    )

    result = TurnResult(player_id=player.player_id, season=0, year=0)
    tm._action_request_training(player, result, season_name="Spring", year=0)

    log = "\n".join(io.printed)
    assert "Skill deficits against your island staffing plan" in log
    assert "Doctor" in log and "need 2" in log
    assert "Nurse" in log and "need 2" in log
    assert "MedicalOrderly" in log and "need 2" in log

    requests = tm.training.all_requests()
    assert [(r.target_profession, len(r.worker_ids)) for r in requests] == [
        ("Doctor", 2),
        ("Nurse", 2),
    ]
