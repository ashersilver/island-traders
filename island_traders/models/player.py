from __future__ import annotations
from dataclasses import dataclass, field
from math import ceil
from .role import Role
from .resource import ResourceBundle, ResourceType
from .workforce import Workforce
from .profession import Profession
from .insurance import InsurancePolicy
from ..constants import (
    PRODUCTION_INPUTS, BASE_PRODUCTION, CURRENCY_SYMBOL,
    MAX_WORKFORCE_FRACTION_OF_POPULATION,
    FARMER_SEASONAL_CONVERSION, MANUFACTURER_PRODUCT_LINES, BASE_POPULATION_SELF_FED,
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
    # Acquisition ticks for owned capital, keyed by item_id. Tick = year*4 + season.
    # Used for straight-line book value depreciation over 5 years.
    capital_acquired_ticks: dict[str, list[int]] = field(default_factory=dict)
    # Capital items purchased mid-game that are still in transit.
    # Each entry: {"item_id": str, "arrives_at_tick": int (year*4 + season_index)}.
    capital_in_transit: list[dict] = field(default_factory=list)
    # Transient per-season flag (Phase C capital lifecycle): item_id ->
    # number of units the player couldn't pay maintenance for this season.
    # Unmaintained units contribute 0 capacity until paid; reset by the
    # next season's maintenance step.  Not persisted in save files.
    unmaintained_capital: dict[str, int] = field(default_factory=dict)
    # Active patents this player has bought, keyed by output resource name.
    # Each value is a list of patent records: [{"patent_id": str, "boost": float}, ...].
    # Per requirements: max 3 active patents per output, –20% input cost each.
    active_patents: dict[str, list[dict]] = field(default_factory=dict)

    def effective_capital_inventory(self) -> dict[str, int]:
        """Capital available for production this season.

        Identical to ``capital_inventory`` minus this season's
        ``unmaintained_capital`` counts — unmaintained units contribute
        zero capacity until paid (Phase C capital lifecycle).
        """
        if not self.unmaintained_capital:
            return self.capital_inventory
        return {
            item_id: max(0, count - self.unmaintained_capital.get(item_id, 0))
            for item_id, count in self.capital_inventory.items()
        }

    def add_capital(self, item_id: str, count: int = 1, acquired_tick: int = 0) -> None:
        """Add `count` of a capital item to the inventory (e.g. on delivery)."""
        self.capital_inventory[item_id] = self.capital_inventory.get(item_id, 0) + count
        ticks = self.capital_acquired_ticks.setdefault(item_id, [])
        ticks.extend([acquired_tick] * count)

    def remove_capital(self, item_id: str, count: int = 1) -> int:
        """Remove up to `count` of a capital item (e.g. destroyed by event).
        Returns the actual count removed."""
        have = self.capital_inventory.get(item_id, 0)
        n = min(have, count)
        if n > 0:
            self.capital_inventory[item_id] = have - n
            ticks = self.capital_acquired_ticks.get(item_id, [])
            if ticks:
                del ticks[:n]
                if not ticks:
                    self.capital_acquired_ticks.pop(item_id, None)
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
                self.add_capital(entry["item_id"], 1, acquired_tick=current_tick)
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

        Hard cap: the total workforce (skilled + unskilled) is bounded
        to MAX_WORKFORCE_FRACTION_OF_POPULATION × current population.
        Available recruits = cap − current workforce, floored at 0.
        Recruits are drawn from residents, so the cap also protects the
        non-worker resident pool from being fully employed.
        """
        cap = int(self.population * MAX_WORKFORCE_FRACTION_OF_POPULATION)
        return max(0, cap - self.workforce.count)

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

    def cancel_insurance_policy(
        self, policy_id: int, year: int, season_index: int
    ) -> float:
        """Cancel an active insurance policy (Issue #5).

        Returns the pro-rata refund amount that should be credited to the
        policy holder.  Caller is responsible for the cash transfer between
        Banker and holder.  Returns 0.0 if the policy is unknown, already
        inactive, or already expired.
        """
        policy = next(
            (p for p in self.insurance_policies if p.policy_id == policy_id), None
        )
        if policy is None or not policy.active:
            return 0.0
        refund = policy.cancel_refund(year, season_index)
        policy.active = False
        return refund

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

    def population_food_fish_needs(
        self, extra_residents: int = 0
    ) -> dict[ResourceType, int]:
        """Seasonal sustenance demand.

        The first ``BASE_POPULATION_SELF_FED`` permanent residents are assumed
        to be fed locally and generate no marginal market Food demand.
        ``extra_residents`` adds transient mouths, such as visiting trainees,
        without mutating resident population; they always count as marginal
        demand above the self-fed baseline.
        """
        population = max(0, self.population)
        transient_residents = max(0, extra_residents)
        marginal_food_residents = max(0, population - BASE_POPULATION_SELF_FED)
        bands = self.workforce.band_summary()
        educated_workers = bands.get("Manager", 0) + bands.get("Technician", 0)
        food = marginal_food_residents + transient_residents
        fish = ceil(population / 100) + ceil(educated_workers / 8)
        return {
            ResourceType.FOOD: food,
            ResourceType.FISH: max(0, fish),
        }

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
                     loan_ledger=None, capital_catalogue=None,
                     current_tick: int = 0) -> float:
        assets = self.dollops + self.inventory.total_value(prices)
        assets += self.capital_book_value(capital_catalogue, current_tick)
        if loan_ledger:
            assets -= loan_ledger.outstanding_debt(self.player_id)
            assets += loan_ledger.loans_receivable(self.player_id)
        return assets

    def capital_book_value(self, capital_catalogue=None, current_tick: int = 0) -> float:
        if not capital_catalogue:
            return 0.0
        items = {item.item_id: item for item in capital_catalogue}
        depreciation_ticks = 5 * 4
        total = 0.0
        for item_id, count in self.capital_inventory.items():
            item = items.get(item_id)
            if not item:
                continue
            ticks = list(self.capital_acquired_ticks.get(item_id, []))
            if len(ticks) < count:
                ticks.extend([0] * (count - len(ticks)))
            for acquired_tick in ticks[:count]:
                age = max(0, current_tick - acquired_tick)
                remaining = max(0.0, (depreciation_ticks - age) / depreciation_ticks)
                total += item.cost * remaining
        return round(total, 2)

    def record_year_wealth(self, prices: dict[ResourceType, float],
                           loan_ledger=None, capital_catalogue=None,
                           current_tick: int = 0) -> None:
        self.wealth_history.append(
            self.total_wealth(prices, loan_ledger, capital_catalogue, current_tick)
        )

    def role_names(self) -> str:
        return ", ".join(getattr(r, "display_name", r.name) for r in self.roles)

    def role_keys(self) -> list[str]:
        return [r.name for r in self.roles]

    def inventory_report(self, prices: dict[ResourceType, float], loan_ledger=None,
                         capital_catalogue=None, current_tick: int = 0) -> str:
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
        equipment_value = self.capital_book_value(capital_catalogue, current_tick)
        if equipment_value:
            lines.append(f"Equipment Book Value: {equipment_value:.1f} {sym}")
        lines.append(
            f"Net Wealth: "
            f"{self.total_wealth(prices, loan_ledger, capital_catalogue, current_tick):.1f} {sym}"
        )
        return "\n".join(lines)

    def __repr__(self) -> str:
        return (
            f"Player({self.name!r}, roles=[{self.role_names()}], "
            f"dollops={self.dollops:.1f})"
        )
