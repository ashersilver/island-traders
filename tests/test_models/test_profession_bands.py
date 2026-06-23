"""Tests for the three-band worker classification (Manager / Technician / Worker)."""
from __future__ import annotations

from island_traders.models.profession import (
    Profession, WorkerBand, PROFESSION_BAND, BAND_TITLES,
    band_of, primary_title, EDUCATION_SEASONS, APPRENTICESHIP_SEASONS,
    APPRENTICESHIP_SETTLING_SEASONS, APPRENTICESHIP_SETTLING_EFFICIENCY,
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
    assert band_of(Profession.MARINE_BIOLOGIST) == WorkerBand.MANAGER
    assert band_of(Profession.MINER)     == WorkerBand.MANAGER

    # Technicians: apprenticeship-trained
    assert band_of(Profession.MECHANIC)            == WorkerBand.TECHNICIAN
    assert band_of(Profession.FARMING_TECHNICIAN)  == WorkerBand.TECHNICIAN
    assert band_of(Profession.FISH_PROCESSING_TECHNICIAN) == WorkerBand.TECHNICIAN
    assert band_of(Profession.MINING_TECHNICIAN)   == WorkerBand.TECHNICIAN
    assert band_of(Profession.VETERINARIAN)        == WorkerBand.TECHNICIAN
    assert band_of(Profession.ASSEMBLY_WORKER)     == WorkerBand.TECHNICIAN
    assert band_of(Profession.FACTORY_FOREMAN)      == WorkerBand.TECHNICIAN
    assert band_of(Profession.OIL_EXTRACTION)      == WorkerBand.TECHNICIAN
    assert band_of(Profession.REFINERY_SPECIALIST) == WorkerBand.TECHNICIAN
    assert band_of(Profession.MINING_FOREMAN)      == WorkerBand.TECHNICIAN

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
    # #18 reconciliation (ruled 2026-06-18): Doctor 4 seasons, Nurse 1,
    # Engineer 3, other Managers 2.
    assert EDUCATION_SEASONS[Profession.DOCTOR] == 4
    assert EDUCATION_SEASONS[Profession.NURSE] == 1
    assert EDUCATION_SEASONS[Profession.ENGINEER] == 3
    # Every Technician apprenticeship is 1 season away when the campus has a
    # Technical Workshop; no-workshop courses add one 50%-productivity settling
    # season on the home island.
    for p, seasons in APPRENTICESHIP_SEASONS.items():
        assert seasons == 1
    assert APPRENTICESHIP_SETTLING_SEASONS == 1
    assert APPRENTICESHIP_SETTLING_EFFICIENCY == 0.50


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


# ---------------------------------------------------------------------------
# Transport-related professions (new — added with the ≥1M+2T workforce rule)
# ---------------------------------------------------------------------------

def test_new_transporter_professions_have_correct_bands():
    """Logistics Manager is a Manager; Flight Crew, Seaman, Warehouse Manager
    are all Technicians (Warehouse Manager despite the title — it's a ground-
    ops supervisor in the operational tier)."""
    assert band_of(Profession.LOGISTICS_MANAGER) == WorkerBand.MANAGER
    assert band_of(Profession.FLIGHT_CREW)       == WorkerBand.TECHNICIAN
    assert band_of(Profession.SEAMAN)            == WorkerBand.TECHNICIAN
    assert band_of(Profession.WAREHOUSE_MANAGER) == WorkerBand.TECHNICIAN


def test_new_technician_professions_for_educator_banker_doctor():
    assert band_of(Profession.LECTURER)        == WorkerBand.MANAGER
    assert band_of(Profession.INSTRUCTOR)      == WorkerBand.TECHNICIAN
    assert band_of(Profession.ACTUARY)         == WorkerBand.TECHNICIAN
    assert band_of(Profession.BANKING_ANALYST) == WorkerBand.TECHNICIAN
    assert band_of(Profession.BANKING_CLERK)   == WorkerBand.TECHNICIAN
    assert band_of(Profession.TRADESMAN)       == WorkerBand.TECHNICIAN
    assert band_of(Profession.MEDICAL_ORDERLY) == WorkerBand.TECHNICIAN
    assert band_of(Profession.MEDICAL_RESEARCHER) == WorkerBand.MANAGER
    assert band_of(Profession.MEDICAL_TECHNICIAN) == WorkerBand.TECHNICIAN


def test_transporter_band_titles_use_new_profession_names():
    titles = BAND_TITLES["Transporter"]
    assert "Logistics Manager" in titles[WorkerBand.MANAGER]
    assert "Flight Crew"       in titles[WorkerBand.TECHNICIAN]
    assert "Seaman"            in titles[WorkerBand.TECHNICIAN]
    assert "Warehouse Manager" in titles[WorkerBand.TECHNICIAN]


# ---------------------------------------------------------------------------
# Invariant: every island starts with at least 1 Manager + 2 Technicians
# ---------------------------------------------------------------------------

def test_every_island_starts_with_at_least_one_manager_and_two_technicians():
    """Workforce baseline rule — every role must have at least 1 Manager and
    2 Technicians among its starting workers (unskilled remainder excluded)."""
    from island_traders.constants import (
        STARTING_WORKERS_BY_PROFESSION, STARTING_WORKFORCE,
    )
    for role, breakdown in STARTING_WORKERS_BY_PROFESSION.items():
        managers = 0
        technicians = 0
        for prof_name, count in breakdown:
            band = band_of(prof_name)
            if band == WorkerBand.MANAGER:
                managers += count
            elif band == WorkerBand.TECHNICIAN:
                technicians += count
        assert managers >= 1, (
            f"{role}: starts with {managers} Manager(s); rule requires ≥ 1"
        )
        assert technicians >= 2, (
            f"{role}: starts with {technicians} Technician(s); rule requires ≥ 2"
        )
        # Sanity check: explicit professions can't exceed total workforce
        explicit_total = sum(c for _, c in breakdown)
        assert explicit_total <= STARTING_WORKFORCE[role], (
            f"{role}: explicit {explicit_total} > STARTING_WORKFORCE "
            f"{STARTING_WORKFORCE[role]}"
        )


def test_every_profession_has_a_label():
    from island_traders.models.profession import PROFESSION_LABEL
    for p in Profession:
        assert p in PROFESSION_LABEL, f"{p} missing from PROFESSION_LABEL"


def test_every_role_profession_has_band_label_and_training_capacity():
    from island_traders.constants import UNIVERSITY_CAPACITY
    from island_traders.models.profession import PROFESSION_LABEL, ROLE_PROFESSIONS

    for role, professions in ROLE_PROFESSIONS.items():
        assert professions, f"{role} has no role professions"
        for profession in professions:
            assert profession in PROFESSION_BAND, f"{role}: {profession} missing band"
            assert profession in PROFESSION_LABEL, f"{role}: {profession} missing label"
            if profession != Profession.CHEF:
                assert profession.value in UNIVERSITY_CAPACITY, (
                    f"{role}: {profession.value} missing university capacity"
                )


def test_farmer_fishing_professions_are_trainable_and_seeded():
    from island_traders.constants import STARTING_WORKERS_BY_PROFESSION
    from island_traders.models.profession import ROLE_PROFESSIONS

    assert Profession.MARINE_BIOLOGIST in ROLE_PROFESSIONS["Farmer"]
    assert Profession.FISH_PROCESSING_TECHNICIAN in ROLE_PROFESSIONS["Farmer"]

    farmer_seed = dict(STARTING_WORKERS_BY_PROFESSION["Farmer"])
    assert farmer_seed["Marine Biologist"] == 1
    assert farmer_seed["Fish Processing Technician"] == 2
    assert farmer_seed["Horticulturalist"] == 1
    assert farmer_seed["Veterinarian"] == 1


def test_playtest_phantom_titles_are_resolved():
    """Titles flagged in playtest either became trainable or stayed worker-tier."""
    from island_traders.models.profession import PROFESSION_LABEL, ROLE_PROFESSIONS

    manufacturer_labels = {
        PROFESSION_LABEL[profession]
        for profession in ROLE_PROFESSIONS["Manufacturer"]
    }
    assert "Factory Foreman" in manufacturer_labels
    assert "Tradesman" in manufacturer_labels
    assert "Assembly Tech" in manufacturer_labels
    assert "Factory Foreman" in BAND_TITLES["Manufacturer"][WorkerBand.TECHNICIAN]
    assert "Tradesman" in BAND_TITLES["Manufacturer"][WorkerBand.TECHNICIAN]
    assert "Assembly Tech" in BAND_TITLES["Manufacturer"][WorkerBand.TECHNICIAN]

    miner_labels = {
        PROFESSION_LABEL[profession]
        for profession in ROLE_PROFESSIONS["Miner"]
    }
    assert "Mining Foreman" in miner_labels
    assert "Refiner" in miner_labels
    assert "Mining Foreman" in BAND_TITLES["Miner"][WorkerBand.TECHNICIAN]
    assert "Refiner" in BAND_TITLES["Miner"][WorkerBand.TECHNICIAN]

    worker_tier_titles = (
        set(BAND_TITLES["Transporter"][WorkerBand.WORKER])
        | set(BAND_TITLES["Doctor"][WorkerBand.WORKER])
    )
    trainable_labels = {
        label
        for professions in ROLE_PROFESSIONS.values()
        for label in (PROFESSION_LABEL[profession] for profession in professions)
    }
    assert {"Stevedore", "Aide"} <= worker_tier_titles
    assert not ({"Stevedore", "Aide"} & trainable_labels)
