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
    PEOPLE_PER_MEAL, EQUIPMENT_MAINTENANCE_CONTRACT_PER_100,
)


class InsufficientFundsError(Exception):
    pass


EQUIPMENT_RESOURCE_CAPITAL: dict[ResourceType, tuple[str, str]] = {
    ResourceType.FARM_MACHINERY: ("Farmer", "farmer.tractor"),
    ResourceType.MINING_EQUIPMENT: ("Miner", "miner.excavator"),
}


@dataclass
class CapitalUnit:
    """A single owned capital item, tracked individually (#185 / #188).

    Conditions chosen at purchase are stored per unit so failure, repair and
    pricing can vary by what the buyer ordered.  ``purchase_value`` is the list
    price paid and is the intended basis for warranty premiums and the repair
    fee.  Phase 2 introduces the record with behaviour-preserving defaults; the
    order-time conditions and ``purchase_value`` are populated by the order /
    delivery flow in later phases, so until then the engine still prices off
    the catalogue ``CapitalItem.cost``.
    """
    item_id: str
    acquired_tick: int = 0
    unit_id: int = 0
    purchase_value: float = 0.0
    # --- conditions captured at purchase (the #185 order form) ---
    maintenance_term_years: int = 0
    predictive_maintenance: bool = False
    guarantee_seasons: int = 1            # resolved #185 decision: 1 season, no charge
    warranty: bool = False
    spares_attached: int = 0
    expedited_eligible: bool = False
    # --- runtime state ---
    status: str = "in_service"            # in_service | failed
    repair_completes_at_tick: int | None = None

    def to_dict(self) -> dict:
        return {
            "item_id": self.item_id,
            "acquired_tick": self.acquired_tick,
            "unit_id": self.unit_id,
            "purchase_value": self.purchase_value,
            "maintenance_term_years": self.maintenance_term_years,
            "predictive_maintenance": self.predictive_maintenance,
            "guarantee_seasons": self.guarantee_seasons,
            "warranty": self.warranty,
            "spares_attached": self.spares_attached,
            "expedited_eligible": self.expedited_eligible,
            "status": self.status,
            "repair_completes_at_tick": self.repair_completes_at_tick,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "CapitalUnit":
        return cls(
            item_id=str(raw.get("item_id", "")),
            acquired_tick=int(raw.get("acquired_tick", 0)),
            unit_id=int(raw.get("unit_id", 0)),
            purchase_value=float(raw.get("purchase_value", 0.0)),
            maintenance_term_years=int(raw.get("maintenance_term_years", 0)),
            predictive_maintenance=bool(raw.get("predictive_maintenance", False)),
            guarantee_seasons=int(raw.get("guarantee_seasons", 1)),
            warranty=bool(raw.get("warranty", False)),
            spares_attached=int(raw.get("spares_attached", 0)),
            expedited_eligible=bool(raw.get("expedited_eligible", False)),
            status=str(raw.get("status", "in_service")),
            repair_completes_at_tick=raw.get("repair_completes_at_tick"),
        )


def capital_unit_from_order(
    item_id: str, order: dict | None, acquired_tick: int, unit_id: int = 0,
) -> CapitalUnit:
    """Build a CapitalUnit carrying the #185 order-form conditions.

    ``order`` is the order payload captured at purchase (see
    ``Player.place_capital_order``); the form's ``spares_kits`` count maps to
    the unit's ``spares_attached``.  Missing keys fall back to the same
    defaults as a plain purchase (guarantee 1 season, no maintenance/warranty).
    """
    order = order or {}
    return CapitalUnit(
        item_id=item_id,
        acquired_tick=acquired_tick,
        unit_id=unit_id,
        purchase_value=float(order.get("purchase_value", 0.0)),
        maintenance_term_years=int(order.get("maintenance_term_years", 0)),
        predictive_maintenance=bool(order.get("predictive_maintenance", False)),
        guarantee_seasons=int(order.get("guarantee_seasons", 1)),
        warranty=bool(order.get("warranty", False)),
        spares_attached=int(order.get("spares_kits", order.get("spares_attached", 0))),
        expedited_eligible=bool(order.get("expedited_eligible", False)),
    )


def maintenance_contract_cost(
    purchase_value: float, term_years: int, predictive: bool,
) -> float:
    """Upfront #188 maintenance/warranty contract cost for one unit.

    Looks up the per-$100 term price (baseline vs Predictive Maintenance) and
    scales it to ``purchase_value``.  Returns 0.0 for no/invalid term.
    """
    rate = EQUIPMENT_MAINTENANCE_CONTRACT_PER_100.get(int(term_years))
    if rate is None or purchase_value <= 0:
        return 0.0
    per_100 = rate[1] if predictive else rate[0]
    return round(per_100 * purchase_value / 100.0, 2)


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
    # Resident household spending pool. Payroll flows here from the island
    # treasury, then households spend it on end products.
    household_cash: float = 0.0
    # Capital equipment owned by this player, tracked as individual units
    # (#185 / #188): CapitalItem.item_id -> list[CapitalUnit].  This is the
    # source of truth; `capital_inventory`, `capital_acquired_ticks`,
    # `capital_warranties` and `failed_capital` are derived read-only views
    # (below) for the many count-based readers.  Populated during the Investing
    # Phase and via mid-game purchases.  See
    # `island_traders.constants_capacity.CAPITAL_CATALOGUE`.
    capital_units: dict[str, list[CapitalUnit]] = field(default_factory=dict)
    # Capital items purchased mid-game that are still in transit.
    # Each entry: {"item_id": str, "arrives_at_tick": int (year*4 + season_index)}.
    capital_in_transit: list[dict] = field(default_factory=list)
    # Transient per-season flag (Phase C capital lifecycle): item_id ->
    # number of units the player couldn't pay maintenance for this season.
    # Unmaintained units contribute 0 capacity until paid; reset by the
    # next season's maintenance step.  Not persisted in save files.
    unmaintained_capital: dict[str, int] = field(default_factory=dict)
    # Paid ship repairs that complete on a future tick.  Each entry:
    # {"item_id": str, "count": int, "completes_at_tick": int}.
    capital_repair_in_progress: list[dict] = field(default_factory=list)
    # Active patents this player has bought, keyed by output resource name.
    # Each value is a list of patent records: [{"patent_id": str, "boost": float}, ...].
    # Per requirements: max 3 active patents per output, –20% input cost each.
    active_patents: dict[str, list[dict]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._season_revenue = 0.0
        self._season_costs = 0.0
        self._pl_history = []
        self._oil_consumed_this_year = 0
        self._food_demanded_this_year = 0
        self._food_bought_this_year = 0
        self._health_demanded_this_year = 0
        self._health_bought_this_year = 0
        self._qol_score = 0.0
        self._food_coverage = 0.0
        self._health_coverage = 0.0
        self._pollution_index = 0.0
        self._qol_observed_years = 0
        # Monotonic id source for CapitalUnit.unit_id (per player); start above
        # any ids already present (e.g. when loaded from a save).
        self._capital_unit_seq = max(
            (u.unit_id for units in self.capital_units.values() for u in units),
            default=0,
        )

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
    # Shareholder loans owed by THIS island back to investors who lent it
    # personal cash (Phase 2b): lender_player_id (str) -> principal owed.
    # A senior liability: subtracted in total_wealth/liquidation value, and the
    # matching receivable is added to the lender's net worth, so lending is
    # net-worth-neutral.  See models/shareholder_loans.py.
    shareholder_loans: dict[str, float] = field(default_factory=dict)

    def net_worth(
        self,
        share_price_by_island: dict[str, float],
        loan_receivable: float = 0.0,
    ) -> float:
        """Investor net worth = personal cash + holdings value + loan receivable.

        `share_price_by_island` maps island player_id (str) -> price per share;
        the caller (the engine, which has the market + valuation history)
        computes those via `equity.share_price(equity.fair_value(...))`.
        `loan_receivable` is the total shareholder-loan principal owed *to* this
        investor across all islands (the engine sums it via
        `shareholder_loans.receivable(...)`), making a loan net-worth-neutral.
        """
        total = self.personal_cash + loan_receivable
        for island_id, shares in self.holdings.items():
            total += shares * share_price_by_island.get(str(island_id), 0.0)
        return total

    # ----- derived count/tick views over the per-unit source of truth -----

    @property
    def capital_inventory(self) -> dict[str, int]:
        """Owned-unit count per item_id (derived from ``capital_units``)."""
        return {
            item_id: len(units)
            for item_id, units in self.capital_units.items()
            if units
        }

    @capital_inventory.setter
    def capital_inventory(self, value: dict[str, int]) -> None:
        """Rebuild units from a {item_id: count} map (bulk seeding / tests).

        Conditions reset to defaults and acquisition tick 0; callers needing
        ages or order conditions should use ``add_capital`` instead.
        """
        self.capital_units = {}
        for item_id, count in value.items():
            if count > 0:
                self.add_capital(item_id, int(count))

    @property
    def capital_acquired_ticks(self) -> dict[str, list[int]]:
        """Acquisition ticks per item_id, in unit (oldest-first) order."""
        return {
            item_id: [u.acquired_tick for u in units]
            for item_id, units in self.capital_units.items()
            if units
        }

    @property
    def capital_warranties(self) -> dict[str, int]:
        """Warranted-unit count per item_id."""
        out: dict[str, int] = {}
        for item_id, units in self.capital_units.items():
            n = sum(1 for u in units if u.warranty)
            if n:
                out[item_id] = n
        return out

    @property
    def failed_capital(self) -> dict[str, int]:
        """Failed-unit count per item_id (down until repaired)."""
        out: dict[str, int] = {}
        for item_id, units in self.capital_units.items():
            n = sum(1 for u in units if u.status == "failed")
            if n:
                out[item_id] = n
        return out

    def effective_capital_inventory(self) -> dict[str, int]:
        """Capital available for production this season.

        In-service (non-failed) units minus this season's
        ``unmaintained_capital`` counts — failed and unmaintained units
        contribute zero capacity until repaired/paid (Phase C lifecycle).
        """
        result: dict[str, int] = {}
        for item_id, units in self.capital_units.items():
            in_service = sum(1 for u in units if u.status == "in_service")
            n = in_service - self.unmaintained_capital.get(item_id, 0)
            if n > 0:
                result[item_id] = n
        return result

    def spares_capacity(self) -> int:
        """Total generic-spares storage from maintained warehouse capital."""
        from ..constants_capacity import CAPITAL_CATALOGUE
        from .capacity import find_item

        capacity = 0
        for item_id, count in self.effective_capital_inventory().items():
            item = find_item(CAPITAL_CATALOGUE, item_id)
            if not item:
                continue
            capacity += int(item.effects.get("spares_storage", 0)) * count
        return capacity

    def add_capital(
        self,
        item_id: str,
        count: int = 1,
        acquired_tick: int = 0,
        units: list[CapitalUnit] | None = None,
    ) -> None:
        """Add capital units (e.g. on delivery).

        Pass pre-built ``units`` (carrying order-time conditions) to attach
        them directly; otherwise ``count`` plain units are created at
        ``acquired_tick`` with default conditions.
        """
        lst = self.capital_units.setdefault(item_id, [])
        if units is not None:
            for u in units:
                self._capital_unit_seq += 1
                if not u.unit_id:
                    u.unit_id = self._capital_unit_seq
                lst.append(u)
            return
        for _ in range(count):
            self._capital_unit_seq += 1
            lst.append(CapitalUnit(
                item_id=item_id,
                acquired_tick=acquired_tick,
                unit_id=self._capital_unit_seq,
            ))

    def add_capital_warranty(self, item_id: str, count: int = 1) -> int:
        """Warranty up to ``count`` owned, unwarranted units of ``item_id``."""
        added = 0
        for u in self.capital_units.get(item_id, []):
            if added >= count:
                break
            if not u.warranty:
                u.warranty = True
                added += 1
        return added

    def mark_capital_failed(self, item_id: str, count: int = 1) -> int:
        """Mark up to ``count`` in-service units down for repair."""
        marked = 0
        for u in self.capital_units.get(item_id, []):
            if marked >= count:
                break
            if u.status == "in_service":
                u.status = "failed"
                marked += 1
        return marked

    def complete_capital_repair(self, item_id: str, count: int = 1) -> int:
        """Return up to ``count`` failed units of ``item_id`` to service."""
        repaired = 0
        for u in self.capital_units.get(item_id, []):
            if repaired >= count:
                break
            if u.status == "failed":
                u.status = "in_service"
                u.repair_completes_at_tick = None
                repaired += 1
        return repaired

    def remove_capital(self, item_id: str, count: int = 1) -> int:
        """Remove up to `count` of a capital item, oldest first (e.g.
        expiry or destroyed by event).  Returns the actual count removed."""
        units = self.capital_units.get(item_id, [])
        n = min(len(units), count)
        if n > 0:
            del units[:n]
            if not units:
                self.capital_units.pop(item_id, None)
        return n

    def capital_count(self, item_id: str) -> int:
        return self.capital_inventory.get(item_id, 0)

    def place_capital_order(
        self,
        item_id: str,
        order: dict | None,
        current_tick: int,
        delivery_seasons: int,
    ) -> int:
        """Place a capital order (#185), delivering now or after the build time.

        ``order`` carries the chosen order-form conditions (see
        ``capital_unit_from_order``); pass ``None`` for a plain purchase.  When
        ``delivery_seasons`` is positive the order rides on ``capital_in_transit``
        and ``deliver_in_transit`` materialises the unit on arrival.  Returns the
        tick the equipment is/was delivered.
        """
        if delivery_seasons <= 0:
            if order:
                self.add_capital(item_id, units=[
                    capital_unit_from_order(item_id, order, current_tick)
                ])
            else:
                self.add_capital(item_id, 1, acquired_tick=current_tick)
            return current_tick
        arrives_at = current_tick + delivery_seasons
        entry: dict = {"item_id": item_id, "arrives_at_tick": arrives_at}
        if order:
            entry["order"] = dict(order)
        self.capital_in_transit.append(entry)
        return arrives_at

    def deliver_in_transit(self, current_tick: int) -> list[str]:
        """Move items whose arrival tick has passed into capital_inventory.
        Returns the list of delivered item_ids (for UI / log purposes)."""
        delivered: list[str] = []
        remaining: list[dict] = []
        for entry in self.capital_in_transit:
            if entry["arrives_at_tick"] <= current_tick:
                order = entry.get("order")
                if order:
                    # Honour the #185 order conditions captured at purchase.
                    self.add_capital(entry["item_id"], units=[
                        capital_unit_from_order(entry["item_id"], order, current_tick)
                    ])
                else:
                    self.add_capital(entry["item_id"], 1, acquired_tick=current_tick)
                delivered.append(entry["item_id"])
            else:
                remaining.append(entry)
        self.capital_in_transit = remaining
        return delivered

    def manufacture_spares(self, count: int = 1) -> int:
        """Manufacture generic spares into this island's inventory (#185/#188).

        Spares are produced by the Manufacturer (generic, not tradable) and
        held until transferred with delivered equipment or consumed in a
        repair.  Returns the number actually manufactured after warehouse
        capacity is applied.
        """
        if count <= 0:
            return 0
        room_left = max(
            0,
            self.spares_capacity() - self.inventory.get(ResourceType.SPARES),
        )
        produced = min(count, room_left)
        if produced > 0:
            self.receive_resources(ResourceType.SPARES, produced)
        return produced

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

    def medical_coverage_seats(self, year: int, season_index: int) -> int:
        """Total head-count of valid medical coverage this island holds
        (sum of covered_count over active medical policies).  Used to gate
        student travel to the Education island (2026-06-02)."""
        return sum(
            p.covered_count
            for p in self.insurance_policies
            if p.policy_type == "medical" and p.is_valid(year, season_index)
        )

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

    def receive_resources(
        self,
        rtype: ResourceType,
        qty: int,
        *,
        acquired_tick: int = 0,
        install_equipment: bool = True,
    ) -> None:
        if qty <= 0:
            return
        if install_equipment and self._install_equipment_resource(
            rtype, qty, acquired_tick
        ):
            return
        self.inventory = self.inventory.add(rtype, qty)

    def _install_equipment_resource(
        self, rtype: ResourceType, qty: int, acquired_tick: int
    ) -> bool:
        mapping = EQUIPMENT_RESOURCE_CAPITAL.get(rtype)
        if mapping is None:
            return False
        role_name, item_id = mapping
        if not any(role.name == role_name for role in self.roles):
            return False
        self.add_capital(item_id, qty, acquired_tick=acquired_tick)
        return True

    def spend_dollops(self, amount: float) -> None:
        if self.dollops < amount:
            raise InsufficientFundsError(
                f"{self.name} has {self.dollops:.2f} {CURRENCY_SYMBOL} but needs {amount:.2f}"
            )
        self.dollops -= amount
        self._season_costs = round(getattr(self, "_season_costs", 0.0) + amount, 2)

    def receive_dollops(self, amount: float) -> None:
        self.dollops += amount
        self._season_revenue = round(getattr(self, "_season_revenue", 0.0) + amount, 2)

    def count_workers(self, profession: str) -> int:
        if profession == Profession.UNSKILLED.value:
            return max(0, self.population - self.workforce.count)
        return len([
            worker for worker in self.workforce.active_workers
            if worker.profession == profession
        ])

    def remove_workers(self, profession: str, count: int) -> list:
        if count <= 0:
            return []
        if profession == Profession.UNSKILLED.value:
            available = self.count_workers(profession)
            if available < count:
                raise ValueError(
                    f"{self.name} only has {available} available {profession} workers"
                )
            self.population -= count
            return []
        selected = [
            worker for worker in self.workforce.active_workers
            if worker.profession == profession
        ][:count]
        if len(selected) < count:
            raise ValueError(
                f"{self.name} only has {len(selected)} available {profession} workers"
            )
        selected_ids = {worker.worker_id for worker in selected}
        self.workforce.workers = [
            worker for worker in self.workforce.workers
            if worker.worker_id not in selected_ids
        ]
        return selected

    def add_workers(self, profession: str, count: int, training_level: int = 1) -> list:
        if count <= 0:
            return []
        if profession == Profession.UNSKILLED.value:
            self.population += count
            return []
        return self.workforce.add_workers(
            count,
            training_level=training_level,
            profession=profession,
        )

    def wealth_breakdown(self, prices: dict[ResourceType, float],
                         loan_ledger=None, capital_catalogue=None,
                         current_tick: int = 0) -> dict:
        """Decompose the win-condition score into its labelled drivers.

        The ``components`` are signed (liabilities negative) and sum to exactly
        ``total`` — ``total_wealth`` is implemented in terms of this so the panel
        and the score can never disagree (P7 / #86).  This is the *island
        liquidation* total; investor wealth (personal cash + equity holdings) is
        a separate balance sheet — see ``net_worth``.
        """
        treasury = self.dollops
        household_cash = self.household_cash
        inventory_value = self.inventory.total_value(prices)
        capital_value = self.capital_book_value(capital_catalogue, current_tick)
        bank_debt = (
            loan_ledger.outstanding_debt(self.player_id) if loan_ledger else 0.0
        )
        loans_receivable = (
            loan_ledger.loans_receivable(self.player_id) if loan_ledger else 0.0
        )
        shareholder_debt = sum(self.shareholder_loans.values())
        # Unrounded so the signed components sum to exactly ``total`` (and to the
        # prior total_wealth value); presentation layers round for display.
        components = {
            "treasury": treasury,
            "household_cash": household_cash,
            "inventory_value": inventory_value,
            "capital_value": capital_value,
            "loans_receivable": loans_receivable,
            "bank_debt": -bank_debt,
            "shareholder_debt": -shareholder_debt,
        }
        total = sum(components.values())
        return {"components": components, "total": total}

    def total_wealth(self, prices: dict[ResourceType, float],
                     loan_ledger=None, capital_catalogue=None,
                     current_tick: int = 0) -> float:
        return self.wealth_breakdown(
            prices, loan_ledger, capital_catalogue, current_tick
        )["total"]

    def capital_book_value(self, capital_catalogue=None, current_tick: int = 0) -> float:
        if not capital_catalogue:
            return 0.0
        items = {item.item_id: item for item in capital_catalogue}
        total = 0.0
        from ..engine.engineering import effective_capital_service_life
        for item_id, count in self.capital_inventory.items():
            item = items.get(item_id)
            if not item:
                continue
            depreciation_ticks = effective_capital_service_life(
                self, item.service_life_seasons
            )
            if depreciation_ticks <= 0:
                depreciation_ticks = 5 * 4
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
