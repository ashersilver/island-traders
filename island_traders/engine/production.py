from __future__ import annotations
from ..models.player import Player
from ..models.resource import ResourceType
from ..engine.events import EventResult
from ..constants import (
    BASE_PRODUCTION, PRODUCTION_INPUTS, SEASONAL_WORKFORCE,
    SEASONAL_YIELD, FARMER_SEASONAL_CONVERSION,
    LABOUR_REQUIREMENTS, SKILLED_PROFESSIONS,
)


class InsufficientInputsError(Exception):
    def __init__(self, role: str, missing: dict[ResourceType, int]):
        self.role = role
        self.missing = missing
        parts = ", ".join(f"{qty}x {r.value}" for r, qty in missing.items())
        super().__init__(f"{role} cannot produce: missing {parts}")


class ProductionEngine:
    def _seasonal_workforce_required(self, player: Player, season_name: str) -> int:
        total = 0
        for role in player.roles:
            total += SEASONAL_WORKFORCE.get(role.name, {}).get(season_name, 0)
        return total

    def _seasonal_labour_requirements(self, role_name: str, season_name: str) -> tuple[int, int]:
        """Return (required_skilled, required_unskilled) scaled for the current season.

        Scales the baseline LABOUR_REQUIREMENTS by the ratio of seasonal to baseline
        total so that peak seasons demand more of both tiers proportionally.
        """
        base = LABOUR_REQUIREMENTS.get(role_name, {"skilled": 0, "unskilled": 0})
        base_total = base["skilled"] + base["unskilled"]
        seasonal_total = SEASONAL_WORKFORCE.get(role_name, {}).get(season_name, base_total)
        if base_total <= 0:
            return 0, 0
        scale = seasonal_total / base_total
        skilled = max(1, round(base["skilled"] * scale))
        unskilled = max(0, round(base["unskilled"] * scale))
        return skilled, unskilled

    def _labour_productivity_factor(self, player: Player, season_name: str) -> float:
        """Weighted skilled+unskilled productivity factor across all of a player's roles."""
        total_skilled = 0
        total_unskilled = 0
        all_skilled_profs: set[str] = set()
        for role in player.roles:
            s, u = self._seasonal_labour_requirements(role.name, season_name)
            total_skilled += s
            total_unskilled += u
            all_skilled_profs.update(SKILLED_PROFESSIONS.get(role.name, []))
        return player.workforce.labour_productivity_factor(
            total_skilled, total_unskilled, list(all_skilled_profs)
        )

    def _role_inputs(self, role_name: str, season_name: str) -> dict[ResourceType, int]:
        """Return inputs for a role this season (Farmer uses seasonal table)."""
        if role_name == "Farmer":
            raw = FARMER_SEASONAL_CONVERSION[season_name]["inputs"]
        else:
            raw = PRODUCTION_INPUTS.get(role_name, {})
        return {ResourceType(k): v for k, v in raw.items()}

    def _role_outputs(self, role_name: str, season_name: str) -> dict[ResourceType, int]:
        """Return base outputs for a role this season (Farmer uses seasonal table)."""
        if role_name == "Farmer":
            raw = FARMER_SEASONAL_CONVERSION[season_name]["outputs"]
        else:
            raw = BASE_PRODUCTION.get(role_name, {})
        return {ResourceType(k): v for k, v in raw.items()}

    def _seasonal_yield(self, role_name: str, season_name: str) -> float:
        """Seasonal base-yield multiplier (1.0 for Farmer — table already encodes it)."""
        if role_name == "Farmer":
            return 1.0
        return SEASONAL_YIELD.get(role_name, {}).get(season_name, 1.0)

    def _all_inputs(self, player: Player, season_name: str) -> dict[ResourceType, int]:
        totals: dict[ResourceType, int] = {}
        for role in player.roles:
            for r, qty in self._role_inputs(role.name, season_name).items():
                totals[r] = totals.get(r, 0) + qty
        return totals

    def can_produce(
        self, player: Player, event_result: EventResult, season_name: str = "Spring"
    ) -> tuple[bool, dict[ResourceType, int]]:
        if event_result.outage:
            return False, {}
        inputs = self._all_inputs(player, season_name)
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
    ) -> dict[ResourceType, int]:
        if event_result.outage:
            return {}

        inputs = self._all_inputs(player, season_name)
        missing = {r: qty for r, qty in inputs.items() if player.inventory.get(r) < qty}
        if missing:
            raise InsufficientInputsError(player.role_names(), missing)

        for r, qty in inputs.items():
            player.give_resources(r, qty)

        workforce_factor = self._labour_productivity_factor(player, season_name)
        effective_factor = max(player.production_capacity, workforce_factor)

        produced: dict[ResourceType, int] = {}
        for role in player.roles:
            sy = self._seasonal_yield(role.name, season_name)
            for r, base_qty in self._role_outputs(role.name, season_name).items():
                qty = max(0, int(base_qty * sy * event_result.yield_modifier * effective_factor))
                qty += event_result.productivity_bonus
                if qty > 0:
                    player.receive_resources(r, qty)
                    produced[r] = produced.get(r, 0) + qty

        player.workforce.apply_season_work()
        return produced

    def production_preview(
        self,
        player: Player,
        event_result: EventResult,
        season_name: str = "Spring",
    ) -> dict:
        if event_result.outage:
            return {"outage": True, "reason": event_result.event_name, "inputs": {}, "outputs": {}}

        inputs = self._all_inputs(player, season_name)
        can, missing = self.can_produce(player, event_result, season_name)

        # Aggregate labour requirements across all roles
        total_skilled_req = 0
        total_unskilled_req = 0
        all_skilled_profs: set[str] = set()
        for role in player.roles:
            s, u = self._seasonal_labour_requirements(role.name, season_name)
            total_skilled_req += s
            total_unskilled_req += u
            all_skilled_profs.update(SKILLED_PROFESSIONS.get(role.name, []))
        skilled_profs_list = list(all_skilled_profs)

        skilled_active = len([w for w in player.workforce.active_workers if w.profession in skilled_profs_list])
        unskilled_active = len([w for w in player.workforce.active_workers if w.profession not in skilled_profs_list])

        workforce_factor = player.workforce.labour_productivity_factor(
            total_skilled_req, total_unskilled_req, skilled_profs_list
        )
        effective_factor = max(player.production_capacity, workforce_factor)
        fill_pct = round(player.workforce.workforce_fill_rate(
            self._seasonal_workforce_required(player, season_name)
        ) * 100)
        eff_pct = round(player.workforce.average_efficiency * 100)

        outputs: dict[ResourceType, int] = {}
        for role in player.roles:
            sy = self._seasonal_yield(role.name, season_name)
            for r, base_qty in self._role_outputs(role.name, season_name).items():
                qty = max(0, int(base_qty * sy * event_result.yield_modifier * effective_factor))
                qty += event_result.productivity_bonus
                if qty > 0:
                    outputs[r] = outputs.get(r, 0) + qty

        return {
            "outage": False,
            "can_produce": can,
            "missing_inputs": missing,
            "inputs_consumed": inputs,
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
