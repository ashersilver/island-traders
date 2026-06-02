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
    HEALTH_SERVICES      = "HealthServices"
    VACCINE              = "Vaccine"
    FINANCE              = "Finance"
    FARM_MACHINERY       = "FarmMachinery"
    MINING_EQUIPMENT     = "MiningEquipment"
    MEDICAL_DEVICES      = "MedicalDevices"
    TRANSPORT_EQUIPMENT  = "TransportEquipment"
    PASSENGER_SEATS      = "PassengerSeats"
    PATENTS              = "Patents"


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
