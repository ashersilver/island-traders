"""Economy Lifecycle Phase B — worker aging & retirement."""
from __future__ import annotations

from island_traders.constants import (
    WORKING_LIFE_SEASONS, DEFAULT_WORKING_LIFE_SEASONS, STARTING_WORKER_AGES,
)
from island_traders.models.profession import Profession, band_of, WorkerBand
from island_traders.models.training import TrainingRegistry, TrainingStatus
from island_traders.models.workforce import Workforce


def _life(profession: str) -> int:
    return WORKING_LIFE_SEASONS.get(
        band_of(profession).value, DEFAULT_WORKING_LIFE_SEASONS
    )


def test_worker_defaults_age_zero():
    wf = Workforce()
    w = wf.add_workers(1, profession=Profession.FARMER.value)[0]
    assert w.age_seasons == 0


def test_add_workers_accepts_seed_age():
    wf = Workforce()
    w = wf.add_workers(1, training_level=1,
                       profession=Profession.FARMER.value, age_seasons=36)[0]
    assert w.age_seasons == 36


def test_advance_age_increments_all_and_returns_nothing_when_young():
    wf = Workforce()
    wf.add_workers(2, profession=Profession.FARMER.value)
    wf.add_workers(1, profession=Profession.UNSKILLED.value)
    retired = wf.advance_age_and_retire(WORKING_LIFE_SEASONS,
                                        DEFAULT_WORKING_LIFE_SEASONS)
    assert retired == []
    assert all(w.age_seasons == 1 for w in wf.workers)
    assert wf.count == 3


def test_retires_at_band_working_life():
    wf = Workforce()
    mgr = wf.add_workers(1, training_level=1, profession=Profession.FARMER.value,
                         age_seasons=WORKING_LIFE_SEASONS["Manager"] - 1)[0]
    tech = wf.add_workers(1, training_level=1,
                          profession=Profession.FARMING_TECHNICIAN.value,
                          age_seasons=WORKING_LIFE_SEASONS["Technician"] - 1)[0]
    assert band_of(mgr.profession) == WorkerBand.MANAGER
    assert band_of(tech.profession) == WorkerBand.TECHNICIAN
    # One more season takes each to exactly its working life → retire.
    retired = wf.advance_age_and_retire(WORKING_LIFE_SEASONS,
                                        DEFAULT_WORKING_LIFE_SEASONS)
    retired_ids = {w.worker_id for w in retired}
    assert mgr.worker_id in retired_ids
    assert tech.worker_id in retired_ids
    assert wf.count == 0  # both removed from the roster


def test_unskilled_uses_worker_band_life():
    wf = Workforce()
    w = wf.add_workers(1, profession=Profession.UNSKILLED.value,
                       age_seasons=WORKING_LIFE_SEASONS["Worker"] - 1)[0]
    assert band_of(w.profession) == WorkerBand.WORKER
    retired = wf.advance_age_and_retire(WORKING_LIFE_SEASONS,
                                        DEFAULT_WORKING_LIFE_SEASONS)
    assert [r.worker_id for r in retired] == [w.worker_id]


def test_in_training_worker_still_ages_and_retires():
    wf = Workforce()
    w = wf.add_workers(1, training_level=1, profession=Profession.FARMER.value,
                       age_seasons=WORKING_LIFE_SEASONS["Manager"] - 1)[0]
    wf.dispatch_for_training([w.worker_id])
    assert w.in_training is True
    retired = wf.advance_age_and_retire(WORKING_LIFE_SEASONS,
                                        DEFAULT_WORKING_LIFE_SEASONS)
    assert [r.worker_id for r in retired] == [w.worker_id]
    assert retired[0].in_training is True   # caller drops it from its batch


def test_training_registry_drop_worker():
    reg = TrainingRegistry()
    req = reg.propose(
        requester_id=0, worker_ids=[10, 11], educator_id=9,
        dollops_to_educator=0.0, target_profession="FarmingTechnician",
        year=0, season=0, transport_mode="air_ticket",
    )
    reg.drop_worker(10)
    assert req.worker_ids == [11]
    assert req.status != TrainingStatus.REJECTED
    # Dropping the last worker rejects the now-empty request.
    reg.drop_worker(11)
    assert req.worker_ids == []
    assert req.status == TrainingStatus.REJECTED


def test_agriculture_bootstrap_seeding_retires_on_schedule():
    """Farmer (Manager) seeded ~1 yr out, Horticulturalist (Tech) ~2 yr.

    Mirrors the engine seeding (seed age = band life − seasons_left)
    and asserts the Farmer retires after ~4 seasons, Horticulturalist
    after ~8.
    """
    seeds = STARTING_WORKER_AGES["Farmer"]
    assert seeds == {"Farmer": 4, "Horticulturalist": 8}

    wf = Workforce()
    farmer = wf.add_workers(
        1, training_level=1, profession="Farmer",
        age_seasons=_life("Farmer") - seeds["Farmer"],
    )[0]
    hort = wf.add_workers(
        1, training_level=1, profession="Horticulturalist",
        age_seasons=_life("Horticulturalist") - seeds["Horticulturalist"],
    )[0]

    retired_ids: set[int] = set()
    for season in range(1, 9):
        for w in wf.advance_age_and_retire(WORKING_LIFE_SEASONS,
                                           DEFAULT_WORKING_LIFE_SEASONS):
            retired_ids.add((w.worker_id, season))
        if season == 4:
            assert any(wid == farmer.worker_id for wid, _ in retired_ids)
            assert not any(wid == hort.worker_id for wid, _ in retired_ids)

    assert any(wid == hort.worker_id and s == 8 for wid, s in retired_ids)
    assert wf.count == 0
