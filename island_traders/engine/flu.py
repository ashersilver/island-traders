from __future__ import annotations

from math import ceil

from ..constants import VACCINE_PEOPLE_PER_DOSE


def vaccine_doses_needed(population: int) -> int:
    return max(0, ceil(max(0, population) / VACCINE_PEOPLE_PER_DOSE))
