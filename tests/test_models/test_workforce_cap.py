"""Population cap on recruitable workforce (≤60% of population)."""
from __future__ import annotations

from island_traders.constants import MAX_WORKFORCE_FRACTION_OF_POPULATION
from island_traders.models.player import Player
from island_traders.models.profession import Profession
from island_traders.models.role import ROLES


def _farmer(population: int = 100, dollops: float = 100.0) -> Player:
    p = Player(0, "Farmer", [ROLES["Farmer"]], dollops, is_human=True)
    p.population = population
    return p


def test_workforce_cap_constant_is_sixty_percent():
    assert MAX_WORKFORCE_FRACTION_OF_POPULATION == 0.60


def test_available_unskilled_caps_workforce_at_sixty_percent_of_population():
    p = _farmer(population=100)
    # Fresh island with 0 workers: can recruit up to 60.
    assert p.workforce.count == 0
    assert p.available_unskilled == 60


def test_available_unskilled_subtracts_current_workforce():
    p = _farmer(population=100)
    p.workforce.add_workers(10, profession=Profession.UNSKILLED.value)
    assert p.workforce.count == 10
    assert p.available_unskilled == 50   # 60 cap − 10 current


def test_available_unskilled_is_zero_when_workforce_at_or_above_cap():
    p = _farmer(population=100)
    p.workforce.add_workers(60, profession=Profession.UNSKILLED.value)
    assert p.available_unskilled == 0
    # Above the cap (e.g. retained from a save / extra Mechanic): still 0.
    p.workforce.add_workers(5, profession=Profession.UNSKILLED.value)
    assert p.workforce.count == 65
    assert p.available_unskilled == 0


def test_recruit_workers_honours_the_cap():
    p = _farmer(population=100)
    p.workforce.add_workers(55, profession=Profession.UNSKILLED.value)
    # Cap is 60; only 5 slots left even though we ask for 20.
    actually_recruited = p.recruit_workers(20)
    assert actually_recruited == 5
    assert p.workforce.count == 60
    assert p.available_unskilled == 0


def test_smaller_population_shrinks_the_cap_proportionally():
    p = _farmer(population=40)
    # Cap = floor(0.6 × 40) = 24.
    assert p.available_unskilled == 24
    p.workforce.add_workers(20, profession=Profession.UNSKILLED.value)
    assert p.available_unskilled == 4


def test_profession_summary_excludes_workers_on_contract_from_active_counts():
    p = _farmer(population=100)
    workers = p.workforce.add_workers(2, profession=Profession.FARMER.value)
    workers[0].on_contract = True

    summary = p.workforce.profession_summary()

    assert summary[Profession.FARMER.value]["active"] == 1
