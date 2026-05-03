from __future__ import annotations
from dataclasses import dataclass
from .resource import ResourceType


@dataclass(frozen=True)
class Role:
    name: str
    island: str
    produces: tuple[ResourceType, ...]
    needs: tuple[ResourceType, ...]
    description: str


ROLES: dict[str, Role] = {
    "Farmer": Role(
        name="Farmer",
        island="Agriculture, Fisheries & Foods Island",
        produces=(ResourceType.FOOD, ResourceType.FISH),
        needs=(ResourceType.CAPITAL_EQUIPMENT, ResourceType.OIL),
        description="Feeds the archipelago — output varies by season (see FARMER_SEASONAL_CONVERSION).",
    ),
    "Miner": Role(
        name="Miner",
        island="Mining & Oil Island",
        produces=(ResourceType.ORE, ResourceType.OIL),
        needs=(ResourceType.OIL, ResourceType.FREIGHT),
        description="Extracts raw materials and energy resources from the earth.",
    ),
    "Transporter": Role(
        name="Transporter",
        island="Transportation & Shipping Island",
        produces=(ResourceType.FREIGHT,),
        needs=(ResourceType.OIL, ResourceType.CAPITAL_EQUIPMENT),
        description="Moves goods between islands — the backbone of trade.",
    ),
    "Educator": Role(
        name="Educator",
        island="Education & Training Island",
        produces=(ResourceType.KNOWLEDGE,),
        needs=(ResourceType.CAPITAL_EQUIPMENT, ResourceType.FINANCE),
        description="Trains the workforce and advances knowledge across the archipelago.",
    ),
    "Banker": Role(
        name="Banker",
        island="Banking Island",
        produces=(ResourceType.FINANCE,),
        needs=(ResourceType.KNOWLEDGE, ResourceType.CAPITAL_EQUIPMENT),
        description="Issues credit and financial services — capital flows where it is invited.",
    ),
    "Manufacturer": Role(
        name="Manufacturer",
        island="Manufacturing Island",
        produces=(ResourceType.GOODS, ResourceType.CAPITAL_EQUIPMENT),
        needs=(ResourceType.ORE, ResourceType.OIL, ResourceType.FREIGHT),
        description="Transforms raw materials into finished goods and capital equipment.",
    ),
    "Doctor": Role(
        name="Doctor",
        island="Healthcare Island",
        produces=(ResourceType.HEALTH_SERVICES, ResourceType.VACCINE),
        needs=(ResourceType.KNOWLEDGE, ResourceType.CAPITAL_EQUIPMENT),
        description="Provides health services and vaccines, keeping the workforce productive.",
    ),
}
