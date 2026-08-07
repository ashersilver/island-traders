"""Derive the island dependency graph from real game data.

The map used to be a hand-maintained edge list in the frontend, which drifted
from the rules: it missed Freight entirely (every island burns Freight on every
trade and on repairs), and the role table it echoed still credited the
Manufacturer with Reagents long after the Doctor took that line over.

Everything here is computed from the same constants the engine runs on, so the
map cannot silently go stale:

* **consumable** edges come from ``PRODUCTION_RECIPES`` inputs plus the
  cross-role needs that never appear in a recipe (energy Oil, continuing-
  education Expertise, sustenance, Spares for repairs, Freight on trade,
  PassengerSeats for training travel, the Banker's office Goods, and the
  household consumer basket).
* **capital** edges come from ``CAPITAL_CATALOGUE`` via the manufactured
  resource each role's equipment is built from.

A dependency is ``universal`` when every island has it regardless of what it
chooses to produce — those are the ones players are most often surprised by.
"""
from __future__ import annotations

from .constants import BANKER_OFFICE_GOODS_PER_SEASON
from .constants_capacity import CAPITAL_CATALOGUE, PRODUCTION_RECIPES
from .models.role import ROLES

# Role that manufactures each role's capital equipment inputs.  Mirrors
# TurnManager._manufactured_resource_for_capital_item.
CAPITAL_INPUT_BY_ROLE: dict[str, str] = {
    "Farmer": "FarmMachinery",
    "Miner": "MiningEquipment",
    "Transporter": "TransportEquipment",
    "Educator": "Reagents",
    "Banker": "Reagents",
    "Manufacturer": "TransportEquipment",
    "Doctor": "MedicalDevices",
}

# Cross-role needs that no recipe scan would surface.  (resource, reason)
UNIVERSAL_CONSUMABLE_NEEDS: list[tuple[str, str]] = [
    ("Oil", "Energy floor — every island burns Oil each season to keep "
            "buildings running; a shortfall causes a brownout."),
    ("Expertise", "Continuing education — one Expertise per active Manager "
                  "per year, or managers lose efficiency."),
    ("Food", "Sustenance — residents eat every season (Food, or "
             "Grain + Produce + Fish/Meat)."),
    ("Freight", "Logistics — trades burn Freight, and equipment repairs need "
                "1–2 units on top of any recipe requirement."),
    ("Spares", "Repairs — a failed capital unit cannot return to service "
               "without Spares."),
    ("Goods", "Household demand — residents buy Goods each season."),
    ("Courses", "Household demand — residents buy Courses each season."),
    ("MedicalSupplies", "Health — nurse upkeep, injury treatment and the "
                        "quality-of-life stockpile."),
    ("PassengerSeats", "Travel — sending trainees to another island, and "
                       "medevac for injured workers."),
]


def _producers() -> dict[str, list[str]]:
    """resource -> roles that can produce it, from the live recipe table."""
    out: dict[str, list[str]] = {}
    for recipe in PRODUCTION_RECIPES:
        out.setdefault(recipe.output, [])
        if recipe.role not in out[recipe.output]:
            out[recipe.output].append(recipe.role)
    return out


def build_dependency_graph() -> dict:
    """Return the full static dependency model for the map."""
    producers = _producers()
    roles = [r for r in ROLES]
    needs: list[dict] = []

    def add(role: str, resource: str, layer: str, reason: str,
            universal: bool = False) -> None:
        # One edge per (role, resource, layer); merge reasons so a resource
        # needed by several of a role's lines still reads as one dependency.
        # `recipe` and `universal` are tracked independently: Oil is both a
        # Farmer recipe input AND a universal energy need, and the overview
        # would wrongly hide that production flow if one flag masked the other.
        for existing in needs:
            if (existing["role"] == role and existing["resource"] == resource
                    and existing["layer"] == layer):
                if reason not in existing["reasons"]:
                    existing["reasons"].append(reason)
                existing["universal"] = existing["universal"] or universal
                existing["recipe"] = existing["recipe"] or not universal
                return
        needs.append({
            "role": role,
            "resource": resource,
            "layer": layer,
            "reasons": [reason],
            "universal": universal,
            "recipe": not universal,
            "from_roles": producers.get(resource, []),
        })

    # --- consumable layer: recipe inputs -----------------------------------
    for recipe in PRODUCTION_RECIPES:
        for resource in recipe.inputs:
            add(recipe.role, resource, "consumable",
                f"Input for {recipe.output}")

    # --- consumable layer: needs no recipe mentions -------------------------
    for role in roles:
        for resource, reason in UNIVERSAL_CONSUMABLE_NEEDS:
            if role == "Banker" and resource == "Goods":
                reason = (f"Office supplies — the Banker consumes "
                          f"{BANKER_OFFICE_GOODS_PER_SEASON} Goods per season "
                          f"while running a loan or policy book.")
            add(role, resource, "consumable", reason, universal=True)

    # --- capital layer -----------------------------------------------------
    for item in CAPITAL_CATALOGUE:
        role = getattr(item, "role", None)
        if role is None:
            continue
        if getattr(item, "effects", None) and item.effects.get("cash_only"):
            # Bought with cash rather than built from a manufactured resource.
            continue
        resource = CAPITAL_INPUT_BY_ROLE.get(role)
        if not resource:
            continue
        add(role, resource, "capital",
            f"Builds {item.name} ({int(getattr(item, 'capacity_units', 1) or 1)}"
            f" unit{'s' if (getattr(item, 'capacity_units', 1) or 1) != 1 else ''})")

    return {
        "producers": producers,
        "needs": needs,
        "roles": list(roles),
        "layers": ["consumable", "capital"],
    }
