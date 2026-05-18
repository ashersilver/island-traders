"""
Worker professions for Island Traders.

Every worker has a profession that determines their specialisation.
Unskilled workers are the general labour pool — any island can employ them
but they operate at the lowest efficiency plateau.

Professions are trained at the University (Education Island).  Each profession
has an annual quota limiting how many can be trained per game year; Professors
additionally have a per-season cap.

Workers are also classified into one of three **bands** — see WorkerBand:
  - MANAGER:    university-trained (Education pipeline; Doctor=2 seasons,
                Nurse=1 season, others=2 seasons)
  - TECHNICIAN: apprenticeship-trained (separate Educator slot pool; worker
                stays on home island during the apprenticeship)
  - WORKER:     hired directly from the island population (no formal training)
"""
from __future__ import annotations
from enum import Enum


class Profession(str, Enum):
    UNSKILLED            = "Unskilled"
    DOCTOR               = "Doctor"
    NURSE                = "Nurse"
    ENGINEER             = "Engineer"
    FARMER               = "Farmer"
    FARMING_TECHNICIAN   = "FarmingTechnician"
    HORTICULTURALIST     = "Horticulturalist"
    VETERINARIAN         = "Veterinarian"
    ASSEMBLY_WORKER      = "AssemblyWorker"
    MINER                = "Miner"
    MINING_TECHNICIAN    = "MiningTechnician"
    OIL_EXTRACTION       = "OilExtractionWorker"
    REFINERY_SPECIALIST  = "RefinerySpecialist"
    BANKER               = "Banker"
    PROFESSOR            = "Professor"
    MECHANIC             = "Mechanic"          # Technician band, multi-island
    # Transporter — new dedicated professions
    LOGISTICS_MANAGER    = "LogisticsManager"  # Manager (Transporter)
    FLIGHT_CREW          = "FlightCrew"        # Technician (Transporter)
    SEAMAN               = "Seaman"            # Technician (Transporter)
    WAREHOUSE_MANAGER    = "WarehouseManager"  # Technician (Transporter, ground ops)
    # Educator — technician-tier teaching staff
    LECTURER             = "Lecturer"          # Manager (Educator faculty)
    TUTOR                = "Tutor"             # Technician (Educator)
    # Banker — technician-tier clerical staff
    BANKING_ANALYST      = "BankingAnalyst"    # Technician (Banker)
    BANKING_CLERK        = "BankingClerk"      # Technician (Banker)
    # Doctor — technician-tier medical support
    MEDICAL_ORDERLY      = "MedicalOrderly"    # Technician (Doctor)


class WorkerBand(str, Enum):
    """Three-tier classification of all workers, regardless of profession."""
    MANAGER    = "Manager"      # university-educated
    TECHNICIAN = "Technician"   # apprenticeship-trained
    WORKER     = "Worker"       # untrained / hired from population


# Each profession's band classification.
# Update here if a profession is added or its tier changes.
PROFESSION_BAND: dict[Profession, WorkerBand] = {
    Profession.UNSKILLED:           WorkerBand.WORKER,
    Profession.DOCTOR:              WorkerBand.MANAGER,
    Profession.NURSE:               WorkerBand.MANAGER,    # 1-season Education
    Profession.ENGINEER:            WorkerBand.MANAGER,
    Profession.FARMER:              WorkerBand.MANAGER,
    Profession.FARMING_TECHNICIAN:  WorkerBand.TECHNICIAN,
    Profession.HORTICULTURALIST:    WorkerBand.TECHNICIAN,
    Profession.VETERINARIAN:        WorkerBand.TECHNICIAN,
    Profession.ASSEMBLY_WORKER:     WorkerBand.TECHNICIAN,
    Profession.MINER:               WorkerBand.MANAGER,    # mining engineer / geologist
    Profession.MINING_TECHNICIAN:   WorkerBand.TECHNICIAN,
    Profession.OIL_EXTRACTION:      WorkerBand.TECHNICIAN,
    Profession.REFINERY_SPECIALIST: WorkerBand.TECHNICIAN,
    Profession.BANKER:              WorkerBand.MANAGER,
    Profession.PROFESSOR:           WorkerBand.MANAGER,
    Profession.MECHANIC:            WorkerBand.TECHNICIAN,
    # Transporter
    Profession.LOGISTICS_MANAGER:   WorkerBand.MANAGER,
    Profession.FLIGHT_CREW:         WorkerBand.TECHNICIAN,
    Profession.SEAMAN:              WorkerBand.TECHNICIAN,
    Profession.WAREHOUSE_MANAGER:   WorkerBand.TECHNICIAN,  # ground ops supervisor
    # Educator
    Profession.LECTURER:            WorkerBand.MANAGER,
    Profession.TUTOR:               WorkerBand.TECHNICIAN,
    # Banker
    Profession.BANKING_ANALYST:     WorkerBand.TECHNICIAN,
    Profession.BANKING_CLERK:       WorkerBand.TECHNICIAN,
    # Doctor
    Profession.MEDICAL_ORDERLY:     WorkerBand.TECHNICIAN,
}


def band_of(profession: Profession | str) -> WorkerBand:
    """Return the WorkerBand for a profession (accepts the enum or its str value)."""
    if isinstance(profession, str):
        try:
            profession = Profession(profession)
        except ValueError:
            return WorkerBand.WORKER
    return PROFESSION_BAND.get(profession, WorkerBand.WORKER)


# Per-island display titles for each band.
# Each entry is keyed by role name -> {band: list of titles shown to the player}.
# The first title in each list is the "primary" label used when summarising counts.
BAND_TITLES: dict[str, dict[WorkerBand, list[str]]] = {
    "Farmer": {
        WorkerBand.MANAGER:    ["Farmer"],
        WorkerBand.TECHNICIAN: ["Farming Technician", "Horticulturalist", "Veterinarian", "Mechanic"],
        WorkerBand.WORKER:     ["Farmhand"],
    },
    "Miner": {
        WorkerBand.MANAGER:    ["Mining Engineer", "Geologist"],
        WorkerBand.TECHNICIAN: ["Mining Technician", "Mining Foreman", "Refiner", "Mechanic"],
        WorkerBand.WORKER:     ["Pit Worker"],
    },
    "Transporter": {
        WorkerBand.MANAGER:    ["Logistics Manager", "Engineer"],
        WorkerBand.TECHNICIAN: ["Flight Crew", "Seaman", "Warehouse Manager", "Mechanic"],
        WorkerBand.WORKER:     ["Stevedore"],
    },
    "Educator": {
        WorkerBand.MANAGER:    ["Professor", "Lecturer"],
        WorkerBand.TECHNICIAN: ["Tutor", "Trainer"],
        WorkerBand.WORKER:     ["Admin"],
    },
    "Banker": {
        WorkerBand.MANAGER:    ["Banker"],
        WorkerBand.TECHNICIAN: ["Banking Analyst", "Banking Clerk"],
        WorkerBand.WORKER:     ["Receptionist"],
    },
    "Manufacturer": {
        WorkerBand.MANAGER:    ["Engineer"],
        WorkerBand.TECHNICIAN: ["Factory Foreman", "Assembly Tech", "Mechanic"],
        WorkerBand.WORKER:     ["Assembler"],
    },
    "Doctor": {
        WorkerBand.MANAGER:    ["Doctor", "Nurse"],
        WorkerBand.TECHNICIAN: ["Medical Orderly"],
        WorkerBand.WORKER:     ["Aide"],
    },
}


def primary_title(role_name: str, band: WorkerBand) -> str:
    """Primary display label for a (role, band) pair. Falls back to band name."""
    role_titles = BAND_TITLES.get(role_name, {})
    titles = role_titles.get(band, [])
    return titles[0] if titles else band.value


# Education pipeline duration in seasons (per Manager profession).
# Per requirements: Doctor 2, Nurse 1, others 2 by default.
EDUCATION_SEASONS: dict[Profession, int] = {
    Profession.DOCTOR:            2,
    Profession.NURSE:             1,
    Profession.ENGINEER:          2,
    Profession.FARMER:             2,
    Profession.MINER:              2,
    Profession.BANKER:             2,
    Profession.PROFESSOR:          2,
    Profession.LOGISTICS_MANAGER:  2,
    Profession.LECTURER:           2,
}

# Apprenticeship pipeline duration in seasons (per Technician profession).
# Default: 2 seasons for all (worker stays on home island during training).
APPRENTICESHIP_SEASONS: dict[Profession, int] = {
    Profession.FARMING_TECHNICIAN:  2,
    Profession.HORTICULTURALIST:    2,
    Profession.VETERINARIAN:        2,
    Profession.ASSEMBLY_WORKER:     2,
    Profession.MINING_TECHNICIAN:   2,
    Profession.OIL_EXTRACTION:      2,
    Profession.REFINERY_SPECIALIST: 2,
    Profession.MECHANIC:            2,
    # Transporter technicians
    Profession.FLIGHT_CREW:         2,
    Profession.SEAMAN:              2,
    Profession.WAREHOUSE_MANAGER:   2,
    # Educator technicians
    Profession.TUTOR:               2,
    # Banker technicians
    Profession.BANKING_ANALYST:     2,
    Profession.BANKING_CLERK:       2,
    # Doctor technicians
    Profession.MEDICAL_ORDERLY:     2,
}


# Which professions are primarily associated with each island role.
# Used to filter available training options for each player.
ROLE_PROFESSIONS: dict[str, list[Profession]] = {
    "Farmer":        [Profession.FARMER, Profession.FARMING_TECHNICIAN, Profession.HORTICULTURALIST, Profession.VETERINARIAN, Profession.MECHANIC],
    "Miner":         [Profession.MINER, Profession.MINING_TECHNICIAN, Profession.OIL_EXTRACTION, Profession.REFINERY_SPECIALIST, Profession.ENGINEER, Profession.MECHANIC],
    "Transporter":   [
        Profession.LOGISTICS_MANAGER, Profession.ENGINEER,
        Profession.FLIGHT_CREW, Profession.SEAMAN, Profession.WAREHOUSE_MANAGER,
        Profession.MECHANIC,
    ],
    "Educator":      [Profession.PROFESSOR, Profession.LECTURER, Profession.TUTOR],
    "Banker":        [Profession.BANKER, Profession.BANKING_ANALYST, Profession.BANKING_CLERK],
    "Manufacturer":  [Profession.ASSEMBLY_WORKER, Profession.ENGINEER, Profession.MECHANIC],
    "Doctor":        [Profession.DOCTOR, Profession.NURSE, Profession.MEDICAL_ORDERLY],
}

# Human-readable label for display
PROFESSION_LABEL: dict[Profession, str] = {
    Profession.UNSKILLED:           "Unskilled (general labour)",
    Profession.DOCTOR:              "Doctor",
    Profession.NURSE:               "Nurse",
    Profession.ENGINEER:            "Engineer",
    Profession.FARMER:              "Farmer (specialist)",
    Profession.FARMING_TECHNICIAN:  "Farming Technician",
    Profession.HORTICULTURALIST:    "Horticulturalist",
    Profession.VETERINARIAN:        "Veterinarian",
    Profession.ASSEMBLY_WORKER:     "Assembly Worker",
    Profession.MINER:               "Miner (specialist)",
    Profession.MINING_TECHNICIAN:   "Mining Technician",
    Profession.OIL_EXTRACTION:      "Oil Extraction Worker",
    Profession.REFINERY_SPECIALIST: "Refinery Specialist",
    Profession.BANKER:              "Banker (specialist)",
    Profession.PROFESSOR:           "Professor",
    Profession.MECHANIC:            "Mechanic",
    # Transporter
    Profession.LOGISTICS_MANAGER:   "Logistics Manager",
    Profession.FLIGHT_CREW:         "Flight Crew",
    Profession.SEAMAN:              "Seaman",
    Profession.WAREHOUSE_MANAGER:   "Warehouse Manager",
    # Educator
    Profession.LECTURER:            "Lecturer",
    Profession.TUTOR:               "Tutor",
    # Banker
    Profession.BANKING_ANALYST:     "Banking Analyst",
    Profession.BANKING_CLERK:       "Banking Clerk",
    # Doctor
    Profession.MEDICAL_ORDERLY:     "Medical Orderly",
}
