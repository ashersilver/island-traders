from __future__ import annotations
from dataclasses import dataclass
from .resource import ResourceType


@dataclass(frozen=True)
class Role:
    name: str
    display_name: str
    short_name: str
    island: str
    produces: tuple[ResourceType, ...]
    needs: tuple[ResourceType, ...]
    description: str


ROLES: dict[str, Role] = {
    "Farmer": Role(
        name="Farmer",
        display_name="Agriculture and Fisheries",
        short_name="Agriculture",
        island="Agriculture and Fisheries Island",
        produces=(ResourceType.FOOD, ResourceType.FISH),
        needs=(ResourceType.FARM_MACHINERY, ResourceType.OIL),
        description="Feeds the archipelago — output varies by season (see FARMER_SEASONAL_CONVERSION).",
    ),
    "Miner": Role(
        name="Miner",
        display_name="Mining and Exploration",
        short_name="Mining",
        island="Mining and Exploration Island",
        produces=(ResourceType.ORE, ResourceType.METAL, ResourceType.OIL),
        needs=(ResourceType.OIL, ResourceType.FREIGHT, ResourceType.MINING_EQUIPMENT),
        description="Extracts raw materials and energy resources from the earth.",
    ),
    "Transporter": Role(
        name="Transporter",
        display_name="Transportation and Logistics",
        short_name="Transportation",
        island="Transportation and Logistics Island",
        produces=(ResourceType.FREIGHT,),
        needs=(ResourceType.OIL, ResourceType.TRANSPORT_EQUIPMENT),
        description="Moves goods between islands — the backbone of trade.",
    ),
    "Educator": Role(
        name="Educator",
        display_name="Education, Research and Training",
        short_name="Education",
        island="Education, Research and Training Island",
        produces=(ResourceType.KNOWLEDGE, ResourceType.PATENTS),
        needs=(ResourceType.LABORATORY_EQUIPMENT,),
        description="Trains the workforce and advances knowledge across the archipelago.",
    ),
    "Banker": Role(
        name="Banker",
        display_name="Banking and Insurance",
        short_name="Banking",
        island="Banking and Insurance Island",
        # Banker income is service-based, not commodity-based: loan interest
        # spread + insurance premiums (and, on the roadmap, deal guarantees,
        # brokerage, project finance).  The Finance commodity has been
        # removed from the production loop.
        produces=(),
        needs=(ResourceType.KNOWLEDGE,),
        description="Lends capital, underwrites insurance, and brokers deals — earning the spread.",
    ),
    "Manufacturer": Role(
        name="Manufacturer",
        display_name="Manufacturing",
        short_name="Manufacturing",
        island="ForgeHaven Manufacturing Island",
        produces=(
            ResourceType.FARM_MACHINERY,
            ResourceType.MINING_EQUIPMENT,
            ResourceType.LABORATORY_EQUIPMENT,
            ResourceType.MEDICAL_DEVICES,
            ResourceType.TRANSPORT_EQUIPMENT,
        ),
        needs=(ResourceType.METAL, ResourceType.OIL),
        description=(
            "ForgeHaven runs four product lines — Farm Machinery, Mining Equipment, "
            "Laboratory Equipment, Medical Devices, or Transportation Equipment. Choose one per season."
        ),
    ),
    "Doctor": Role(
        name="Doctor",
        display_name="Healthcare and Health Research",
        short_name="Healthcare",
        island="Healthcare and Health Research Island",
        produces=(ResourceType.HEALTH_SERVICES, ResourceType.VACCINE),
        needs=(ResourceType.KNOWLEDGE, ResourceType.LABORATORY_EQUIPMENT),
        description="Provides health services and vaccines, keeping the workforce productive.",
    ),
}


ROLE_DISPLAY_NAMES: dict[str, str] = {
    key: role.display_name for key, role in ROLES.items()
}

ROLE_SHORT_NAMES: dict[str, str] = {
    key: role.short_name for key, role in ROLES.items()
}
