from __future__ import annotations
from dataclasses import dataclass, field
from math import ceil
from .role import Role
from .resource import ResourceBundle, ResourceType
from .workforce import Workforce
from .profession import Profession
from .insurance import InsurancePolicy
from .equity import CapTable
from ..constants import (
    PRODUCTION_INPUTS, BASE_PRODUCTION, CURRENCY_SYMBOL,
    MAX_WORKFORCE_FRACTION_OF_POPULATION,
    FARMER_SEASONAL_CONVERSION, MANUFACTURER_PRODUCT_LINES,
    PEOPLE_PER_MEAL,
)


class InsufficientFundsError(Exception):
    pass


def _allocate_raw_meals(
    meals_needed: int, grain: int, produce: int, fish: int, meat: int,
) -> tuple[int, dict[ResourceType, int]]:
    """Allocate raw ingredients to satisfy ``meals_needed`` meals.

    Each meal needs one fill in each of three slots: grain, produce,
    protein (fish or meat are interchangeable for the protein slot).
    Native ingredients fill their own slot 1:1; surplus from any slot
    substitutes for a different slot at 2:1.

    Returns ``(meals_satisfied, used)`` where ``used`` is a dict of
    {GRAIN, PRODUCE, FISH, MEAT} → units consumed. Pure (no side
    effects); caller is responsible for inventory mutation.

    Algorithm — waterfill across the three slot levels:
      1. Native fill: each slot reaches ``min(native_inventory, meals_needed)``.
      2. Compute surplus pool from each slot (anything beyond what its
         own slot consumed).
      3. Sub slots available = ``floor(surplus_pool / 2)``.
      4. Distribute sub slots greedily to raise the lowest slot level
         first (bring s0 to s1, then s0+s1 to s2, then all three together).
      5. ``meals = min(slot_levels)`` capped at ``meals_needed``.
    """
    used = {
        ResourceType.GRAIN:   0,
        ResourceType.PRODUCE: 0,
        ResourceType.FISH:    0,
        ResourceType.MEAT:    0,
    }
    if meals_needed <= 0:
        return 0, used

    # Phase 1 — native fills, capped at meals_needed (no point overfilling).
    g_native       = min(grain, meals_needed)
    p_native       = min(produce, meals_needed)
    protein_have   = fish + meat
    prot_native    = min(protein_have, meals_needed)

    # Phase 2 — surplus pool for substitution.
    g_surplus      = max(0, grain - g_native)
    p_surplus      = max(0, produce - p_native)
    prot_surplus   = max(0, protein_have - prot_native)
    sub_pool_units = g_surplus + p_surplus + prot_surplus
    sub_slots      = sub_pool_units // 2   # 2 units → 1 slot fill

    # Waterfill on the three slot levels.
    levels = sorted([g_native, p_native, prot_native])  # ascending
    # Step A: bring level[0] up to level[1].
    if levels[0] < levels[1] and sub_slots > 0:
        delta = min(levels[1] - levels[0], sub_slots)
        levels[0] += delta
        sub_slots -= delta
    # Step B: bring level[0]+level[1] up to level[2] together.
    if levels[1] < levels[2] and sub_slots >= 2:
        delta = min(levels[2] - levels[1], sub_slots // 2)
        levels[0] += delta
        levels[1] += delta
        sub_slots -= delta * 2
    # Step C: raise all three together (capped at meals_needed).
    if levels[2] < meals_needed and sub_slots >= 3:
        delta = min(meals_needed - levels[2], sub_slots // 3)
        levels[0] += delta
        levels[1] += delta
        levels[2] += delta
        sub_slots -= delta * 3

    meals = min(levels[0], levels[1], levels[2], meals_needed)
    if meals <= 0:
        return 0, used

    # Phase 3 — back out per-resource deduction.  Native first, then
    # take substitutes from any remaining surplus (grain → produce →
    # protein order is arbitrary; what matters for callers is the total
    # deducted per resource).
    #
    # Native deducted per slot is min(native_used, meals).  Each slot
    # that wasn't filled natively must be filled by substitute, and
    # each substitute slot fill takes 2 inventory units (the 2:1 rule).
    g_used_native    = min(grain, meals)
    p_used_native    = min(produce, meals)
    prot_used_native = min(protein_have, meals)
    native_fills     = g_used_native + p_used_native + prot_used_native
    sub_slot_fills   = max(0, meals * 3 - native_fills)
    sub_units_used   = sub_slot_fills * 2

    used[ResourceType.GRAIN]   = g_used_native
    used[ResourceType.PRODUCE] = p_used_native
    # Split protein-native between fish and meat (fish first, then meat).
    fish_used = min(fish, prot_used_native)
    meat_used = prot_used_native - fish_used
    used[ResourceType.FISH] = fish_used
    used[ResourceType.MEAT] = meat_used

    # Distribute substitute draws across whatever has surplus.
    # Order: grain surplus → produce surplus → fish surplus → meat surplus.
    remaining_sub = sub_units_used
    for rtype, native_used in (
        (ResourceType.GRAIN,   g_used_native),
        (ResourceType.PRODUCE, p_used_native),
        (ResourceType.FISH,    fish_used),
        (ResourceType.MEAT,    meat_used),
    ):
        if remaining_sub <= 0:
            break
        inventory_of_this = {
            ResourceType.GRAIN:   grain,
            ResourceType.PRODUCE: produce,
            ResourceType.FISH:    fish,
            ResourceType.MEAT:    meat,
        }[rtype]
        available = inventory_of_this - native_used
        take = min(available, remaining_sub)
        used[rtype] += take
        remaining_sub -= take

    return meals, used


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

    # --- Equity / balance-sheet split (Phase 1, additive) ------------------
    # `dollops` (above) is the ISLAND's operating treasury.  `personal_cash`
    # is the player-as-investor's private wealth (the auction budget; the
    # winning bid is paid from here to imaginary former owners).  `holdings`
    # maps an island's player_id (as str) -> shares this investor owns in it.
    # `cap_table` records who owns THIS player's island (60/40 at auction).
    # All default empty/zero so existing games are unaffected until the
    # economy flip wires them in.  See
    # requirements/equity-balance-sheet-separation.md.
    personal_cash: float = 0.0
    holdings: dict[str, int] = field(default_factory=dict)
    cap_table: CapTable | None = None

    def net_worth(self, share_price_by_island: dict[str, float]) -> float:
        """Investor net worth = personal cash + market value of all holdings.

        `share_price_by_island` maps island player_id (str) -> price per share;
        the caller (the engine, which has the market + valuation history)
        computes those via `equity.share_price(equity.fair_value(...))`.
        """
        total = self.personal_cash
        for island_id, shares in self.holdings.items():
            total += shares * share_price_by_island.get(str(island_id), 0.0)
        return total

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

    def meals_needed(self, extra_residents: int = 0, absent_residents: int = 0) -> int:
        """Per-season meal demand for this island.

        Sustenance basket model (2026-05-25): each ``PEOPLE_PER_MEAL``
        residents (default 10) consume one "meal" per season. A meal is
        satisfied by 1 Food, OR (1 Grain + 1 Produce + 1 (Fish or Meat)).
        Substitution between raw ingredients runs at 2:1 — see
        ``consume_sustenance``. The legacy ``BASE_POPULATION_SELF_FED``
        baseline is gone; every resident counts toward demand.

        ``extra_residents`` adds transient mouths (e.g. visiting trainees
        on campus) without mutating resident population. ``absent_residents``
        removes residents who are physically away and fed by another island.
        """
        residents = (
            max(0, self.population)
            + max(0, extra_residents)
            - max(0, absent_residents)
        )
        residents = max(0, residents)
        return ceil(residents / PEOPLE_PER_MEAL) if residents > 0 else 0

    def consume_sustenance(
        self, meals_needed: int
    ) -> tuple[int, dict[ResourceType, int], int]:
        """Deduct sustenance from inventory for the given meal count.

        Consumption order:
          1. Food first (1 Food → 1 meal).
          2. Raw basket for the remainder: each meal = 1 grain slot + 1
             produce slot + 1 protein slot. Native fill is 1:1
             (grain → grain slot, produce → produce slot, fish or meat
             → protein slot). When a slot is short and another slot has
             surplus, the surplus substitutes at 2:1 (two surplus units
             cover one missing slot).

        The substitution allocator water-fills to maximize the number of
        fully-satisfied meals — partial substitution that can't complete
        a meal is wasted, so we count whole meals only.

        Mutates ``self.inventory``. Returns
        ``(meals_satisfied, ingredients_used, meals_short)`` where
        ``ingredients_used`` is a dict of {Food, Grain, Produce, Fish,
        Meat} → units actually consumed.
        """
        used = {
            ResourceType.FOOD:    0,
            ResourceType.GRAIN:   0,
            ResourceType.PRODUCE: 0,
            ResourceType.FISH:    0,
            ResourceType.MEAT:    0,
        }
        if meals_needed <= 0:
            return 0, used, 0

        # Phase 1 — eat Food first.
        food_have = self.inventory.get(ResourceType.FOOD)
        food_use = min(food_have, meals_needed)
        if food_use > 0:
            self.inventory = self.inventory.subtract(ResourceType.FOOD, food_use)
            used[ResourceType.FOOD] = food_use
        remaining = meals_needed - food_use

        if remaining > 0:
            # Phase 2 — raw allocation with substitution.
            grain   = self.inventory.get(ResourceType.GRAIN)
            produce = self.inventory.get(ResourceType.PRODUCE)
            fish    = self.inventory.get(ResourceType.FISH)
            meat    = self.inventory.get(ResourceType.MEAT)
            raw_meals, raw_used = _allocate_raw_meals(
                remaining, grain, produce, fish, meat
            )
            if raw_meals > 0:
                for rtype in (ResourceType.GRAIN, ResourceType.PRODUCE,
                              ResourceType.FISH, ResourceType.MEAT):
                    if raw_used[rtype] > 0:
                        self.inventory = self.inventory.subtract(
                            rtype, raw_used[rtype]
                        )
                used[ResourceType.GRAIN]   = raw_used[ResourceType.GRAIN]
                used[ResourceType.PRODUCE] = raw_used[ResourceType.PRODUCE]
                used[ResourceType.FISH]    = raw_used[ResourceType.FISH]
                used[ResourceType.MEAT]    = raw_used[ResourceType.MEAT]
        else:
            raw_meals = 0

        satisfied = food_use + raw_meals
        shortfall = max(0, meals_needed - satisfied)
        return satisfied, used, shortfall

    def meals_available(self) -> int:
        """Total meals current inventory could satisfy (pure peek; no
        mutation).  Used by UI / server alerts to compute sustenance
        runway without committing to a particular consumption order.

        Counts Food at 1:1 plus raw allocation under the substitution
        rules at an effectively-unbounded meal target so we measure the
        ceiling.
        """
        food = self.inventory.get(ResourceType.FOOD)
        grain = self.inventory.get(ResourceType.GRAIN)
        produce = self.inventory.get(ResourceType.PRODUCE)
        fish = self.inventory.get(ResourceType.FISH)
        meat = self.inventory.get(ResourceType.MEAT)
        # Cap meal target at (food + total raw) — the absolute upper
        # bound is "every unit of food + every unit of raw at best-case
        # 1:1" so we can't exceed food + sum_raw meals.
        raw_total = grain + produce + fish + meat
        ceiling = food + raw_total
        if ceiling <= 0:
            return 0
        raw_meals, _ = _allocate_raw_meals(ceiling, grain, produce, fish, meat)
        return food + raw_meals

    def sustenance_shortfall_demand(
        self, extra_residents: int = 0
    ) -> dict[ResourceType, int]:
        """Market demand basket for unmet sustenance, post-consumption.

        Call AFTER ``consume_sustenance``: posts each component of the
        basket (Food, Grain, Produce, Fish, Meat) at the shortfall-meal
        level so AI sellers see the full demand surface. The basket
        intentionally overcounts in absolute units — it's a signal, and
        price elasticity sorts out which seller fills which need.
        """
        meals = self.meals_needed(extra_residents=extra_residents)
        # Recompute satisfaction WITHOUT mutating inventory — we already
        # mutated during consume_sustenance; this method is for
        # post-consumption posting where consume already ran.
        # If the engine calls consume first, the inventory reflects the
        # post-consumption state, so meals_needed minus what we just had
        # is the shortfall. But this method is also useful as a
        # standalone "what would the market basket be?" check, so we
        # peek at current inventory.
        food = self.inventory.get(ResourceType.FOOD)
        if food >= meals:
            return {}
        remaining = meals - food
        grain   = self.inventory.get(ResourceType.GRAIN)
        produce = self.inventory.get(ResourceType.PRODUCE)
        fish    = self.inventory.get(ResourceType.FISH)
        meat    = self.inventory.get(ResourceType.MEAT)
        raw_meals, _ = _allocate_raw_meals(remaining, grain, produce, fish, meat)
        shortfall = remaining - raw_meals
        if shortfall <= 0:
            return {}
        return {
            ResourceType.FOOD:    shortfall,
            ResourceType.GRAIN:   shortfall,
            ResourceType.PRODUCE: shortfall,
            ResourceType.FISH:    shortfall,
            ResourceType.MEAT:    shortfall,
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
