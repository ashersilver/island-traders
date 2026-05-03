from __future__ import annotations
from dataclasses import dataclass, field
from .role import Role
from .resource import ResourceBundle, ResourceType
from .workforce import Workforce
from .profession import Profession
from ..constants import (
    PRODUCTION_INPUTS, BASE_PRODUCTION, CURRENCY_SYMBOL, UNSKILLED_RECRUITMENT_RATIO,
    FARMER_SEASONAL_CONVERSION, MANUFACTURER_PRODUCT_LINES,
)


class InsufficientFundsError(Exception):
    pass


@dataclass
class Player:
    player_id: int
    name: str
    roles: list[Role]
    dollops: float
    inventory: ResourceBundle = field(default_factory=ResourceBundle)
    workforce: Workforce = field(default_factory=Workforce)
    is_human: bool = True
    wealth_history: list[float] = field(default_factory=list)
    # Minimum effective workforce factor from island infrastructure.
    # Production never falls below this fraction of base output (even with
    # poor workforce coverage), representing physical plant & equipment.
    production_capacity: float = 1.0
    # Total island population (employed workforce + unskilled residents).
    # Grows each year via year_end_births().  New people are NOT automatic
    # workers — players must recruit them via the Recruit action.
    population: int = 100

    @property
    def available_unskilled(self) -> int:
        """How many unskilled residents can be recruited as workers right now.
        Based on the 1-per-2-unskilled-residents rule."""
        non_workers = max(0, self.population - self.workforce.count)
        return int(non_workers * UNSKILLED_RECRUITMENT_RATIO)

    def recruit_workers(self, count: int) -> int:
        """Draw up to count unskilled workers from the island population.
        Returns actual number recruited (may be less if pool is smaller)."""
        can_recruit = min(count, self.available_unskilled)
        if can_recruit > 0:
            self.workforce.add_workers(can_recruit, training_level=0,
                                       profession=Profession.UNSKILLED.value)
        return can_recruit

    def all_produced_resources(self) -> list[ResourceType]:
        seen: set[ResourceType] = set()
        result = []
        for role in self.roles:
            for r in role.produces:
                if r not in seen:
                    seen.add(r)
                    result.append(r)
        return result

    def all_required_inputs(
        self, season: str = "Spring", product_line: str | None = None
    ) -> dict[ResourceType, int]:
        totals: dict[ResourceType, int] = {}
        for role in self.roles:
            if role.name == "Farmer":
                raw = FARMER_SEASONAL_CONVERSION[season]["inputs"]
            elif role.name == "Manufacturer":
                line_key = (
                    product_line
                    if product_line and product_line in MANUFACTURER_PRODUCT_LINES
                    else next(iter(MANUFACTURER_PRODUCT_LINES))
                )
                raw = MANUFACTURER_PRODUCT_LINES[line_key]["inputs"]
            else:
                raw = PRODUCTION_INPUTS.get(role.name, {})
            for r_str, qty in raw.items():
                r = ResourceType(r_str)
                totals[r] = totals.get(r, 0) + qty
        return totals

    def has_resources(self, requirements: dict[ResourceType, int]) -> bool:
        return self.inventory.can_satisfy(requirements)

    def give_resources(self, rtype: ResourceType, qty: int) -> None:
        self.inventory = self.inventory.subtract(rtype, qty)

    def receive_resources(self, rtype: ResourceType, qty: int) -> None:
        self.inventory = self.inventory.add(rtype, qty)

    def spend_dollops(self, amount: float) -> None:
        if self.dollops < amount:
            raise InsufficientFundsError(
                f"{self.name} has {self.dollops:.2f} {CURRENCY_SYMBOL} but needs {amount:.2f}"
            )
        self.dollops -= amount

    def receive_dollops(self, amount: float) -> None:
        self.dollops += amount

    def total_wealth(self, prices: dict[ResourceType, float]) -> float:
        return self.dollops + self.inventory.total_value(prices)

    def record_year_wealth(self, prices: dict[ResourceType, float]) -> None:
        self.wealth_history.append(self.total_wealth(prices))

    def role_names(self) -> str:
        return ", ".join(r.name for r in self.roles)

    def inventory_report(self, prices: dict[ResourceType, float]) -> str:
        sym = CURRENCY_SYMBOL
        lines = [
            f"=== INVENTORY: {self.name} ({self.role_names()}) ===",
            f"Dollops: {self.dollops:.1f} {sym}",
            "",
            "Resources:",
        ]
        total_res_value = 0.0
        for r in ResourceType:
            qty = self.inventory.get(r)
            if qty > 0:
                price = prices.get(r, 0.0)
                val = qty * price
                total_res_value += val
                lines.append(
                    f"  {r.value:<18} {qty:>4} units  @ {price:>7.2f} {sym} = {val:>9.2f} {sym}"
                )
        if total_res_value == 0.0:
            lines.append("  (none)")
        lines.append("")

        ws = self.workforce.summary()
        lines.append(
            f"Population: {self.population}  "
            f"(employed: {ws['total']}  |  "
            f"recruitable unskilled: {self.available_unskilled})"
        )
        lines.append(
            f"Workforce: {ws['active']}/{ws['total']} active  "
            f"(avg efficiency: {ws['avg_efficiency_pct']}%  |  "
            f"base capacity: {self.production_capacity*100:.0f}%)"
        )
        if ws["by_tier"]:
            for k, v in ws["by_tier"].items():
                lines.append(f"  {k:<32} × {v}")
        lines.append("")
        lines.append(f"Total Wealth: {self.total_wealth(prices):.1f} {sym}")
        return "\n".join(lines)

    def __repr__(self) -> str:
        return (
            f"Player({self.name!r}, roles=[{self.role_names()}], "
            f"dollops={self.dollops:.1f})"
        )
