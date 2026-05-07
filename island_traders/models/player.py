from __future__ import annotations
from dataclasses import dataclass, field
from .role import Role
from .resource import ResourceBundle, ResourceType
from .workforce import Workforce
from .profession import Profession
from .insurance import InsurancePolicy
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
    insurance_policies: list[InsurancePolicy] = field(default_factory=list)
    # Minimum effective workforce factor from island infrastructure.
    # Production never falls below this fraction of base output (even with
    # poor workforce coverage), representing physical plant & equipment.
    production_capacity: float = 1.0
    # Total island population (employed workforce + unskilled residents).
    # Grows each year via year_end_births().  New people are NOT automatic
    # workers — players must recruit them via the Recruit action.
    population: int = 100
    # Capital equipment owned by this player, keyed by CapitalItem.item_id.
    # Populated during the Investing Phase and via mid-game purchases.
    # See `island_traders.constants_capacity.CAPITAL_CATALOGUE`.
    capital_inventory: dict[str, int] = field(default_factory=dict)
    # Capital items purchased mid-game that are still in transit.
    # Each entry: {"item_id": str, "arrives_at_tick": int (year*4 + season_index)}.
    capital_in_transit: list[dict] = field(default_factory=list)
    # Active patents this player has bought, keyed by output resource name.
    # Each value is a list of patent records: [{"patent_id": str, "boost": float}, ...].
    # Per requirements: max 3 active patents per output, –20% input cost each.
    active_patents: dict[str, list[dict]] = field(default_factory=dict)

    def add_capital(self, item_id: str, count: int = 1) -> None:
        """Add `count` of a capital item to the inventory (e.g. on delivery)."""
        self.capital_inventory[item_id] = self.capital_inventory.get(item_id, 0) + count

    def remove_capital(self, item_id: str, count: int = 1) -> int:
        """Remove up to `count` of a capital item (e.g. destroyed by event).
        Returns the actual count removed."""
        have = self.capital_inventory.get(item_id, 0)
        n = min(have, count)
        if n > 0:
            self.capital_inventory[item_id] = have - n
            if self.capital_inventory[item_id] == 0:
                del self.capital_inventory[item_id]
        return n

    def capital_count(self, item_id: str) -> int:
        return self.capital_inventory.get(item_id, 0)

    def deliver_in_transit(self, current_tick: int) -> list[str]:
        """Move items whose arrival tick has passed into capital_inventory.
        Returns the list of delivered item_ids (for UI / log purposes)."""
        delivered: list[str] = []
        remaining: list[dict] = []
        for entry in self.capital_in_transit:
            if entry["arrives_at_tick"] <= current_tick:
                self.add_capital(entry["item_id"], 1)
                delivered.append(entry["item_id"])
            else:
                remaining.append(entry)
        self.capital_in_transit = remaining
        return delivered

    # ------------------------------------------------------------------ Patents

    PATENT_BOOST_PER_PATENT: float = 0.20    # 20 % input cost reduction
    PATENT_MAX_PER_OUTPUT:   int   = 3       # cap stack at 3

    def apply_patent(self, output_name: str) -> bool:
        """Consume 1 Patent from inventory and activate it on `output_name`.

        Returns True on success.  Returns False if no Patent in inventory or
        the per-output cap is reached.
        """
        from .resource import ResourceType
        if self.active_patent_count(output_name) >= self.PATENT_MAX_PER_OUTPUT:
            return False
        try:
            self.inventory = self.inventory.subtract(ResourceType.PATENTS, 1)
        except Exception:
            return False
        active = self.active_patents.setdefault(output_name, [])
        active.append({
            "patent_id": f"p{len(active) + 1}",
            "boost":     self.PATENT_BOOST_PER_PATENT,
        })
        return True

    def active_patent_count(self, output_name: str) -> int:
        return len(self.active_patents.get(output_name, []))

    def patent_input_multiplier(self, output_name: str) -> float:
        """Aggregate input-cost multiplier for an output.

        Each active patent contributes a (1 - PATENT_BOOST_PER_PATENT) factor.
        Capped at PATENT_MAX_PER_OUTPUT — so the floor is (1 - 3 * 0.2) = 0.4
        (60 % reduction).  Multiplicative: 0 / 0.8 / 0.64 / 0.512 if multiplied,
        but the spec calls for additive 20 % each, so we use (1 - n * 0.2).
        """
        n = min(self.active_patent_count(output_name), self.PATENT_MAX_PER_OUTPUT)
        return max(0.4, 1.0 - n * self.PATENT_BOOST_PER_PATENT)

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

    def has_active_insurance(self, policy_type: str, year: int, season_index: int) -> bool:
        return any(
            p.policy_type == policy_type and p.is_valid(year, season_index)
            for p in self.insurance_policies
        )

    def add_insurance_policy(self, policy: InsurancePolicy) -> None:
        self.insurance_policies.append(policy)

    def active_policies(self, year: int, season_index: int) -> list[InsurancePolicy]:
        return [p for p in self.insurance_policies if p.is_valid(year, season_index)]

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

    def total_wealth(self, prices: dict[ResourceType, float],
                     loan_ledger=None) -> float:
        assets = self.dollops + self.inventory.total_value(prices)
        if loan_ledger:
            assets -= loan_ledger.outstanding_debt(self.player_id)
            assets += loan_ledger.loans_receivable(self.player_id)
        return assets

    def record_year_wealth(self, prices: dict[ResourceType, float],
                           loan_ledger=None) -> None:
        self.wealth_history.append(self.total_wealth(prices, loan_ledger))

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
