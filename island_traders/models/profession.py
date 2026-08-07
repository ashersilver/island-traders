"""
Worker professions for Island Traders.

Every worker has a profession that determines their specialisation.
Unskilled workers are the general labour pool — any island can employ them
but they operate at the lowest efficiency plateau.

Professions are trained at the University (Education Island).  Each profession
has an annual quota limiting how many can be trained per game year; Professors
additionally have a per-season cap.

Workers are also classified into one of three **bands** — see WorkerBand:
  - MANAGER:    university-trained (Education pipeline; Doctor=4 seasons,
                Nurse=1 season, others=2 seasons)
  - TECHNICIAN: vocationally trained (Instructor + optional Educator workshop;
                1 season away with the workshop, otherwise 2 seasons away and
                a 50%-productivity settling season on the home island)
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
    MARINE_BIOLOGIST     = "Marine Biologist"
    FISH_PROCESSING_TECHNICIAN = "Fish Processing Technician"
    ASSEMBLY_WORKER      = "AssemblyWorker"
    FACTORY_FOREMAN      = "FactoryForeman"
    MINER                = "Miner"
    MINING_TECHNICIAN    = "MiningTechnician"
    MINING_FOREMAN       = "MiningForeman"
    OIL_EXTRACTION       = "OilExtractionWorker"
    REFINERY_SPECIALIST  = "RefinerySpecialist"
    BANKER               = "Banker"
    ACTUARY              = "Actuary"
    INSURANCE_ADJUSTER   = "InsuranceAdjuster"  # Technician (Banker) — claims
    PROFESSOR            = "Professor"
    TECHNICAL_DIRECTOR   = "TechnicalDirector"
    MECHANIC             = "Mechanic"          # Technician band, multi-island
    # Transporter — new dedicated professions
    LOGISTICS_MANAGER    = "LogisticsManager"  # Manager (Transporter)
    FLIGHT_CREW          = "FlightCrew"        # Technician (Transporter)
    SEAMAN               = "Seaman"            # Technician (Transporter)
    WAREHOUSE_MANAGER    = "WarehouseManager"  # Technician (Transporter, ground ops)
    # Educator — technician-tier teaching staff
    LECTURER             = "Lecturer"          # Manager (Educator faculty)
    INSTRUCTOR           = "Instructor"        # Technician (Educator) — consolidated from Tutor
    # Banker — technician-tier clerical staff
    BANKING_ANALYST      = "BankingAnalyst"    # Technician (Banker)
    BANKING_CLERK        = "BankingClerk"      # Technician (Banker)
    # Manufacturer — skilled trades
    TRADESMAN            = "Tradesman"         # Technician (Manufacturer)
    # Doctor — technician-tier medical support
    MEDICAL_ORDERLY      = "MedicalOrderly"    # Technician (Doctor)
    MEDICAL_RESEARCHER   = "MedicalResearcher" # Manager (Doctor)
    MEDICAL_TECHNICIAN   = "MedicalTechnician" # Technician (Doctor)
    # Cross-island sustenance support
    CHEF                 = "Chef"              # Technician (all islands)
    LAWYER               = "Lawyer"            # Manager (all islands) — leases


class WorkerBand(str, Enum):
    """Three-tier classification of all workers, regardless of profession."""
    MANAGER    = "Manager"      # university-educated
    TECHNICIAN = "Technician"   # apprenticeship-trained
    WORKER     = "Worker"       # untrained / hired from population


class EngineerSpecialty(str, Enum):
    """Optional fourth-season/return-course specialization for Engineers."""
    INDUSTRIAL = "Industrial"
    MECHANICAL = "Mechanical"
    ELECTRICAL = "Electrical"
    CHEMICAL = "Chemical"


ENGINEER_SPECIALTY_STACK_CAP = 2


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
    Profession.MARINE_BIOLOGIST:    WorkerBand.MANAGER,
    Profession.FISH_PROCESSING_TECHNICIAN: WorkerBand.TECHNICIAN,
    Profession.ASSEMBLY_WORKER:     WorkerBand.TECHNICIAN,
    Profession.FACTORY_FOREMAN:      WorkerBand.TECHNICIAN,
    Profession.MINER:               WorkerBand.MANAGER,    # mining engineer / geologist
    Profession.MINING_TECHNICIAN:   WorkerBand.TECHNICIAN,
    Profession.MINING_FOREMAN:      WorkerBand.TECHNICIAN,
    Profession.OIL_EXTRACTION:      WorkerBand.TECHNICIAN,
    Profession.REFINERY_SPECIALIST: WorkerBand.TECHNICIAN,
    Profession.BANKER:              WorkerBand.MANAGER,
    Profession.ACTUARY:             WorkerBand.TECHNICIAN,
    Profession.INSURANCE_ADJUSTER:  WorkerBand.TECHNICIAN,
    Profession.PROFESSOR:           WorkerBand.MANAGER,
    Profession.TECHNICAL_DIRECTOR:  WorkerBand.MANAGER,
    Profession.MECHANIC:            WorkerBand.TECHNICIAN,
    # Transporter
    Profession.LOGISTICS_MANAGER:   WorkerBand.MANAGER,
    Profession.FLIGHT_CREW:         WorkerBand.TECHNICIAN,
    Profession.SEAMAN:              WorkerBand.TECHNICIAN,
    Profession.WAREHOUSE_MANAGER:   WorkerBand.TECHNICIAN,  # ground ops supervisor
    # Educator
    Profession.LECTURER:            WorkerBand.MANAGER,
    Profession.INSTRUCTOR:          WorkerBand.TECHNICIAN,
    # Banker
    Profession.BANKING_ANALYST:     WorkerBand.TECHNICIAN,
    Profession.BANKING_CLERK:       WorkerBand.TECHNICIAN,
    # Manufacturer
    Profession.TRADESMAN:           WorkerBand.TECHNICIAN,
    # Doctor
    Profession.MEDICAL_ORDERLY:     WorkerBand.TECHNICIAN,
    Profession.MEDICAL_RESEARCHER:  WorkerBand.MANAGER,
    Profession.MEDICAL_TECHNICIAN:  WorkerBand.TECHNICIAN,
    # Cross-island
    Profession.CHEF:                WorkerBand.TECHNICIAN,
    Profession.LAWYER:              WorkerBand.MANAGER,
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
        WorkerBand.MANAGER:    ["Farmer", "Marine Biologist", "Lawyer"],
        WorkerBand.TECHNICIAN: [
            "Farming Technician", "Fish Processing Technician",
            "Horticulturalist", "Veterinarian", "Mechanic", "Chef",
        ],
        WorkerBand.WORKER:     ["Farmhand"],
    },
    "Miner": {
        WorkerBand.MANAGER:    ["Mining Engineer", "Geologist", "Lawyer"],
        WorkerBand.TECHNICIAN: ["Mining Technician", "Mining Foreman", "Refiner", "Mechanic", "Chef"],
        WorkerBand.WORKER:     ["Pit Worker"],
    },
    "Transporter": {
        WorkerBand.MANAGER:    ["Logistics Manager", "Engineer", "Lawyer"],
        WorkerBand.TECHNICIAN: ["Flight Crew", "Seaman", "Warehouse Manager", "Mechanic", "Chef"],
        WorkerBand.WORKER:     ["Stevedore"],
    },
    "Educator": {
        WorkerBand.MANAGER:    ["Professor", "Lecturer", "Technical Director", "Lawyer"],
        WorkerBand.TECHNICIAN: ["Instructor", "Tutor", "Trainer", "Chef"],
        WorkerBand.WORKER:     ["Admin"],
    },
    "Banker": {
        WorkerBand.MANAGER:    ["Banker", "Lawyer"],
        WorkerBand.TECHNICIAN: ["Banking Analyst", "Actuary", "Insurance Adjuster", "Banking Clerk", "Chef"],
        WorkerBand.WORKER:     ["Receptionist"],
    },
    "Manufacturer": {
        WorkerBand.MANAGER:    ["Engineer", "Lawyer"],
        WorkerBand.TECHNICIAN: ["Factory Foreman", "Tradesman", "Assembly Tech", "Mechanic", "Chef"],
        WorkerBand.WORKER:     ["Assembler"],
    },
    "Doctor": {
        WorkerBand.MANAGER:    ["Doctor", "Nurse", "Medical Researcher", "Lawyer"],
        WorkerBand.TECHNICIAN: ["Medical Technician", "Medical Orderly", "Chef"],
        WorkerBand.WORKER:     ["Aide"],
    },
}


def primary_title(role_name: str, band: WorkerBand) -> str:
    """Primary display label for a (role, band) pair. Falls back to band name."""
    role_titles = BAND_TITLES.get(role_name, {})
    titles = role_titles.get(band, [])
    return titles[0] if titles else band.value


# Education pipeline duration in seasons (per Manager profession).
# Canonical (#18 reconciliation, ruled 2026-06-18): Doctor 4, Nurse 1,
# all other Managers 2, except Engineer now takes 3 seasons before an
# optional 4th specialty season.
EDUCATION_SEASONS: dict[Profession, int] = {
    Profession.DOCTOR:            4,
    Profession.NURSE:             1,
    Profession.ENGINEER:          3,
    Profession.FARMER:             2,
    Profession.MARINE_BIOLOGIST:   2,
    Profession.MINER:              2,
    Profession.BANKER:             2,
    Profession.MEDICAL_RESEARCHER: 2,
    Profession.PROFESSOR:          2,
    Profession.TECHNICAL_DIRECTOR: 2,
    Profession.LOGISTICS_MANAGER:  2,
    Profession.LECTURER:           2,
    Profession.LAWYER:             2,
}

# Apprenticeship pipeline: number of seasons the apprentice is *away* at
# the Education Island.  Canonical (education-model.md, ruled 2026-05-17):
# 1 season away for every Technician when the campus has a Technical Workshop.
# Without that facility, the #18 rule adds one away season and one 50%
# settling season on return; see training_duration and
# settling_seasons_on_return.
APPRENTICESHIP_SEASONS: dict[Profession, int] = {
    Profession.FARMING_TECHNICIAN:  1,
    Profession.FISH_PROCESSING_TECHNICIAN: 1,
    Profession.HORTICULTURALIST:    1,
    Profession.VETERINARIAN:        1,
    Profession.ASSEMBLY_WORKER:     1,
    Profession.FACTORY_FOREMAN:      1,
    Profession.MINING_TECHNICIAN:   1,
    Profession.MINING_FOREMAN:      1,
    Profession.OIL_EXTRACTION:      1,
    Profession.REFINERY_SPECIALIST: 1,
    Profession.MECHANIC:            1,
    # Transporter technicians
    Profession.FLIGHT_CREW:         1,
    Profession.SEAMAN:              1,
    Profession.WAREHOUSE_MANAGER:   1,
    # Educator technicians
    Profession.INSTRUCTOR:          1,
    # Banker technicians
    Profession.BANKING_ANALYST:     1,
    Profession.BANKING_CLERK:       1,
    Profession.ACTUARY:             1,
    Profession.INSURANCE_ADJUSTER:  1,
    Profession.TRADESMAN:           1,
    # Doctor technicians
    Profession.MEDICAL_ORDERLY:     1,
    Profession.MEDICAL_TECHNICIAN:  1,
    # Cross-island technicians
    Profession.CHEF:                1,
}

# How many post-return seasons a freshly-qualified apprentice without a
# Technical Workshop works at reduced productivity before reaching 100%.
APPRENTICESHIP_SETTLING_SEASONS: int = 1
# Productivity multiplier applied during each settling season.
APPRENTICESHIP_SETTLING_EFFICIENCY: float = 0.50


# Which professions are primarily associated with each island role.
# Used to filter available training options for each player.
ROLE_PROFESSIONS: dict[str, list[Profession]] = {
    "Farmer":        [
        Profession.FARMER,
        Profession.FARMING_TECHNICIAN,
        Profession.HORTICULTURALIST,
        Profession.VETERINARIAN,
        Profession.MARINE_BIOLOGIST,
        Profession.FISH_PROCESSING_TECHNICIAN,
        Profession.MECHANIC,
        Profession.CHEF, Profession.LAWYER,
    ],
    "Miner":         [
        Profession.MINER,
        Profession.MINING_TECHNICIAN,
        Profession.MINING_FOREMAN,
        Profession.OIL_EXTRACTION,
        Profession.REFINERY_SPECIALIST,
        Profession.ENGINEER,
        Profession.MECHANIC,
        Profession.CHEF, Profession.LAWYER,
    ],
    "Transporter":   [
        Profession.LOGISTICS_MANAGER, Profession.ENGINEER,
        Profession.FLIGHT_CREW, Profession.SEAMAN, Profession.WAREHOUSE_MANAGER,
        Profession.MECHANIC, Profession.CHEF, Profession.LAWYER,
    ],
    "Educator":      [
        Profession.PROFESSOR,
        Profession.LECTURER,
        Profession.TECHNICAL_DIRECTOR,
        Profession.INSTRUCTOR,
        Profession.CHEF, Profession.LAWYER,
    ],
    "Banker":        [Profession.BANKER, Profession.ACTUARY, Profession.INSURANCE_ADJUSTER,
                      Profession.BANKING_ANALYST, Profession.BANKING_CLERK, Profession.CHEF, Profession.LAWYER],
    "Manufacturer":  [
        Profession.FACTORY_FOREMAN,
        Profession.TRADESMAN,
        Profession.ASSEMBLY_WORKER,
        Profession.ENGINEER,
        Profession.MECHANIC,
        Profession.CHEF, Profession.LAWYER,
    ],
    "Doctor":        [
        Profession.DOCTOR,
        Profession.NURSE,
        Profession.MEDICAL_RESEARCHER,
        Profession.MEDICAL_TECHNICIAN,
        Profession.MEDICAL_ORDERLY,
        Profession.CHEF, Profession.LAWYER,
    ],
}

# Training that uses lab Reagents in addition to normal Expertise/Course slots.
SCIENCE_TRAINING_PROFESSIONS: set[Profession] = {
    Profession.FARMER,
    Profession.MARINE_BIOLOGIST,
    Profession.HORTICULTURALIST,
    Profession.VETERINARIAN,
    Profession.MINER,
    Profession.REFINERY_SPECIALIST,
    Profession.PROFESSOR,
    Profession.DOCTOR,
    Profession.NURSE,
    Profession.MEDICAL_RESEARCHER,
    Profession.MEDICAL_TECHNICIAN,
    Profession.ENGINEER,
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
    Profession.MARINE_BIOLOGIST:    "Marine Biologist",
    Profession.FISH_PROCESSING_TECHNICIAN: "Fish Processing Technician",
    Profession.ASSEMBLY_WORKER:     "Assembly Tech",
    Profession.FACTORY_FOREMAN:     "Factory Foreman",
    Profession.MINER:               "Miner (specialist)",
    Profession.MINING_TECHNICIAN:   "Mining Technician",
    Profession.MINING_FOREMAN:      "Mining Foreman",
    Profession.OIL_EXTRACTION:      "Oil Extraction Worker",
    Profession.REFINERY_SPECIALIST: "Refiner",
    Profession.BANKER:              "Banker (specialist)",
    Profession.ACTUARY:             "Actuary",
    Profession.INSURANCE_ADJUSTER:  "Insurance Adjuster",
    Profession.PROFESSOR:           "Professor",
    Profession.TECHNICAL_DIRECTOR:  "Technical Director",
    Profession.MECHANIC:            "Mechanic",
    # Transporter
    Profession.LOGISTICS_MANAGER:   "Logistics Manager",
    Profession.FLIGHT_CREW:         "Flight Crew",
    Profession.SEAMAN:              "Seaman",
    Profession.WAREHOUSE_MANAGER:   "Warehouse Manager",
    # Educator
    Profession.LECTURER:            "Lecturer",
    Profession.INSTRUCTOR:          "Instructor",
    # Banker
    Profession.BANKING_ANALYST:     "Banking Analyst",
    Profession.BANKING_CLERK:       "Banking Clerk",
    # Manufacturer
    Profession.TRADESMAN:           "Tradesman",
    # Doctor
    Profession.MEDICAL_ORDERLY:     "Medical Orderly",
    Profession.MEDICAL_RESEARCHER:  "Medical Researcher",
    Profession.MEDICAL_TECHNICIAN:  "Medical Technician",
    # Cross-island
    Profession.CHEF:                "Chef",
    Profession.LAWYER:              "Lawyer",
}
