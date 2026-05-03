"""
Worker professions for Island Traders.

Every worker has a profession that determines their specialisation.
Unskilled workers are the general labour pool — any island can employ them
but they operate at the lowest efficiency plateau.

Professions are trained at the University (Education Island).  Each profession
has an annual quota limiting how many can be trained per game year; Professors
additionally have a per-season cap.
"""
from __future__ import annotations
from enum import Enum


class Profession(str, Enum):
    UNSKILLED            = "Unskilled"
    DOCTOR               = "Doctor"
    NURSE                = "Nurse"
    ENGINEER             = "Engineer"
    FARMER               = "Farmer"
    VETERINARIAN         = "Veterinarian"
    ASSEMBLY_WORKER      = "AssemblyWorker"
    MINER                = "Miner"
    OIL_EXTRACTION       = "OilExtractionWorker"
    REFINERY_SPECIALIST  = "RefinerySpecialist"
    BANKER               = "Banker"
    PROFESSOR            = "Professor"


# Which professions are primarily associated with each island role.
# Used to filter available training options for each player.
ROLE_PROFESSIONS: dict[str, list[Profession]] = {
    "Farmer":        [Profession.FARMER, Profession.VETERINARIAN],
    "Miner":         [Profession.MINER, Profession.OIL_EXTRACTION, Profession.REFINERY_SPECIALIST, Profession.ENGINEER],
    "Transporter":   [Profession.ENGINEER],
    "Educator":      [Profession.PROFESSOR],
    "Banker":        [Profession.BANKER],
    "Manufacturer":  [Profession.ASSEMBLY_WORKER, Profession.ENGINEER],
    "Doctor":        [Profession.DOCTOR, Profession.NURSE],
}

# Human-readable label for display
PROFESSION_LABEL: dict[Profession, str] = {
    Profession.UNSKILLED:           "Unskilled (general labour)",
    Profession.DOCTOR:              "Doctor",
    Profession.NURSE:               "Nurse",
    Profession.ENGINEER:            "Engineer",
    Profession.FARMER:              "Farmer (specialist)",
    Profession.VETERINARIAN:        "Veterinarian",
    Profession.ASSEMBLY_WORKER:     "Assembly Worker",
    Profession.MINER:               "Miner (specialist)",
    Profession.OIL_EXTRACTION:      "Oil Extraction Worker",
    Profession.REFINERY_SPECIALIST: "Refinery Specialist",
    Profession.BANKER:              "Banker (specialist)",
    Profession.PROFESSOR:           "Professor",
}
