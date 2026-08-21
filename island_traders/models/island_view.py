"""Per-island views of a multi-role player.

The engine models a player who holds several roles as a **single** island: one
treasury, one inventory, one workforce roster.  That is fine for the rules, but
it makes the dashboard's per-island tabs lie — selecting "Mining" while you also
own "Banking" still showed the combined cash, stock and headcount.

This module derives a *view* of each island a player owns, so the dashboard can
render one tab as if that island were the only one the player held.  Nothing
here mutates the player; it is a pure attribution layer.

Attribution policy (deterministic, and exactly reproduces the consolidated
figures when summed):

* **Capital equipment** — exact.  Every ``CapitalItem`` carries a ``role``, so
  each owned unit's depreciated book value lands on its own island.  Catalogue
  items with ``role == "Any"`` genuinely serve every island the player holds;
  their value is split by island weight (below) and they are listed on every
  island tab.
* **Personnel** — by profession.  ``ROLE_PROFESSIONS`` says which professions
  belong to which island.  A profession claimed by exactly one of the player's
  roles goes wholly to that island.  A profession claimed by several of them
  (Engineer, Mechanic, Chef) or by none (Unskilled) is split by island weight.
* **Inventory** — by trade flow.  A resource an island produces or consumes is
  claimed by that island; when several of the player's islands claim it, the
  stock is split between the claimants by weight.  A resource no island claims
  is split across all of them by weight.
* **Treasury / cash** — pooled in the engine, so it is split by island weight.

**Island weight** is the island's share of the player's *unambiguously* held
workers (those whose profession only one of the player's islands claims).  When
that is not decidable — a brand-new island with only Unskilled labour, say — the
weights fall back to each island's ``LABOUR_REQUIREMENTS`` headcount, and
finally to an even split.  Weights never depend on the quantities they
allocate, so the attribution is not circular.

Integer quantities (workers, inventory units) are split by the largest-remainder
method, so every unit is allocated exactly once and the per-island figures sum
back to the consolidated total.
"""
from __future__ import annotations

from .profession import PROFESSION_BAND, PROFESSION_LABEL, Profession, ROLE_PROFESSIONS
from ..constants import (
    BASE_PRODUCTION,
    FARMER_SEASONAL_CONVERSION,
    LABOUR_REQUIREMENTS,
    MANUFACTURER_PRODUCT_LINES,
    OUTPUT_PRODUCTION_INPUTS,
    OUTPUT_PRODUCTION_INPUT_STEPS,
    PRODUCTION_INPUTS,
)

# Catalogue role marker for equipment that serves whichever island needs it.
SHARED_CAPITAL_ROLE = "Any"


# ---------------------------------------------------------------------------
# Static role → {professions, resources} maps
# ---------------------------------------------------------------------------

def role_professions(role_name: str) -> set[str]:
    """Profession *values* associated with ``role_name``'s island."""
    return {p.value for p in ROLE_PROFESSIONS.get(role_name, [])}


def role_resources(role_name: str) -> set[str]:
    """Resource *values* an island produces or consumes.

    Covers the base production table, the Farmer's seasonal conversion table,
    the Manufacturer's product lines, and every flavour of production input
    (per-role, per-output, and stepped lab consumables).
    """
    resources: set[str] = set()
    resources.update(BASE_PRODUCTION.get(role_name, {}))
    resources.update(PRODUCTION_INPUTS.get(role_name, {}))
    for output_inputs in OUTPUT_PRODUCTION_INPUTS.get(role_name, {}).values():
        resources.update(output_inputs)
    for step in OUTPUT_PRODUCTION_INPUT_STEPS.get(role_name, {}).values():
        resources.update(step.get("inputs", {}))
    if role_name == "Farmer":
        for season in FARMER_SEASONAL_CONVERSION.values():
            resources.update(season.get("inputs", {}))
            resources.update(season.get("outputs", {}))
    if role_name == "Manufacturer":
        for line in MANUFACTURER_PRODUCT_LINES.values():
            resources.update(line.get("inputs", {}))
            output = line.get("output")
            if output is not None:
                resources.add(getattr(output, "value", output))
    return {getattr(r, "value", r) for r in resources}


# ---------------------------------------------------------------------------
# Allocation helpers
# ---------------------------------------------------------------------------

def _normalise(weights: dict[str, float]) -> dict[str, float]:
    total = sum(weights.values())
    if total <= 0:
        n = len(weights) or 1
        return {k: 1.0 / n for k in weights}
    return {k: v / total for k, v in weights.items()}


def split_int(total: int, weights: dict[str, float]) -> dict[str, int]:
    """Split ``total`` whole units across ``weights`` by largest remainder.

    The parts always sum back to ``total``; ties break on the weight order,
    which is the player's role order, so the result is stable across renders.
    """
    keys = list(weights)
    if not keys:
        return {}
    if total <= 0:
        return {k: 0 for k in keys}
    shares = _normalise(weights)
    exact = {k: total * shares[k] for k in keys}
    parts = {k: int(exact[k]) for k in keys}
    remainder = total - sum(parts.values())
    for key in sorted(keys, key=lambda k: (-(exact[k] - parts[k]), keys.index(k))):
        if remainder <= 0:
            break
        parts[key] += 1
        remainder -= 1
    return parts


def split_float(total: float, weights: dict[str, float], places: int = 1) -> dict[str, float]:
    """Split a money amount by weight, giving the last island the rounding drift."""
    keys = list(weights)
    if not keys:
        return {}
    shares = _normalise(weights)
    parts = {k: round(total * shares[k], places) for k in keys}
    parts[keys[-1]] = round(total - sum(parts[k] for k in keys[:-1]), places)
    return parts


def island_weights(player) -> dict[str, float]:
    """Each island's share of the player, used to split pooled quantities.

    Derived from workers whose profession only one of the player's islands
    claims; falls back to labour requirements, then to an even split.
    """
    roles = [r.name for r in player.roles]
    if not roles:
        return {}
    claims = {role: role_professions(role) for role in roles}

    unambiguous = {role: 0.0 for role in roles}
    for worker in player.workforce.workers:
        owners = [role for role in roles if worker.profession in claims[role]]
        if len(owners) == 1:
            unambiguous[owners[0]] += 1
    if sum(unambiguous.values()) > 0:
        return _normalise(unambiguous)

    labour = {
        role: float(sum(LABOUR_REQUIREMENTS.get(role, {}).values()))
        for role in roles
    }
    if sum(labour.values()) > 0:
        return _normalise(labour)
    return _normalise({role: 1.0 for role in roles})


# ---------------------------------------------------------------------------
# Per-island breakdowns
# ---------------------------------------------------------------------------

def _allocate_by_claim(
    quantities: dict[str, int],
    roles: list[str],
    claims: dict[str, set[str]],
    weights: dict[str, float],
) -> dict[str, dict[str, int]]:
    """Split ``{key: count}`` across islands, preferring the islands claiming it."""
    out: dict[str, dict[str, int]] = {role: {} for role in roles}
    for key, count in quantities.items():
        if count <= 0:
            continue
        claimants = [role for role in roles if key in claims[role]]
        target = claimants or roles
        parts = split_int(count, {role: weights[role] for role in target})
        for role, part in parts.items():
            if part:
                out[role][key] = out[role].get(key, 0) + part
    return out


def personnel_by_island(player, training_targets: dict[int, str] | None = None) -> dict[str, dict]:
    """Per-island ``profession_summary``-shaped payloads.

    Same shape as ``Workforce.profession_summary`` so the dashboard can render
    an island tab through exactly the code path it uses for the consolidated
    view.
    """
    roles = [r.name for r in player.roles]
    weights = island_weights(player)
    claims = {role: role_professions(role) for role in roles}
    summary = player.workforce.profession_summary(training_targets)

    active = _allocate_by_claim(
        {k: v["active"] for k, v in summary.items()}, roles, claims, weights
    )
    training = _allocate_by_claim(
        {k: v["training"] for k, v in summary.items()}, roles, claims, weights
    )

    out: dict[str, dict] = {}
    for role in roles:
        professions: dict[str, dict] = {}
        for key in set(active[role]) | set(training[role]):
            professions[key] = {
                "label": summary[key]["label"],
                "active": active[role].get(key, 0),
                "training": training[role].get(key, 0),
            }
        out[role] = professions
    return out


def _band_summary(professions: dict[str, dict], field: str) -> dict[str, int]:
    bands = {"Manager": 0, "Technician": 0, "Worker": 0}
    for key, counts in professions.items():
        try:
            band = PROFESSION_BAND[Profession(key)].value
        except (ValueError, KeyError):
            band = "Worker"
        bands[band] = bands.get(band, 0) + counts.get(field, 0)
    return bands


def equipment_value_by_island(player, capital_catalogue=None, current_tick: int = 0) -> dict[str, float]:
    """Depreciated capital book value attributed to each island."""
    roles = [r.name for r in player.roles]
    weights = island_weights(player)
    by_item = player.capital_book_value_by_item(capital_catalogue, current_tick)
    item_roles = {item.item_id: item.role for item in (capital_catalogue or [])}

    out = {role: 0.0 for role in roles}
    shared = 0.0
    for item_id, value in by_item.items():
        role = item_roles.get(item_id)
        if role in out:
            out[role] += value
        else:
            # "Any"-role equipment, or kit for a role this player has since
            # lost — it still backs the player's operations, so spread it.
            shared += value
    if shared:
        for role, part in split_float(shared, weights, places=2).items():
            out[role] += part
    return {role: round(value, 1) for role, value in out.items()}


def island_breakdown(
    player,
    capital_catalogue=None,
    current_tick: int = 0,
    training_targets: dict[int, str] | None = None,
) -> list[dict]:
    """One payload per island the player holds, each isolated from the others.

    Returns ``[]`` for a player with fewer than two roles — a single-role
    player's island *is* the consolidated view, so callers keep using the
    existing fields and nothing has to change for the common case.
    """
    roles = [r.name for r in player.roles]
    if len(roles) < 2:
        return []

    weights = island_weights(player)
    claims = {role: role_resources(role) for role in roles}

    inventory = _allocate_by_claim(
        {r.value: qty for r, qty in player.inventory.amounts.items() if qty > 0},
        roles,
        claims,
        weights,
    )
    personnel = personnel_by_island(player, training_targets)
    equipment = equipment_value_by_island(player, capital_catalogue, current_tick)
    treasury = split_float(float(player.dollops), weights)

    # Headcounts are allocated from the roster directly rather than summed out
    # of the personnel display, so "active / total" on an island tab still adds
    # back up to the consolidated figure (which counts on-contract and absent
    # workers differently from the per-profession display).
    prof_claims = {role: role_professions(role) for role in roles}
    head_total: dict[str, int] = {}
    for worker in player.workforce.workers:
        head_total[worker.profession] = head_total.get(worker.profession, 0) + 1
    head_active: dict[str, int] = {}
    for worker in player.workforce.active_workers:
        head_active[worker.profession] = head_active.get(worker.profession, 0) + 1
    total_by_island = _allocate_by_claim(head_total, roles, prof_claims, weights)
    active_by_island = _allocate_by_claim(head_active, roles, prof_claims, weights)

    islands = []
    for role in roles:
        professions = personnel[role]
        active_bands = _band_summary(professions, "active")
        training_bands = _band_summary(professions, "training")
        islands.append({
            "role": role,
            "share": round(weights[role], 4),
            "treasury": treasury[role],
            "dollops": treasury[role],
            "equipment_value": equipment[role],
            "inventory": inventory[role],
            "workforce_professions": professions,
            "workforce_bands": active_bands,
            "workforce_training_bands": training_bands,
            "workforce_active": sum(active_by_island[role].values()),
            "workforce_count": sum(total_by_island[role].values()),
        })
    return islands


def profession_label(profession: str) -> str:
    try:
        return PROFESSION_LABEL.get(Profession(profession), profession)
    except ValueError:
        return profession
