"""Tests for the three-band worker classification (Manager / Technician / Worker)."""
from __future__ import annotations

from island_traders.models.profession import (
    Profession, WorkerBand, PROFESSION_BAND, BAND_TITLES,
    band_of, primary_title, EDUCATION_SEASONS, APPRENTICESHIP_SEASONS,
)
from island_traders.models.workforce import Workforce


def test_every_profession_has_a_band():
    for p in Profession:
        assert p in PROFESSION_BAND, f"{p} missing from PROFESSION_BAND"


def test_band_classifications():
    # Managers: university-trained
    assert band_of(Profession.DOCTOR)    == WorkerBand.MANAGER
    assert band_of(Profession.NURSE)     == WorkerBand.MANAGER
    assert band_of(Profession.ENGINEER)  == WorkerBand.MANAGER
    assert band_of(Profession.BANKER)    == WorkerBand.MANAGER
    assert band_of(Profession.PROFESSOR) == WorkerBand.MANAGER
    assert band_of(Profession.FARMER)    == WorkerBand.MANAGER
    assert band_of(Profession.MINER)     == WorkerBand.MANAGER

    # Technicians: apprenticeship-trained
    assert band_of(Profession.MECHANIC)            == WorkerBand.TECHNICIAN
    assert band_of(Profession.FARMING_TECHNICIAN)  == WorkerBand.TECHNICIAN
    assert band_of(Profession.MINING_TECHNICIAN)   == WorkerBand.TECHNICIAN
    assert band_of(Profession.VETERINARIAN)        == WorkerBand.TECHNICIAN
    assert band_of(Profession.ASSEMBLY_WORKER)     == WorkerBand.TECHNICIAN
    assert band_of(Profession.OIL_EXTRACTION)      == WorkerBand.TECHNICIAN
    assert band_of(Profession.REFINERY_SPECIALIST) == WorkerBand.TECHNICIAN

    # Worker tier
    assert band_of(Profession.UNSKILLED) == WorkerBand.WORKER


def test_band_of_accepts_string():
    assert band_of("Doctor") == WorkerBand.MANAGER
    assert band_of("Mechanic") == WorkerBand.TECHNICIAN
    assert band_of("Unknown") == WorkerBand.WORKER  # fallback


def test_every_island_has_titles_for_all_three_bands():
    expected_roles = {"Farmer", "Miner", "Transporter", "Educator",
                       "Banker", "Manufacturer", "Doctor"}
    assert set(BAND_TITLES.keys()) == expected_roles
    for role, by_band in BAND_TITLES.items():
        for band in WorkerBand:
            assert band in by_band, f"{role} missing band {band}"
            assert by_band[band], f"{role} {band} title list is empty"


def test_primary_title_examples():
    assert primary_title("Farmer", WorkerBand.WORKER) == "Farmhand"
    assert primary_title("Miner", WorkerBand.WORKER) == "Pit Worker"
    assert primary_title("Transporter", WorkerBand.WORKER) == "Stevedore"
    assert primary_title("Doctor", WorkerBand.MANAGER) == "Doctor"


def test_education_and_apprenticeship_durations():
    assert EDUCATION_SEASONS[Profession.DOCTOR] == 2
    assert EDUCATION_SEASONS[Profession.NURSE] == 1   # Nurse is faster per requirements
    for p, seasons in APPRENTICESHIP_SEASONS.items():
        assert seasons >= 1


def test_workforce_band_helpers():
    wf = Workforce()
    wf.add_workers(1, training_level=1, profession=Profession.DOCTOR.value)
    wf.add_workers(2, training_level=1, profession=Profession.MECHANIC.value)
    wf.add_workers(3, profession=Profession.UNSKILLED.value)

    summary = wf.band_summary()
    assert summary["Manager"] == 1
    assert summary["Technician"] == 2
    assert summary["Worker"] == 3

    assert wf.count_by_band(WorkerBand.MANAGER) == 1
    assert wf.count_by_band(WorkerBand.TECHNICIAN) == 2
    assert wf.count_by_band(WorkerBand.WORKER) == 3

    assert wf.has_mechanic() is True
    assert wf.mechanic_count() == 2
