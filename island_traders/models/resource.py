from __future__ import annotations
from enum import Enum
from dataclasses import dataclass, field


class ResourceType(str, Enum):
    FOOD              = "Food"
    FISH              = "Fish"
    GRAIN             = "Grain"
    PRODUCE           = "Produce"
    MEAT              = "Meat"
    ORE               = "Ore"
    METAL             = "Metal"
    OIL               = "Oil"
    FREIGHT           = "Freight"
    EXPERTISE         = "Expertise"
    COURSES           = "Courses"
    REAGENTS = "Reagents"
    GOODS             = "Goods"
    MEDICAL_SUPPLIES     = "MedicalSupplies"
    # Backward-compatible alias for older saves/API clients that still say
    # HealthServices. The canonical resource value is MedicalSupplies.
    HEALTH_SERVICES      = "MedicalSupplies"
    VACCINE              = "Vaccine"
    # Medical & Laboratory Island's assay line (#26).  One resource covers every
    # assay the archipelago buys — metal assays for the Miner, soil analyses for
    # the Farmer, and later environmental assessments (#25) and health
    # certificates (#19).  The "type" is narrative context, not an engine
    # distinction; each consumer pays for 1 Lab Test.
    LABORATORY_TESTS     = "LaboratoryTests"
    FINANCE              = "Finance"
    FARM_MACHINERY       = "FarmMachinery"
    MINING_EQUIPMENT     = "MiningEquipment"
    MEDICAL_DEVICES      = "MedicalDevices"
    TRANSPORT_EQUIPMENT  = "TransportEquipment"
    PASSENGER_SEATS      = "PassengerSeats"
    PATENTS              = "Patents"
    SPARES               = "Spares"

    @classmethod
    def _missing_(cls, value):
        if value == "HealthServices":
            return cls.MEDICAL_SUPPLIES
        return None


# Generic spares (#185/#188): manufactured by the Manufacturer and consumed
# during repair. Spares are tradable so islands can stock repair kits before
# equipment fails.
NON_TRADABLE_RESOURCES: frozenset[ResourceType] = frozenset()


class InsufficientResourceError(Exception):
    pass


@dataclass
class ResourceBundle:
    amounts: dict[ResourceType, int] = field(default_factory=dict)

    def get(self, rtype: ResourceType) -> int:
        return self.amounts.get(rtype, 0)

    def add(self, rtype: ResourceType, qty: int) -> ResourceBundle:
        new = dict(self.amounts)
        new[rtype] = new.get(rtype, 0) + qty
        return ResourceBundle(new)

    def subtract(self, rtype: ResourceType, qty: int) -> ResourceBundle:
        current = self.amounts.get(rtype, 0)
        if current < qty:
            raise InsufficientResourceError(
                f"Cannot subtract {qty} {rtype.value}: only {current} available"
            )
        new = dict(self.amounts)
        new[rtype] = current - qty
        return ResourceBundle(new)

    def can_satisfy(self, requirements: dict[ResourceType, int]) -> bool:
        return all(self.get(r) >= qty for r, qty in requirements.items())

    def total_value(self, prices: dict[ResourceType, float]) -> float:
        return sum(qty * prices.get(r, 0.0) for r, qty in self.amounts.items())

    def __add__(self, other: ResourceBundle) -> ResourceBundle:
        result = dict(self.amounts)
        for r, qty in other.amounts.items():
            result[r] = result.get(r, 0) + qty
        return ResourceBundle(result)

    def __sub__(self, other: ResourceBundle) -> ResourceBundle:
        bundle = self
        for r, qty in other.amounts.items():
            bundle = bundle.subtract(r, qty)
        return bundle

    def __repr__(self) -> str:
        parts = [f"{r.value}:{qty}" for r, qty in self.amounts.items() if qty > 0]
        return f"ResourceBundle({', '.join(parts) if parts else 'empty'})"
