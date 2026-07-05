from __future__ import annotations
import re
from dataclasses import replace
from math import ceil, floor
from ..models.player import Player
from ..models.resource import ResourceType
from ..engine.events import EventResult
from ..constants import (
    BASE_PRODUCTION, PRODUCTION_INPUTS, SEASONAL_WORKFORCE,
    SEASONAL_YIELD, FARMER_SEASONAL_CONVERSION, MANUFACTURER_PRODUCT_LINES,
    OUTPUT_PRODUCTION_INPUTS,
    LABOUR_REQUIREMENTS, SKILLED_PROFESSIONS, PRODUCER_PRODUCTIVITY_MULTIPLIER,
    KITCHEN_SPECS,
    EXPERTISE_DEGRADATION_FLOORS, EXPERTISE_DEGRADATION_ROLE_OVERRIDES,
    EXPERTISE_DEGRADATION_ENABLED, UNIQUE_SPECIALIST_PROFESSION,
    FARMER_HORTICULTURALIST_BONUS_MULTIPLIER,
    FARMER_VETERINARIAN_BONUS_MULTIPLIER,
    FARMER_FISH_WITHOUT_MARINE_BIOLOGIST_MULTIPLIER,
    FISH_PROCESSING_TECHNICIANS_PER_BOAT,
    MANUFACTURER_DURABLE_CAP_BASE,
    MANUFACTURER_DURABLE_CAP_BONUS_PER_ITEM,
    MANUFACTURER_DURABLE_CAP_MAX,
    MANUFACTURER_DURABLE_OUTPUTS,
)
from ..constants_capacity import CAPITAL_CATALOGUE, PRODUCTION_RECIPES
from ..models.capacity import compute_capacity, find_item, recipe_for
from ..models.profession import Profession, WorkerBand, band_of, PROFESSION_BAND
from .engineering import (
    active_engineer_specialty_counts,
    adjusted_capacity_for_engineers,
    adjusted_recipe_for_engineers,
    adjusted_workforce_for_engineers,
    electrical_efficiency_bonus,
)


def _band_of_profession_str(profession: str) -> WorkerBand | None:
    """Look up the band for a profession by its string value.

    Returns None if the string isn't a known Profession enum value (which
    shouldn't happen in practice — SKILLED_PROFESSIONS only lists valid
    enum string values — but defensive in case of a typo'd override).
    """
    try:
        prof_enum = Profession(profession)
    except ValueError:
        return None
    return PROFESSION_BAND.get(prof_enum)


class InsufficientInputsError(Exception):
    def __init__(self, role: str, missing: dict[ResourceType, int]):
        self.role = role
        self.missing = missing
        parts = ", ".join(f"{qty}x {r.value}" for r, qty in missing.items())
        super().__init__(f"{role} cannot produce: missing {parts}")


class InsufficientOperatingCashError(Exception):
    def __init__(self, role: str, needed: float, available: float):
        self.role = role
        self.needed = needed
        self.available = available
        super().__init__(
            f"{role} cannot produce: needs {needed:.1f} Dp build cash, "
            f"has {available:.1f} Dp"
        )


class ProductionEngine:
    # Optional ResourceFlowTelemetry (B1/B2, #73); set by Game.setup() in
    # simulation.  None during normal play and in direct unit-test construction.
    telemetry: object | None = None

    def _has_active_profession(self, player: Player, profession: str) -> bool:
        return any(w.profession == profession for w in player.workforce.active_workers)

    def _farmer_output_multiplier(self, player: Player, output: ResourceType) -> float:
        """Farmer specialist bonuses and fishing-line staffing modifiers."""
        if output in (ResourceType.GRAIN, ResourceType.PRODUCE):
            if self._has_active_profession(player, Profession.HORTICULTURALIST.value):
                return FARMER_HORTICULTURALIST_BONUS_MULTIPLIER
            return 1.0
        if output == ResourceType.MEAT:
            if self._has_active_profession(player, Profession.VETERINARIAN.value):
                return FARMER_VETERINARIAN_BONUS_MULTIPLIER
            return 1.0
        if output == ResourceType.FISH:
            return self._farmer_fish_multiplier(player)
        return 1.0

    def _farmer_fish_multiplier(self, player: Player) -> float:
        multiplier = 1.0
        if not self._has_active_profession(player, Profession.MARINE_BIOLOGIST.value):
            multiplier *= FARMER_FISH_WITHOUT_MARINE_BIOLOGIST_MULTIPLIER

        boats = player.effective_capital_inventory().get("farmer.fishing_boat", 0)
        if boats <= 0:
            return multiplier

        technicians_needed = boats * FISH_PROCESSING_TECHNICIANS_PER_BOAT
        technicians = player.workforce.count_profession(
            Profession.FISH_PROCESSING_TECHNICIAN.value
        )
        multiplier *= min(1.0, technicians / technicians_needed)

        # The first boat preserves the old base yield; additional boats scale
        # the fishing line linearly while capacity still caps impossible output.
        multiplier *= boats
        return multiplier
    def _has_enhanced_metal_equipment(self, player: Player) -> bool:
        # Effective inventory: unmaintained units don't count this season.
        return player.effective_capital_inventory().get(
            "miner.enhanced_crusher_smelter", 0
        ) > 0

    def _metal_recipe_multiplier(self, player: Player) -> float:
        return 3.0 if self._has_enhanced_metal_equipment(player) else 1.0

    def run_kitchens(self, player: Player) -> list[str]:
        """Run all kitchen capital once for this player this season.

        Kitchens are deliberately separate from role production: any island can
        own one, and each kitchen idles gracefully when short on staffing or
        raw ingredients.
        """
        chef_count = player.workforce.count_profession(Profession.CHEF.value)
        chefs_available = chef_count
        effective_inventory = player.effective_capital_inventory()
        messages: list[str] = []

        for item_id, spec in KITCHEN_SPECS.items():
            kitchen_count = effective_inventory.get(item_id, 0)
            label = self._kitchen_label(item_id)
            for kitchen_number in range(1, kitchen_count + 1):
                if spec.get("requires_chef", False):
                    if chefs_available <= 0:
                        messages.append(
                            f"{label} {kitchen_number} idle: needs a Chef."
                        )
                        continue
                    chefs_available -= 1
                produced, missing = self._run_one_kitchen(player, spec)
                if produced:
                    messages.append(
                        f"{label} {kitchen_number}: produced {produced} Food."
                    )
                else:
                    messages.append(
                        f"{label} {kitchen_number} idle: short on {missing}."
                    )
        return messages

    def _kitchen_label(self, item_id: str) -> str:
        item = find_item(CAPITAL_CATALOGUE, item_id)
        return item.name if item is not None else item_id

    def _run_one_kitchen(self, player: Player, spec: dict) -> tuple[int, str]:
        food_qty = int(spec["food_per_season"])
        recipe = spec["recipe"]
        grain_needed = ceil(recipe.get("Grain", 0) * food_qty)
        produce_needed = ceil(recipe.get("Produce", 0) * food_qty)
        protein_needed = ceil(recipe.get("Protein", 0) * food_qty)
        shortages: list[str] = []
        if player.inventory.get(ResourceType.GRAIN) < grain_needed:
            shortages.append("Grain")
        if player.inventory.get(ResourceType.PRODUCE) < produce_needed:
            shortages.append("Produce")
        available_protein = (
            player.inventory.get(ResourceType.FISH)
            + player.inventory.get(ResourceType.MEAT)
        )
        if available_protein < protein_needed:
            shortages.append("Fish/Meat")
        if shortages:
            return 0, ", ".join(shortages)

        fish = player.inventory.get(ResourceType.FISH)
        meat = player.inventory.get(ResourceType.MEAT)
        prefer_fish = fish >= meat
        first = ResourceType.FISH if prefer_fish else ResourceType.MEAT
        second = ResourceType.MEAT if prefer_fish else ResourceType.FISH
        first_used = min(protein_needed, player.inventory.get(first))
        second_used = protein_needed - first_used

        player.give_resources(ResourceType.GRAIN, grain_needed)
        player.give_resources(ResourceType.PRODUCE, produce_needed)
        if first_used:
            player.give_resources(first, first_used)
        if second_used:
            player.give_resources(second, second_used)
        player.receive_resources(ResourceType.FOOD, food_qty)
        if self.telemetry is not None:
            self.telemetry.record_consumed(ResourceType.GRAIN, grain_needed)
            self.telemetry.record_consumed(ResourceType.PRODUCE, produce_needed)
            if first_used:
                self.telemetry.record_consumed(first, first_used)
            if second_used:
                self.telemetry.record_consumed(second, second_used)
            self.telemetry.record_produced(ResourceType.FOOD, food_qty)
        return food_qty, ""

    def _adjust_recipe_for_player(
        self, recipe, player: Player
    ):
        if (
            recipe.role == "Miner"
            and recipe.output == ResourceType.METAL.value
            and self._has_enhanced_metal_equipment(player)
        ):
            recipe = replace(
                recipe,
                inputs={
                    resource: (amount * 0.5 if resource == ResourceType.OIL.value else amount)
                    for resource, amount in recipe.inputs.items()
                },
            )
        return recipe

    def _role_player(self, player: Player, role) -> Player:
        return replace(player, roles=[role])

    def _seasonal_workforce_required(self, player: Player, season_name: str) -> int:
        total = 0
        for role in player.roles:
            total += SEASONAL_WORKFORCE.get(role.name, {}).get(season_name, 0)
        return total

    def _seasonal_labour_requirements(
        self, role_name: str, season_name: str, product_line: str | None = None
    ) -> tuple[int, int]:
        """Return (required_skilled, required_unskilled) scaled for the current season.

        For the Manufacturer, uses the chosen product_line's labour spec instead of
        the generic LABOUR_REQUIREMENTS entry, then scales for the season.
        """
        if role_name == "Manufacturer" and product_line and product_line in MANUFACTURER_PRODUCT_LINES:
            line = MANUFACTURER_PRODUCT_LINES[product_line]
            base = {"skilled": line["skilled"], "unskilled": line["unskilled"]}
        else:
            base = LABOUR_REQUIREMENTS.get(role_name, {"skilled": 0, "unskilled": 0})
        base_total = base["skilled"] + base["unskilled"]
        seasonal_total = SEASONAL_WORKFORCE.get(role_name, {}).get(season_name, base_total)
        if base_total <= 0:
            return 0, 0
        scale = seasonal_total / base_total
        skilled = max(1, round(base["skilled"] * scale))
        unskilled = max(0, round(base["unskilled"] * scale))
        return skilled, unskilled

    def _labour_productivity_factor(
        self, player: Player, season_name: str, product_line: str | None = None
    ) -> float:
        """Weighted skilled+unskilled productivity factor across all of a player's roles.

        Applies the graceful-degradation floor (GitHub #47 / 2026-05-27
        playtest) as a safety net: when the natural factor would otherwise
        leave the player frozen at zero production, the floor lets them
        limp along at a band-specific fraction of normal so the market
        can still trade and recovery is possible.
        """
        total_skilled = 0
        total_unskilled = 0
        all_skilled_profs: set[str] = set()
        for role in player.roles:
            s, u = self._seasonal_labour_requirements(role.name, season_name, product_line)
            total_skilled += s
            total_unskilled += u
            all_skilled_profs.update(SKILLED_PROFESSIONS.get(role.name, []))
        natural = player.workforce.labour_productivity_factor(
            total_skilled, total_unskilled, list(all_skilled_profs)
        )
        natural = min(1.0, natural + electrical_efficiency_bonus(player))
        if not EXPERTISE_DEGRADATION_ENABLED:
            return natural
        floor = self.expertise_degradation_floor(player)
        return max(natural, floor)

    @staticmethod
    def expertise_degradation_floor(player: Player) -> float:
        """Return the per-player production floor based on missing expertise.

        For each of the player's roles, compose floors multiplicatively:

        - If the role's unique specialist (Farmer/Miner/Doctor/Banker/
          Professor/Engineer/LogisticsManager) is absent → 0.10.
        - Else if no Manager-tier worker at all → 0.25 (rare; e.g. Doctor
          with no Doctor AND no Nurse).
        - If no Technician-tier worker at all → 0.50 (composes with above).
        - Unskilled missing has no floor effect.

        Across multiple roles, take the MIN floor — multi-role expertise
        gaps are tracked the same restrictive way the underlying
        productivity factor sums them across roles.  Returns 1.0 if the
        player has no expertise gaps in any role (no floor applies).

        Public so the server payload can surface it on the capacity panel
        without re-implementing the math.
        """
        floors_per_role: list[float] = []
        for role in player.roles:
            role_name = role.name
            overrides = EXPERTISE_DEGRADATION_ROLE_OVERRIDES.get(role_name, {})
            role_floor = 1.0
            skilled_profs = SKILLED_PROFESSIONS.get(role_name, [])

            # Unique specialist check (most-severe single check).
            unique = UNIQUE_SPECIALIST_PROFESSION.get(role_name)
            unique_present = bool(
                unique and player.workforce.count_profession(unique) > 0
            )
            any_manager_present = any(
                player.workforce.count_profession(prof) > 0
                for prof in skilled_profs
                if _band_of_profession_str(prof) == WorkerBand.MANAGER
            )
            if unique and not unique_present:
                role_floor *= overrides.get(
                    "unique_specialist",
                    EXPERTISE_DEGRADATION_FLOORS["unique_specialist"],
                )
            elif not any_manager_present and any(
                _band_of_profession_str(p) == WorkerBand.MANAGER
                for p in skilled_profs
            ):
                # No unique specialist required, but no Manager-tier at
                # all (rare — e.g. Doctor with no Doctor *and* no Nurse
                # would land here if the unique check were relaxed).
                role_floor *= overrides.get(
                    "manager",
                    EXPERTISE_DEGRADATION_FLOORS["manager"],
                )

            # Technician-tier check (composes with the above).
            tech_profs = [
                p for p in skilled_profs
                if _band_of_profession_str(p) == WorkerBand.TECHNICIAN
            ]
            if tech_profs and not any(
                player.workforce.count_profession(p) > 0 for p in tech_profs
            ):
                role_floor *= overrides.get(
                    "technician",
                    EXPERTISE_DEGRADATION_FLOORS["technician"],
                )

            floors_per_role.append(role_floor)

        if not floors_per_role:
            return 1.0
        return min(floors_per_role)

    def _role_inputs(
        self, role_name: str, season_name: str, product_line: str | None = None
    ) -> dict[ResourceType, int]:
        """Return inputs for a role this season."""
        if role_name == "Farmer":
            raw = FARMER_SEASONAL_CONVERSION[season_name]["inputs"]
        elif role_name == "Manufacturer":
            line_key = product_line if product_line in MANUFACTURER_PRODUCT_LINES else next(iter(MANUFACTURER_PRODUCT_LINES))
            raw = MANUFACTURER_PRODUCT_LINES[line_key]["inputs"]
        else:
            raw = PRODUCTION_INPUTS.get(role_name, {})
        return {ResourceType(k): v for k, v in raw.items()}

    def _role_outputs(
        self, role_name: str, season_name: str, product_line: str | None = None
    ) -> dict[ResourceType, int]:
        """Return base outputs for a role this season."""
        if role_name == "Farmer":
            raw = FARMER_SEASONAL_CONVERSION[season_name]["outputs"]
        elif role_name == "Manufacturer":
            line_key = product_line if product_line in MANUFACTURER_PRODUCT_LINES else next(iter(MANUFACTURER_PRODUCT_LINES))
            line = MANUFACTURER_PRODUCT_LINES[line_key]
            raw = {line["output"]: line["qty"]}
        else:
            raw = BASE_PRODUCTION.get(role_name, {})
        return {ResourceType(k): v for k, v in raw.items()}

    def _output_inputs(self, role_name: str, output: ResourceType) -> dict[ResourceType, int]:
        """Return inputs consumed only when a specific output is produced."""
        raw = OUTPUT_PRODUCTION_INPUTS.get(role_name, {}).get(output.value, {})
        return {ResourceType(k): v for k, v in raw.items()}

    def _seasonal_yield(self, role_name: str, season_name: str) -> float:
        """Seasonal base-yield multiplier (1.0 for Farmer — table already encodes it)."""
        if role_name == "Farmer":
            return 1.0
        return SEASONAL_YIELD.get(role_name, {}).get(season_name, 1.0)

    def _all_inputs(
        self, player: Player, season_name: str, product_line: str | None = None
    ) -> dict[ResourceType, int]:
        totals: dict[ResourceType, int] = {}
        for role in player.roles:
            for r, qty in self._role_inputs(role.name, season_name, product_line).items():
                totals[r] = totals.get(r, 0) + qty

        # Apply patent boost: average multiplier across all produced outputs.
        # Each active patent on an output reduces the buyer's input cost by 20%
        # (capped at 3 patents = 60% reduction per output).  We apply the
        # average across the role's outputs to all inputs uniformly — patents
        # on any output yield some benefit, full benefit when all outputs are
        # patented.
        produced = [r for r in player.all_produced_resources()
                    if r != ResourceType.PATENTS]
        if produced and player.active_patents:
            multipliers = [player.patent_input_multiplier(r.value) for r in produced]
            avg_mult = sum(multipliers) / len(multipliers)
            if avg_mult < 1.0:
                totals = {r: max(0, int(round(qty * avg_mult)))
                          for r, qty in totals.items()}
        return totals

    def _affordable_output_inputs(
        self,
        player: Player,
        role_name: str,
        outputs: dict[ResourceType, int],
    ) -> tuple[dict[ResourceType, int], set[ResourceType]]:
        """Return output-specific inputs that can be paid, plus skipped outputs.

        Output-specific gates are intentionally non-atomic: if an Educator lacks
        Reagents for Patents, Expertise/Courses still run.
        """
        inventory_after_inputs = {
            resource: player.inventory.get(resource)
            for resource in ResourceType
        }
        consumed: dict[ResourceType, int] = {}
        skipped: set[ResourceType] = set()
        for output, qty in outputs.items():
            if qty <= 0:
                continue
            needs = self._output_inputs(role_name, output)
            missing = [
                resource
                for resource, amount in needs.items()
                if inventory_after_inputs.get(resource, 0) < amount
            ]
            if missing:
                skipped.add(output)
                continue
            for resource, amount in needs.items():
                inventory_after_inputs[resource] = inventory_after_inputs.get(resource, 0) - amount
                consumed[resource] = consumed.get(resource, 0) + amount
        return consumed, skipped

    def _freight_surcharge(self, product_line: str | None, qty: int) -> int:
        """Return Freight units consumed to ship produced goods (Manufacturer only)."""
        if not product_line or product_line not in MANUFACTURER_PRODUCT_LINES:
            return 0
        freight_per_unit = MANUFACTURER_PRODUCT_LINES[product_line]["freight_per_unit"]
        if freight_per_unit <= 0 or qty <= 0:
            return 0
        board_scale_qty = max(1, round(qty / PRODUCER_PRODUCTIVITY_MULTIPLIER))
        return freight_per_unit * board_scale_qty

    def can_produce(
        self,
        player: Player,
        event_result: EventResult,
        season_name: str = "Spring",
        product_line: str | None = None,
    ) -> tuple[bool, dict[ResourceType, int]]:
        if event_result.outage:
            return False, {}
        inputs = self._all_inputs(player, season_name, product_line)
        # Add freight surcharge to required inputs check (estimate using base qty)
        if product_line and product_line in MANUFACTURER_PRODUCT_LINES:
            base_qty = MANUFACTURER_PRODUCT_LINES[product_line]["qty"]
            freight_needed = self._freight_surcharge(product_line, base_qty)
            if freight_needed:
                inputs[ResourceType.FREIGHT] = inputs.get(ResourceType.FREIGHT, 0) + freight_needed
        missing = {
            r: qty - player.inventory.get(r)
            for r, qty in inputs.items()
            if player.inventory.get(r) < qty
        }
        return len(missing) == 0, missing

    def produce(
        self,
        player: Player,
        event_result: EventResult,
        season_name: str = "Spring",
        product_line: str | None = None,
    ) -> dict[ResourceType, int]:
        if event_result.outage:
            return {}

        inputs = self._all_inputs(player, season_name, product_line)
        missing = {r: qty for r, qty in inputs.items() if player.inventory.get(r) < qty}
        if missing:
            if self.telemetry is not None:
                for r in missing:
                    self.telemetry.record_starvation(r)
            raise InsufficientInputsError(player.role_names(), missing)

        for r, qty in inputs.items():
            player.give_resources(r, qty)
            if self.telemetry is not None:
                self.telemetry.record_consumed(r, qty)

        workforce_factor = self._labour_productivity_factor(player, season_name, product_line)
        effective_factor = max(player.production_capacity, workforce_factor)

        produced: dict[ResourceType, int] = {}
        for role in player.roles:
            sy = self._seasonal_yield(role.name, season_name)
            role_outputs = self._role_outputs(role.name, season_name, product_line)
            output_inputs, skipped_outputs = self._affordable_output_inputs(
                player, role.name, role_outputs
            )
            for r, qty in output_inputs.items():
                player.give_resources(r, qty)
                if self.telemetry is not None:
                    self.telemetry.record_consumed(r, qty)
            for r, base_qty in role_outputs.items():
                if r in skipped_outputs:
                    continue
                qty = max(0, int(base_qty * sy * event_result.yield_modifier * effective_factor))
                if role.name == "Farmer":
                    qty = int(qty * self._farmer_output_multiplier(player, r))
                qty += event_result.productivity_bonus
                if qty > 0:
                    # Deduct freight surcharge for Manufacturer shipment
                    freight = self._freight_surcharge(product_line, qty)
                    if freight:
                        if player.inventory.get(ResourceType.FREIGHT) >= freight:
                            player.give_resources(ResourceType.FREIGHT, freight)
                        # If not enough freight, ship anyway (partial loss already modelled by can_produce check)
                    player.receive_resources(r, qty)
                    produced[r] = produced.get(r, 0) + qty
                    if self.telemetry is not None:
                        self.telemetry.record_produced(r, qty)

        player.workforce.apply_season_work()
        return produced

    def production_preview(
        self,
        player: Player,
        event_result: EventResult,
        season_name: str = "Spring",
        product_line: str | None = None,
    ) -> dict:
        if event_result.outage:
            return {"outage": True, "reason": event_result.event_name, "inputs": {}, "outputs": {}}

        inputs = self._all_inputs(player, season_name, product_line)
        can, missing = self.can_produce(player, event_result, season_name, product_line)

        # Aggregate labour requirements across all roles
        total_skilled_req = 0
        total_unskilled_req = 0
        all_skilled_profs: set[str] = set()
        for role in player.roles:
            s, u = self._seasonal_labour_requirements(role.name, season_name, product_line)
            total_skilled_req += s
            total_unskilled_req += u
            all_skilled_profs.update(SKILLED_PROFESSIONS.get(role.name, []))
        skilled_profs_list = list(all_skilled_profs)

        skilled_active = len([w for w in player.workforce.active_workers if w.profession in skilled_profs_list])
        unskilled_active = len([w for w in player.workforce.active_workers if w.profession not in skilled_profs_list])

        workforce_factor = player.workforce.labour_productivity_factor(
            total_skilled_req, total_unskilled_req, skilled_profs_list
        )
        workforce_factor = min(1.0, workforce_factor + electrical_efficiency_bonus(player))
        effective_factor = max(player.production_capacity, workforce_factor)
        fill_pct = round(player.workforce.workforce_fill_rate(
            self._seasonal_workforce_required(player, season_name)
        ) * 100)
        eff_pct = round(player.workforce.average_efficiency * 100)

        outputs: dict[ResourceType, int] = {}
        freight_surcharge = 0
        output_specific_inputs: dict[ResourceType, int] = {}
        skipped_outputs: dict[str, list[ResourceType]] = {}
        for role in player.roles:
            sy = self._seasonal_yield(role.name, season_name)
            role_outputs = self._role_outputs(role.name, season_name, product_line)
            role_specific_inputs, role_skipped = self._affordable_output_inputs(
                player, role.name, role_outputs
            )
            if role_skipped:
                skipped_outputs[role.name] = sorted(role_skipped, key=lambda r: r.value)
            for resource, qty_needed in role_specific_inputs.items():
                output_specific_inputs[resource] = (
                    output_specific_inputs.get(resource, 0) + qty_needed
                )
            for r, base_qty in role_outputs.items():
                if r in role_skipped:
                    continue
                qty = max(0, int(base_qty * sy * event_result.yield_modifier * effective_factor))
                if role.name == "Farmer":
                    qty = int(qty * self._farmer_output_multiplier(player, r))
                qty += event_result.productivity_bonus
                if qty > 0:
                    outputs[r] = outputs.get(r, 0) + qty
                    freight_surcharge += self._freight_surcharge(product_line, qty)

        result = {
            "outage": False,
            "can_produce": can,
            "missing_inputs": missing,
            "inputs_consumed": inputs,
            "output_specific_inputs": output_specific_inputs,
            "skipped_outputs": skipped_outputs,
            "outputs": outputs,
            "event": event_result.event_name,
            "yield_modifier": event_result.yield_modifier,
            "seasonal_yield": {r.name: self._seasonal_yield(r.name, season_name) for r in player.roles},
            "workforce_required": self._seasonal_workforce_required(player, season_name),
            "workforce_count": player.workforce.count,
            "fill_rate_pct": fill_pct,
            "avg_efficiency_pct": eff_pct,
            "workforce_factor": round(workforce_factor, 3),
            "effective_factor": round(effective_factor, 3),
            "base_capacity_pct": round(player.production_capacity * 100),
            # Labour split
            "skilled_required": total_skilled_req,
            "unskilled_required": total_unskilled_req,
            "skilled_active": skilled_active,
            "unskilled_active": unskilled_active,
        }
        if product_line:
            result["product_line"] = product_line
            result["freight_surcharge"] = freight_surcharge
        return result

    def _capacity_limit(
        self,
        player: Player,
        role_name: str,
        output: ResourceType,
        season_name: str = "Spring",
    ) -> int | None:
        recipe = recipe_for(PRODUCTION_RECIPES, role_name, output.value)
        if not recipe:
            return None
        recipe = self._adjust_recipe_for_player(recipe, player)
        engineer_counts = active_engineer_specialty_counts(player)
        recipe = adjusted_recipe_for_engineers(recipe, engineer_counts)

        mult = player.patent_input_multiplier(recipe.output)
        if mult < 1.0:
            recipe = replace(
                recipe,
                inputs={resource: amount * mult for resource, amount in recipe.inputs.items()},
            )

        bands = player.workforce.band_summary()
        wf_by_band = {
            WorkerBand.MANAGER: bands.get("Manager", 0),
            WorkerBand.TECHNICIAN: bands.get("Technician", 0),
            WorkerBand.WORKER: bands.get("Worker", 0),
        }
        wf_by_band = adjusted_workforce_for_engineers(wf_by_band, engineer_counts)
        on_hand = {r.value: player.inventory.get(r) for r in ResourceType}
        if (
            role_name == "Farmer"
            and output.value in FARMER_SEASONAL_CONVERSION[season_name]["outputs"]
            and output not in (ResourceType.FOOD, ResourceType.MEAT)
        ):
            enough_for_seasonal_run = all(
                player.inventory.get(ResourceType(resource)) >= amount
                for resource, amount in FARMER_SEASONAL_CONVERSION[season_name]["inputs"].items()
            )
            on_hand = dict(on_hand)
            for resource in recipe.inputs:
                on_hand[resource] = float("inf") if enough_for_seasonal_run else 0
        if role_name == "Farmer" and output == ResourceType.FOOD:
            # Packaged Food accepts either Fish or Meat as its protein.
            on_hand[ResourceType.FISH.value] = (
                player.inventory.get(ResourceType.FISH)
                + player.inventory.get(ResourceType.MEAT)
            )
        cap = compute_capacity(
            recipe=recipe,
            catalogue=CAPITAL_CATALOGUE,
            owned=player.effective_capital_inventory(),
            workforce=wf_by_band,
            on_hand=on_hand,
        )
        cap = adjusted_capacity_for_engineers(cap, engineer_counts, recipe.output)
        if cap.max_producible == float("inf"):
            return None
        return max(0, floor(cap.max_producible))

    def production_options(
        self,
        player: Player,
        event_result: EventResult,
        season_name: str = "Spring",
    ) -> list[dict]:
        """Return per-product production choices for this player right now."""
        if event_result.outage:
            return []

        options: list[dict] = []
        for role in player.roles:
            line_keys = (
                list(MANUFACTURER_PRODUCT_LINES)
                if role.name == "Manufacturer"
                else [None]
            )
            for product_line in line_keys:
                role_player = self._role_player(player, role)
                preview = self.production_preview(
                    role_player, event_result, season_name, product_line
                )
                if preview.get("outage"):
                    continue
                for output, preview_qty in preview.get("outputs", {}).items():
                    if preview_qty <= 0:
                        continue
                    if role.name == "Miner" and output == ResourceType.METAL:
                        preview_qty = int(preview_qty * self._metal_recipe_multiplier(player))
                    capacity_limit = self._capacity_limit(
                        player, role.name, output, season_name
                    )
                    max_qty = preview_qty if capacity_limit is None else min(preview_qty, capacity_limit)
                    if role.name == "Manufacturer" and product_line:
                        max_qty = min(
                            max_qty,
                            self._manufacturer_cash_limited_qty(player, product_line),
                        )
                        if output.value in MANUFACTURER_DURABLE_OUTPUTS:
                            max_qty = min(
                                max_qty,
                                self.manufacturer_durable_allowance_remaining(player),
                            )
                    options.append({
                        "role": role.name,
                        "output": output,
                        "product_line": product_line,
                        "max_qty": max(0, int(max_qty)),
                        "preview_qty": int(preview_qty),
                        "capacity_limit": capacity_limit,
                        "preview": preview,
                    })
            if role.name == "Farmer":
                # Meat is a deliberate livestock line: 4 Grain feedstock per
                # Meat, with Veterinarian depth boosting output.
                meat_capacity = self._capacity_limit(
                    player, role.name, ResourceType.MEAT, season_name
                )
                if meat_capacity and meat_capacity > 0:
                    meat_max = int(
                        meat_capacity
                        * self._farmer_output_multiplier(player, ResourceType.MEAT)
                    )
                    if meat_max > 0:
                        options.append({
                            "role": role.name,
                            "output": ResourceType.MEAT,
                            "product_line": None,
                            "max_qty": meat_max,
                            "preview_qty": meat_max,
                            "capacity_limit": meat_capacity,
                            "preview": self.production_preview(
                                self._role_player(player, role), event_result, season_name
                            ),
                        })
                # Food is now a deliberate convenience product, not a crop.
                # It is packaged only when the island has an Industrial Kitchen
                # and a balanced set of ingredients on hand.
                preview_qty = min(
                    player.inventory.get(ResourceType.GRAIN),
                    player.inventory.get(ResourceType.PRODUCE),
                    player.inventory.get(ResourceType.FISH)
                    + player.inventory.get(ResourceType.MEAT),
                )
                capacity_limit = self._capacity_limit(
                    player, role.name, ResourceType.FOOD, season_name
                )
                max_qty = preview_qty if capacity_limit is None else min(preview_qty, capacity_limit)
                if max_qty > 0:
                    options.append({
                        "role": role.name,
                        "output": ResourceType.FOOD,
                        "product_line": None,
                        "max_qty": int(max_qty),
                        "preview_qty": int(preview_qty),
                        "capacity_limit": capacity_limit,
                        "preview": self.production_preview(
                            self._role_player(player, role), event_result, season_name
                        ),
                    })
        return [opt for opt in options if opt["max_qty"] > 0]

    @staticmethod
    def produce_option_key(option: dict) -> str:
        """Stable identity for a production option across menu build + dispatch.

        Encodes (role, output, product_line) so the dashboard's per-product
        Produce button can round-trip back to the exact option in
        ``production_options`` when the player picks it, without relying on a
        fragile list index.
        """
        return f"{option['role']}|{option['output'].value}|{option['product_line'] or ''}"

    def produce_menu_options(
        self,
        player: Player,
        event_result: EventResult,
        season_name: str = "Spring",
        prices: dict | None = None,
    ) -> list[dict]:
        """Menu-ready produce choices: one entry per producible product.

        Turns ``production_options`` into ``[{key, label, max_qty, context}]`` so
        the action menu can render a distinct "Produce <product>" button per
        output (e.g. "Produce Equipment Spares Kits") instead of a single generic
        Produce action that opens a follow-up picker.  ``context`` is a compact
        sub-line for the button, e.g. "2 Metal + 1 Oil → 4 Spares · 9 runs from
        stock · 12 Dp each".  Pass ``prices`` (market current_prices) to include
        the unit price.
        """
        prices = prices or {}
        out: list[dict] = []
        for option in self.production_options(player, event_result, season_name):
            product_line = option["product_line"]
            output = option["output"]
            if product_line and product_line in MANUFACTURER_PRODUCT_LINES:
                spec = MANUFACTURER_PRODUCT_LINES[product_line]
                name = spec["desc"]
                context = self._recipe_context(player, spec, output)
                build_cost = float(spec.get("build_cost_dollops", 0.0))
                if build_cost > 0:
                    context += f" · {build_cost:g} Dp/unit build cost"
                if output.value in MANUFACTURER_DURABLE_OUTPUTS:
                    context += (
                        " · durable allowance "
                        f"{self.manufacturer_durable_allowance_remaining(player)}/"
                        f"{self.manufacturer_durable_allowance(player)}"
                    )
            else:
                name = output.value
                context = f"up to {option['max_qty']} now"
            price = prices.get(output)
            if price:
                context += f" · {round(price)} Dp each"
            out.append({
                "key": self.produce_option_key(option),
                "label": f"Produce {name}",
                "max_qty": option["max_qty"],
                "context": context,
            })
        return out

    @staticmethod
    def _recipe_context(player: Player, spec: dict, output: ResourceType) -> str:
        """Recipe + affordable-runs sub-line for a Manufacturer product line."""
        recipe_inputs = spec.get("inputs") or {}
        inputs_str = " + ".join(f"{need} {res}" for res, need in recipe_inputs.items())
        # Space out camelCase resource values (FarmMachinery → Farm Machinery).
        unit = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", output.value)
        context = f"{inputs_str} → {spec['qty']} {unit}" if inputs_str \
            else f"→ {spec['qty']} {unit}"
        affordable = [
            int(player.inventory.get(ResourceType(res)) // need)
            for res, need in recipe_inputs.items() if need > 0
        ]
        if affordable:
            runs = max(0, min(affordable))
            context += f" · {runs} run{'' if runs == 1 else 's'} from stock"
        return context

    def manufacturer_durable_allowance(self, player: Player) -> int:
        owned = player.effective_capital_inventory()
        bonus_items = (
            int(owned.get("manufacturer.assembly_line", 0) > 0)
            + int(owned.get("manufacturer.precision_workshop", 0) > 0)
        )
        return min(
            MANUFACTURER_DURABLE_CAP_MAX,
            MANUFACTURER_DURABLE_CAP_BASE
            + bonus_items * MANUFACTURER_DURABLE_CAP_BONUS_PER_ITEM,
        )

    def manufacturer_durable_allowance_remaining(self, player: Player) -> int:
        used = int(getattr(player, "manufacturer_durable_output_used", 0))
        return max(0, self.manufacturer_durable_allowance(player) - used)

    @staticmethod
    def reset_manufacturer_durable_allowance(player: Player) -> None:
        player.manufacturer_durable_output_used = 0

    @staticmethod
    def _manufacturer_cash_limited_qty(player: Player, product_line: str) -> int:
        spec = MANUFACTURER_PRODUCT_LINES.get(product_line, {})
        per_unit = float(spec.get("build_cost_dollops", 0.0))
        if per_unit <= 0:
            return 10**9
        return max(0, floor(player.dollops / per_unit))

    def _inputs_for_selected_output(
        self,
        player: Player,
        role_name: str,
        output: ResourceType,
        qty: int,
        preview_qty: int,
        season_name: str,
        product_line: str | None,
    ) -> dict[ResourceType, int]:
        if (
            role_name == "Farmer"
            and output.value in FARMER_SEASONAL_CONVERSION[season_name]["outputs"]
            and output not in (ResourceType.FOOD, ResourceType.MEAT)
        ):
            role = next(r for r in player.roles if r.name == role_name)
            role_player = self._role_player(player, role)
            base_inputs = self._all_inputs(role_player, season_name, product_line)
            if preview_qty <= 0 or qty <= 0:
                return {}
            ratio = min(1.0, qty / preview_qty)
            return {
                r: ceil(amount * ratio)
                for r, amount in base_inputs.items()
                if ceil(amount * ratio) > 0
            }

        recipe = recipe_for(PRODUCTION_RECIPES, role_name, output.value)
        if recipe:
            if role_name == "Farmer" and output == ResourceType.FOOD:
                fish_used = min(qty, player.inventory.get(ResourceType.FISH))
                meat_used = qty - fish_used
                inputs = {
                    ResourceType.GRAIN: qty,
                    ResourceType.PRODUCE: qty,
                }
                if fish_used:
                    inputs[ResourceType.FISH] = fish_used
                if meat_used:
                    inputs[ResourceType.MEAT] = meat_used
                return inputs
            recipe = self._adjust_recipe_for_player(recipe, player)
            recipe = adjusted_recipe_for_engineers(
                recipe, active_engineer_specialty_counts(player)
            )
            mult = player.patent_input_multiplier(recipe.output)
            return {
                ResourceType(resource): ceil(amount * mult * qty)
                for resource, amount in recipe.inputs.items()
                if ceil(amount * mult * qty) > 0
            }

        role = next(r for r in player.roles if r.name == role_name)
        role_player = self._role_player(player, role)
        base_inputs = self._all_inputs(role_player, season_name, product_line)
        if preview_qty <= 0 or qty <= 0:
            return {}
        ratio = min(1.0, qty / preview_qty)
        inputs = {
            r: ceil(amount * ratio)
            for r, amount in base_inputs.items()
            if ceil(amount * ratio) > 0
        }
        if role_name == "Manufacturer" and product_line:
            freight = self._freight_surcharge(product_line, qty)
            if freight:
                inputs[ResourceType.FREIGHT] = inputs.get(ResourceType.FREIGHT, 0) + freight
        return inputs

    def produce_product(
        self,
        player: Player,
        event_result: EventResult,
        season_name: str,
        role_name: str,
        output: ResourceType,
        qty: int,
        product_line: str | None = None,
    ) -> dict[ResourceType, int]:
        if event_result.outage or qty <= 0:
            return {}

        options = self.production_options(player, event_result, season_name)
        option = next(
            (
                opt for opt in options
                if opt["role"] == role_name
                and opt["output"] == output
                and opt["product_line"] == product_line
            ),
            None,
        )
        if option is None:
            raise InsufficientInputsError(role_name, {})
        qty = min(qty, option["max_qty"])
        build_cost = 0.0
        if role_name == "Manufacturer" and product_line:
            line = MANUFACTURER_PRODUCT_LINES.get(product_line, {})
            build_cost = round(float(line.get("build_cost_dollops", 0.0)) * qty, 2)
            if build_cost > player.dollops:
                raise InsufficientOperatingCashError(role_name, build_cost, player.dollops)
        inputs = self._inputs_for_selected_output(
            player=player,
            role_name=role_name,
            output=output,
            qty=qty,
            preview_qty=option["preview_qty"],
            season_name=season_name,
            product_line=product_line,
        )
        missing = {
            r: amount - player.inventory.get(r)
            for r, amount in inputs.items()
            if player.inventory.get(r) < amount
        }
        if missing:
            if self.telemetry is not None:
                for r in missing:
                    self.telemetry.record_starvation(r)
            raise InsufficientInputsError(role_name, missing)

        for r, amount in inputs.items():
            player.give_resources(r, amount)
            if self.telemetry is not None:
                self.telemetry.record_consumed(r, amount)
        if build_cost > 0:
            player.spend_dollops(build_cost)
        player._oil_consumed_this_year = (
            getattr(player, "_oil_consumed_this_year", 0)
            + inputs.get(ResourceType.OIL, 0)
        )
        player.receive_resources(output, qty)
        if role_name == "Manufacturer" and output.value in MANUFACTURER_DURABLE_OUTPUTS:
            player.manufacturer_durable_output_used = (
                int(getattr(player, "manufacturer_durable_output_used", 0)) + qty
            )
        if self.telemetry is not None:
            self.telemetry.record_produced(output, qty)
        player.workforce.apply_season_work()
        return {output: qty}
