from __future__ import annotations
import math
import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from ..models.player import Player
from ..models.equity import CapTable, AUCTIONED_SHARES
from ..models.owner import Owner
from ..models.market import Market
from ..models.deal import DealLedger
from ..models.capital_negotiation import (
    CapitalNegotiationLedger,
    CapitalOrderNegotiation,
    CapitalNegotiationStatus,
)
from ..models.order_book import ManufacturerOrderBook, compute_promise_dates
from ..models.worker_transfer import WorkerTransferOffer
from ..models.loan import LoanLedger, Loan, LoanStatus
from ..models.lease import LeaseLedger, Lease, LeaseStatus
from ..models.storage_contract import (
    StorageContractLedger, StorageContract, StorageContractStatus,
)
from ..models.insurance import banker_can_process_claims
from ..models.resource import ResourceType
from ..models.role import ROLES
from ..models.profession import Profession, band_of
from ..models.training import (
    TrainingRegistry,
    TrainingRequest,
    TrainingStatus,
    campus_has_technical_workshop,
    settling_seasons_on_return,
)
from ..models.staffing import StaffingRegistry, StaffingContract, StaffingStatus
from ..models.workforce import Workforce, Worker
from ..engine.cycle import BusinessCycle, PHASES
from ..engine.events import EventChartLoader, SeasonEventResolver
from ..engine.production import ProductionEngine
from ..engine.trading import TradingEngine
from ..engine.telemetry import ResourceFlowTelemetry
from ..engine.turn import TurnManager
from ..engine.engineering import effective_capital_service_life
from ..constants import (
    SEASONS, STARTING_DOLLOPS, STARTING_INVENTORY,
    STARTING_WORKFORCE, STARTING_TRAINED_FRACTION,
    STARTING_WORKERS_BY_PROFESSION,
    WORKING_LIFE_SEASONS, DEFAULT_WORKING_LIFE_SEASONS, STARTING_WORKER_AGES,
    DEFAULT_MAINTENANCE_FRACTION, STARTING_AGED_CAPITAL,
    EQUIPMENT_FAILURE_PROB_BY_QUARTER,
    EQUIPMENT_FAILURE_EVENT_MULTIPLIER,
    EQUIPMENT_FAILURE_REPAIR_FRACTION,
    EQUIPMENT_SPARES_REPAIR_DISCOUNT,
    EQUIPMENT_REPAIR_AIR_FREIGHT,
    EQUIPMENT_REPAIR_SHIP_FREIGHT,
    EQUIPMENT_WARRANTY_ANNUAL_RATE,
    BASE_BIRTH_RATE,
    QOL_BIRTH_RATE_MIN, QOL_BIRTH_RATE_MAX,
    QOL_EMIGRATION_THRESHOLD, QOL_EMIGRATION_RATE,
    STARTING_PRODUCTION_CAPACITY,
    STARTING_POPULATION,
    WORKFORCE_PARTICIPATION_RATE,
    TOTAL_STARTING_DOLLOPS, TOTAL_STARTING_POPULATION,
    CURRENCY_SYMBOL,
    BASE_PRICES,
    BABY_BOOM_POPULATION_GROWTH_MULTIPLIER,
    BABY_BOOM_QOL_STABILITY_DELTA,
    PAYROLL_WAGE_BY_BAND,
    HOUSEHOLD_ACTIVITY_STIMULUS_PER_CAPITA,
    REBUILD_LEVY_INSTALLMENTS,
    REBUILD_LEVY_MIN_DOLLOPS,
)
from ..constants_capacity import CAPITAL_CATALOGUE
from .qol import (
    compute_qol,
    food_coverage,
    health_coverage,
    mitigated_pollution_index,
)

SAVE_VERSION = 8

# Renamed resources: old save inventory key -> current key (2026-06-02).
LEGACY_RESOURCE_IDS: dict[str, str] = {
    "LaboratoryEquipment": "Reagents",
    "HealthServices": "MedicalSupplies",
}

LEGACY_CAPITAL_ITEM_IDS: dict[str, str] = {
    "educator.apprenticeship_programme": "educator.technical_workshop",
    # The old storage effect was never enforced; preserve old saves by
    # converting the retired building into its functional replacement.
    "farmer.storage_building": "farmer.grain_silo",
}


def _current_capital_item_id(item_id: str) -> str:
    return LEGACY_CAPITAL_ITEM_IDS.get(item_id, item_id)


def _migrate_capital_inventory(raw: dict) -> dict[str, int]:
    migrated: dict[str, int] = {}
    for item_id, count in raw.items():
        current_id = _current_capital_item_id(str(item_id))
        migrated[current_id] = migrated.get(current_id, 0) + int(count)
    return migrated


def _migrate_capital_ticks(raw: dict) -> dict[str, list[int]]:
    migrated: dict[str, list[int]] = {}
    for item_id, ticks in raw.items():
        current_id = _current_capital_item_id(str(item_id))
        migrated.setdefault(current_id, []).extend(int(t) for t in ticks)
    return migrated


def _migrate_capital_in_transit(raw: list[dict]) -> list[dict]:
    migrated: list[dict] = []
    for entry in raw:
        current = dict(entry)
        if "item_id" in current:
            current["item_id"] = _current_capital_item_id(str(current["item_id"]))
        migrated.append(current)
    return migrated


def _migrate_capital_units(pd: dict) -> dict[str, list]:
    """Build per-unit capital records (#185 / #188) from a serialized player.

    New saves carry ``capital_units`` directly; older saves are migrated from
    the legacy aggregate dicts (counts + acquisition ticks, with warranty /
    failed flags) so existing games load unchanged.
    """
    from ..models.player import CapitalUnit

    raw_units = pd.get("capital_units")
    if raw_units is not None:
        out: dict[str, list] = {}
        for item_id, units in raw_units.items():
            current_id = _current_capital_item_id(str(item_id))
            out.setdefault(current_id, []).extend(
                CapitalUnit.from_dict({**u, "item_id": current_id}) for u in units
            )
        return out

    # Legacy migration from the old aggregate dicts.
    inventory = _migrate_capital_inventory(pd.get("capital_inventory", {}))
    ticks = _migrate_capital_ticks(pd.get("capital_acquired_ticks", {}))
    warranties = _migrate_capital_inventory(pd.get("capital_warranties", {}))
    failed = _migrate_capital_inventory(pd.get("failed_capital", {}))
    out: dict[str, list] = {}
    seq = 0
    for item_id, count in inventory.items():
        item_ticks = list(ticks.get(item_id, []))
        if len(item_ticks) < count:
            item_ticks.extend([0] * (count - len(item_ticks)))
        n_warranty = warranties.get(item_id, 0)
        n_failed = failed.get(item_id, 0)
        units: list = []
        for i in range(count):
            seq += 1
            units.append(CapitalUnit(
                item_id=item_id,
                acquired_tick=int(item_ticks[i]),
                unit_id=seq,
                warranty=(i < n_warranty),
                status=("failed" if i >= count - n_failed else "in_service"),
            ))
        out[item_id] = units
    return out


@dataclass
class PlayerSpec:
    name: str
    role_names: list[str]
    is_human: bool = True
    starting_dollops: float | None = None  # overrides config default if set


@dataclass
class GameConfig:
    player_specs: list[PlayerSpec]
    num_years: int = 3
    starting_dollops: float = STARTING_DOLLOPS
    event_charts_path: str | None = None


@dataclass
class GameSummary:
    winner: Player
    final_rankings: list[tuple[Player, float]]
    deal_count: int
    price_history: list
    # Total Dollops in circulation, snapshotted once per season (index 0 is the
    # opening balance before any season runs).  Surfaced so calibration can see
    # whether the economy inflates or starves as faucets/sinks change — the
    # formula market mints/burns cash, so the money supply is otherwise
    # unanchored.  See requirements/economics-review-2026-06-10.md (P5 / #73).
    money_supply: list[float] = field(default_factory=list)
    # Dynamic supply-chain liveness (B1/B2, #73): a ResourceFlowTelemetry with
    # per-resource produced/consumed/traded volumes and input-starvation counts.
    resource_flow: "ResourceFlowTelemetry | None" = None
    brownout_count: int = 0
    ce_factor_samples: list[float] = field(default_factory=list)


class Game:
    def __init__(self, config: GameConfig, io_adapter, save_path: str = "island_traders_save.json"):
        self.config = config
        self.io = io_adapter
        self.save_path = save_path
        self.players: list[Player] = []
        self.market: Market | None = None
        self.ledger: DealLedger | None = None
        self.capital_negotiations: CapitalNegotiationLedger | None = None
        self.order_book = ManufacturerOrderBook()
        self.transfer_offers: list[WorkerTransferOffer] = []
        self.loan_ledger: LoanLedger | None = None
        self.lease_ledger: LeaseLedger | None = None
        self.storage_contract_ledger: StorageContractLedger | None = None
        self.training: TrainingRegistry | None = None
        self.staffing: StaffingRegistry | None = None
        self.turn_manager: TurnManager | None = None
        self._resume_year: int = 0
        self._resume_season: int = 0
        # Per-season total Dollops in circulation; see GameSummary.money_supply.
        self._money_supply_history: list[float] = []
        # Dynamic supply-chain liveness counters (B1/B2, #73); wired to the
        # market + production engine in setup().
        self.resource_flow = ResourceFlowTelemetry()
        self._ce_factor_samples: list[float] = []
        self.business_cycle = BusinessCycle()
        self.current_cycle = self.business_cycle.snapshot()

    def setup(self) -> None:
        self.market = Market()
        self.ledger = DealLedger()
        self.capital_negotiations = CapitalNegotiationLedger()
        self.order_book = ManufacturerOrderBook()
        self.transfer_offers = []
        self.owners: dict[str, Owner] = {}
        self.loan_ledger = LoanLedger()
        self.lease_ledger = LeaseLedger()
        self.storage_contract_ledger = StorageContractLedger()
        self.training = TrainingRegistry()
        self.staffing = StaffingRegistry()

        num_players = len(self.config.player_specs)
        default_dollops = TOTAL_STARTING_DOLLOPS / num_players
        # Each island starts with STARTING_POPULATION residents (50) — a fixed
        # per-island figure, NOT a share of a global total.  (Previously this
        # used TOTAL_STARTING_POPULATION // num_players = 20, which silently
        # overrode the intended 50 and left population < the 50-worker
        # workforce.  2026-06-02.)
        default_population = STARTING_POPULATION
        # Each island starts with a fixed STARTING_WORKFORCE (50) regardless of
        # player count — "each island starts with 50 workers" (2026-06-02).
        # Previously scaled by 7/num_players, which (with a fixed 50-resident
        # population) would inflate small-game islands past their populace.
        # 2026-07-01: workforce_scale now also carries WORKFORCE_PARTICIPATION_RATE
        # (0.50) so the starting workforce is half the population, not all of
        # it — this scales STARTING_WORKFORCE totals and each named profession's
        # seed count uniformly, preserving the calibrated manager/technician/
        # worker ratios within each role.
        workforce_scale = WORKFORCE_PARTICIPATION_RATE

        for idx, spec in enumerate(self.config.player_specs):
            roles = []
            for rname in spec.role_names:
                if rname not in ROLES:
                    raise ValueError(f"Unknown role: {rname!r}. Valid roles: {list(ROLES.keys())}")
                roles.append(ROLES[rname])

            dollops = spec.starting_dollops if spec.starting_dollops is not None else default_dollops

            player = Player(
                player_id=idx,
                name=spec.name,
                roles=roles,
                dollops=dollops,
                is_human=spec.is_human,
                population=default_population,
            )

            # Equity scaffolding (Phase 1/2b): every player owns a 60% majority
            # of their own island (player_id == island id); 40% remains
            # authorized but unissued.
            # Additive — the pure engine keeps its single-pool economy and
            # total_wealth scoring; the web path (app.py) applies the full flip
            # (treasury reseed, bid->personal cash, shareholder loans).
            player.cap_table = CapTable.new_with_majority(str(idx))
            player.holdings = {str(idx): AUCTIONED_SHARES}
            self.owners[str(idx)] = Owner(
                owner_id=str(idx),
                name=player.name,
                personal_cash=player.personal_cash,
                holdings={str(idx): AUCTIONED_SHARES},
            )

            # Production capacity = max of all assigned roles
            combined_capacity = max(
                (STARTING_PRODUCTION_CAPACITY.get(rname, 0.5) for rname in spec.role_names),
                default=0.5,
            )
            player.production_capacity = combined_capacity

            # Bootstrap starting inventory
            for rname in spec.role_names:
                for res_str, qty in STARTING_INVENTORY.get(rname, {}).items():
                    player.receive_resources(ResourceType(res_str), qty)

            # Build starting workforce with specific professions (scaled by player count)
            for rname in spec.role_names:
                total_workers = max(1, round(STARTING_WORKFORCE.get(rname, 3) * workforce_scale))
                profession_breakdown = STARTING_WORKERS_BY_PROFESSION.get(rname, [])

                allocated = 0
                role_age_seed = STARTING_WORKER_AGES.get(rname, {})
                for profession_name, count in profession_breakdown:
                    scaled_count = max(1, round(count * workforce_scale))
                    seed_age = 0
                    seasons_left = role_age_seed.get(profession_name)
                    if seasons_left is not None:
                        life = WORKING_LIFE_SEASONS.get(
                            band_of(profession_name).value,
                            DEFAULT_WORKING_LIFE_SEASONS,
                        )
                        seed_age = max(0, life - seasons_left)
                    player.workforce.add_workers(
                        scaled_count, training_level=1,
                        profession=profession_name, age_seasons=seed_age,
                    )
                    allocated += scaled_count

                # Remaining slots are Unskilled
                unskilled_count = total_workers - allocated
                if unskilled_count > 0:
                    player.workforce.add_workers(unskilled_count, training_level=0,
                                                 profession=Profession.UNSKILLED.value)

                # Phase C — seed pre-existing aged capital for this role.
                # acquired_tick = -age means age = 0 - (-age) at start
                # (game starts at tick 0).
                for item_id, qty, age in STARTING_AGED_CAPITAL.get(rname, []):
                    player.add_capital(item_id, qty, acquired_tick=-age)

            self.players.append(player)

        charts = (
            EventChartLoader.from_yaml(self.config.event_charts_path)
            if self.config.event_charts_path
            else EventChartLoader.default_charts()
        )
        self.event_resolver = SeasonEventResolver(charts)
        production = ProductionEngine()
        trading = TradingEngine(self.market, self.ledger, self.players)
        # Wire dynamic supply-chain liveness telemetry (B1/B2, #73) through the
        # market + production engine so the simulation runner can read it.
        self.market.telemetry = self.resource_flow
        production.telemetry = self.resource_flow
        # Let production recall a player's own unsold asks to cover an input
        # shortfall (Wave 5.2) rather than forcing a buy-back.
        production.market = self.market
        production.io = self.io
        self.turn_manager = TurnManager(
            self.players, production, trading, self.market, self.io, self.training,
            self.staffing, self.loan_ledger, self.lease_ledger,
            storage_contract_ledger=self.storage_contract_ledger,
        )
        self.turn_manager.current_cycle = self.current_cycle

    def _total_money_supply(self) -> float:
        """Total liquid Dollops in circulation: every island's operating
        treasury, every investor's personal cash, and resident household cash.
        Loans, payroll, and player trades only move Dollops between these
        balances, so this is conserved except where the formula market mints
        (sell) or burns (buy) cash."""
        island_cash = sum(p.dollops + p.household_cash for p in self.players)
        if getattr(self, "owners", None) and any(p.owner_id for p in self.players):
            return island_cash + sum(owner.personal_cash for owner in self.owners.values())
        return sum(p.dollops + p.personal_cash + p.household_cash for p in self.players)

    def _get_player(self, player_id: int) -> Player | None:
        return next((p for p in self.players if p.player_id == player_id), None)

    def create_transfer_offer(
        self,
        *,
        from_player: Player,
        to_player: Player,
        profession: str,
        count: int,
        fee_per_head: float,
        direction: str,
        expires_season: int,
    ) -> WorkerTransferOffer:
        if count <= 0:
            raise ValueError("Transfer count must be positive.")
        if fee_per_head < 0:
            raise ValueError("Transfer fee cannot be negative.")
        offer = WorkerTransferOffer.create(
            from_player=from_player.player_id,
            to_player=to_player.player_id,
            profession=profession,
            count=count,
            fee_per_head=fee_per_head,
            expires_season=expires_season,
            direction=direction,
        )
        self.transfer_offers.append(offer)
        return offer

    def resolve_transfer_offer(
        self,
        responding_player: Player,
        offer_id: str,
        accept: bool,
    ) -> dict:
        offer = next((o for o in self.transfer_offers if o.offer_id == offer_id), None)
        if offer is None or offer.status != "pending":
            return {"ok": False, "error": "Offer not found or already resolved"}
        expected_responder = (
            offer.to_player if offer.direction == "offer" else offer.from_player
        )
        if responding_player.player_id != expected_responder:
            return {"ok": False, "error": "Not your offer to respond to"}
        if not accept:
            offer.status = "declined"
            return {"ok": True, "accepted": False, "offer_id": offer_id}

        sender = self._get_player(offer.from_player)
        receiver = self._get_player(offer.to_player)
        if sender is None or receiver is None:
            offer.status = "expired"
            return {"ok": False, "error": "Transfer party no longer exists"}
        available = sender.count_workers(offer.profession)
        if available < offer.count:
            return {
                "ok": False,
                "error": (
                    f"Sender only has {available} available "
                    f"{offer.profession} workers"
                ),
            }
        total_fee = round(offer.fee_per_head * offer.count, 2)
        if receiver.dollops < total_fee:
            return {"ok": False, "error": "Receiver cannot afford the transfer fee"}

        moved = sender.remove_workers(offer.profession, offer.count)
        if offer.profession == Profession.UNSKILLED.value:
            receiver.add_workers(offer.profession, offer.count)
        else:
            for worker in moved:
                worker.worker_id = receiver.workforce._next_id
                receiver.workforce._next_id += 1
                worker.in_training = False
                worker.on_contract = False
                worker.absent_seasons = 0
                receiver.workforce.workers.append(worker)
        receiver.spend_dollops(total_fee)
        sender.receive_dollops(total_fee)
        offer.status = "accepted"
        return {
            "ok": True,
            "accepted": True,
            "offer_id": offer_id,
            "workers_moved": offer.count,
            "profession": offer.profession,
            "fee_paid": total_fee,
        }

    def expire_transfer_offers(self, current_season_index: int) -> None:
        for offer in self.transfer_offers:
            if offer.status == "pending" and current_season_index > offer.expires_season:
                offer.status = "expired"

    def refresh_order_promises(
        self,
        manufacturer_id: int,
        current_year: int,
        current_season: int,
    ) -> None:
        manufacturer = self._get_player(manufacturer_id)
        slots = 1
        if manufacturer is not None and self.turn_manager is not None:
            slots = self.turn_manager.production.manufacturer_durable_allowance(
                manufacturer
            )
        compute_promise_dates(
            self.order_book,
            manufacturer_id,
            slots,
            current_year,
            current_season,
        )

    def enqueue_capital_negotiation(
        self,
        negotiation: CapitalOrderNegotiation,
        current_year: int,
        current_season: int,
        *,
        locked: bool = True,
    ) -> None:
        entry = self.order_book.add(
            negotiation.negotiation_id,
            negotiation.manufacturer_id,
            premium=round(
                negotiation.buyer_offer - negotiation.recommended_total,
                2,
            ),
        )
        entry.premium = round(
            negotiation.buyer_offer - negotiation.recommended_total,
            2,
        )
        entry.locked = locked
        if not locked:
            self.order_book.place_by_premium(
                negotiation.negotiation_id,
                negotiation.manufacturer_id,
                entry.premium,
            )
        self.refresh_order_promises(
            negotiation.manufacturer_id,
            current_year,
            current_season,
        )

    def record_season_pl(self, season_name: str) -> None:
        for player in self.players:
            revenue = round(getattr(player, "_season_revenue", 0.0), 2)
            costs = round(getattr(player, "_season_costs", 0.0), 2)
            history = list(getattr(player, "_pl_history", []))
            history.append({
                "season": season_name,
                "revenue": revenue,
                "costs": costs,
                "profit": round(revenue - costs, 2),
            })
            player._pl_history = history[-4:]

    def reset_season_pl(self) -> None:
        for player in self.players:
            player._season_revenue = 0.0
            player._season_costs = 0.0

    def island_report_for_player(
        self,
        player: Player,
        prices: dict[ResourceType, float] | None = None,
        current_tick: int = 0,
    ) -> dict:
        prices = prices or (self.market.current_prices() if self.market else {})
        inventory_value = player.inventory.total_value(prices)
        capital_value = player.capital_book_value(CAPITAL_CATALOGUE, current_tick)
        loans = self.loan_ledger.outstanding_debt(player.player_id) if self.loan_ledger else 0.0
        deficiencies = []
        catalogue = {item.item_id: item for item in CAPITAL_CATALOGUE}
        for item_id, failed in player.failed_capital.items():
            if failed <= 0:
                continue
            item = catalogue.get(item_id)
            deficiencies.append({
                "item_id": item_id,
                "name": item.name if item else item_id,
                "failed": failed,
                "repairable": True,
            })
        training_active = (
            len(self.training.active_for_player(player.player_id))
            if self.training else 0
        )
        graduating_next = 0
        if self.training:
            for req in self.training.active_for_player(player.player_id):
                if req.return_year < 0 or req.return_season < 0:
                    continue
                ret_tick = req.return_year * len(SEASONS) + req.return_season
                if 0 <= ret_tick - current_tick <= 1:
                    graduating_next += len(req.worker_ids)
        capacity = player.workforce.count
        employed = player.workforce.active_count
        return {
            "pl_history": list(getattr(player, "_pl_history", [])),
            "balance_sheet": {
                "treasury": round(player.dollops, 2),
                "inventory_value": round(inventory_value, 2),
                "capital_value": round(capital_value, 2),
                "loans": round(loans, 2),
                "net_worth": round(
                    player.dollops + inventory_value + capital_value - loans,
                    2,
                ),
            },
            "deficiencies": deficiencies,
            "manpower": {
                "population": player.population,
                "employed": employed,
                "capacity": capacity,
                "vacancies": max(0, capacity - employed),
                "training_queue": training_active,
                "graduating_next": graduating_next,
            },
        }

    def _seasonal_payroll_due(self, player: Player) -> float:
        return round(
            sum(
                PAYROLL_WAGE_BY_BAND.get(band_of(worker.profession).value, 0.0)
                for worker in player.workforce.active_workers
            ),
            2,
        )

    def _process_payroll(self, year: int, season: int) -> None:
        """Charge per-season wages for active home workers.

        Payroll moves Dollops from the island treasury to resident household
        cash. Trainees and contracted-away staff are excluded because they are
        not available to the home island. Shortfalls are logged but do not add
        a layoff/morale rule in this pass.
        """
        _ = (year, season)  # kept for log-hook symmetry with other processors
        for player in self.players:
            due = self._seasonal_payroll_due(player)
            if due <= 0:
                continue
            paid = min(player.dollops, due)
            player.dollops = round(player.dollops - paid, 2)
            player.household_cash = round(player.household_cash + paid, 2)
            if paid >= due:
                self.io.print(
                    f"[PAYROLL] {player.name}: paid {CURRENCY_SYMBOL}{paid:.2f} "
                    f"to household wages."
                )
            else:
                shortfall = round(due - paid, 2)
                self.io.print(
                    f"[PAYROLL SHORTFALL] {player.name}: paid "
                    f"{CURRENCY_SYMBOL}{paid:.2f} of {CURRENCY_SYMBOL}{due:.2f}; "
                    f"{CURRENCY_SYMBOL}{shortfall:.2f} unpaid."
                )

    def _process_household_activity_stimulus(self, year: int, season: int) -> None:
        """Mint a small household income floor tied to active local employment.

        Payroll recirculates island treasury, but playtest calibration still
        showed a large money-supply drain from maintenance, external funding,
        and other non-player sinks. This household-side faucet keeps consumer
        demand funded without handing operating cash directly to producers.
        """
        _ = (year, season)
        rate = HOUSEHOLD_ACTIVITY_STIMULUS_PER_CAPITA
        if rate <= 0:
            return
        for player in self.players:
            if player.workforce.active_count <= 0:
                continue
            amount = round(max(0, player.population) * rate, 2)
            if amount <= 0:
                continue
            player.household_cash = round(player.household_cash + amount, 2)
            self.io.print(
                f"[HOUSEHOLDS] {player.name}: received "
                f"{CURRENCY_SYMBOL}{amount:.2f} in local activity income."
            )

    def run(self) -> GameSummary:
        # Opening balance, before any season runs (resumed games append from
        # wherever they left off — the series stays monotonic in season order).
        if not self._money_supply_history:
            self._money_supply_history.append(round(self._total_money_supply(), 2))
        for year in range(self._resume_year, self.config.num_years):
            self._reset_annual_qol_accumulators()
            start_season = self._resume_season if year == self._resume_year else 0
            for season_index in range(start_season, len(SEASONS)):
                self.current_cycle = self.business_cycle.advance_season()
                self.event_resolver.current_cycle = self.current_cycle
                self.turn_manager.current_cycle = self.current_cycle
                if self.business_cycle.last_phase_change:
                    old, new = self.business_cycle.last_phase_change
                    self.io.print(
                        f"[CYCLE] {old} -> {new}: {PHASES[new].note}."
                    )
                self.expire_transfer_offers(season_index)
                self._process_training_returns(year, season_index)
                self._process_staffing_returns(year, season_index)
                self._process_retirements(year, season_index)
                self._process_capital_maintenance(year, season_index)
                self._process_spoilage(year, season_index)
                self._process_payroll(year, season_index)
                self._process_household_activity_stimulus(year, season_index)
                event_results = self.event_resolver.resolve_all(
                    self.players, self.turn_manager._damage_counters, year=year,
                    season_index=season_index,
                )
                self._apply_business_cycle_event_effects(event_results)
                self._process_disaster_capital_impacts(year, season_index, event_results)
                # Surface any halt-cap suppressions in the game log
                # (2026-05-27 event-frequency-cap brief).
                for msg in self.event_resolver.last_suppressions:
                    self.io.print(f"[EVENT] Suppressed halt: {msg}")
                # Expose resolved events to server hooks (conditions panel etc.).
                self._last_event_results = event_results
                # Optional hooks — set by the server to install/clear the
                # per-season Ready timer in simultaneous-play mode.
                cb = getattr(self, "before_season", None)
                if cb:
                    try:
                        cb(year, season_index)
                    except Exception:
                        pass
                self.turn_manager.run_season(year, season_index, event_results)
                self._record_ce_factor_samples()
                self.record_season_pl(SEASONS[season_index])
                self._advance_temporary_absences()
                cb = getattr(self, "after_season", None)
                if cb:
                    try:
                        cb(year, season_index)
                    except Exception:
                        pass
                self._auto_save(year, season_index + 1)
                self.reset_season_pl()
                self._money_supply_history.append(
                    round(self._total_money_supply(), 2)
                )

            prices = self.market.current_prices()
            year_end_tick = year * len(SEASONS) + (len(SEASONS) - 1)
            wealthies = [
                p.total_wealth(prices, self.loan_ledger, CAPITAL_CATALOGUE, year_end_tick)
                for p in self.players
            ]

            for player, wealth in zip(self.players, wealthies):
                player.record_year_wealth(
                    prices, self.loan_ledger, CAPITAL_CATALOGUE, year_end_tick
                )
            self._process_year_end_qol_and_population(year, prices, year_end_tick)

            self.io.print(self._year_end_summary(year, prices, year_end_tick))

        Path(self.save_path).unlink(missing_ok=True)
        return self.compute_summary()

    def _reset_annual_qol_accumulators(self) -> None:
        for player in self.players:
            player._oil_consumed_this_year = 0
            player._food_demanded_this_year = 0
            player._food_bought_this_year = 0
            player._health_demanded_this_year = 0
            player._health_bought_this_year = 0

    def _process_year_end_qol_and_population(
        self,
        year: int,
        prices: dict[ResourceType, float],
        year_end_tick: int,
    ) -> None:
        _ = (prices, year_end_tick)
        qol_scores: dict[int, float] = {}
        for player in self.players:
            fc = food_coverage(
                getattr(player, "_food_demanded_this_year", 0),
                getattr(player, "_food_bought_this_year", 0),
            )
            hc = health_coverage(
                getattr(player, "_health_demanded_this_year", 0),
                getattr(player, "_health_bought_this_year", 0),
            )
            pi = mitigated_pollution_index(
                getattr(player, "_oil_consumed_this_year", 0),
                player.population,
                hc,
            )
            qol = compute_qol(fc, hc, pi)
            player._qol_score = round(qol, 3)
            player._food_coverage = round(fc, 3)
            player._health_coverage = round(hc, 3)
            player._pollution_index = round(pi, 3)
            player._qol_observed_years = getattr(player, "_qol_observed_years", 0) + 1
            qol_scores[player.player_id] = qol
            self.io.print(
                f"  [QoL] {player.name}: food={fc:.0%} health={hc:.0%} "
                f"pollution={pi:.0%} -> QoL {qol:.2f}"
            )

        for player in self.players:
            qol = qol_scores[player.player_id]
            birth_modifier = QOL_BIRTH_RATE_MIN + qol * (
                QOL_BIRTH_RATE_MAX - QOL_BIRTH_RATE_MIN
            )
            birth_rate = BASE_BIRTH_RATE * birth_modifier
            new_people = max(0, round(player.population * birth_rate))
            if new_people:
                player.population += new_people
                self.io.print(
                    f"  [Population] {player.name}: +{new_people} people born "
                    f"(QoL {qol:.2f} -> rate {birth_rate:.3f}; "
                    f"population now {player.population})"
                )

        if len(self.players) < 2:
            return
        mean_qol = sum(qol_scores.values()) / len(qol_scores)
        best_player = max(self.players, key=lambda p: qol_scores[p.player_id])
        for player in self.players:
            if player is best_player:
                continue
            qol = qol_scores[player.player_id]
            if mean_qol - qol >= QOL_EMIGRATION_THRESHOLD:
                emigrants = max(1, round(player.population * QOL_EMIGRATION_RATE))
                emigrants = min(emigrants, player.population - 1)
                if emigrants > 0:
                    player.population -= emigrants
                    best_player.population += emigrants
                    self.io.print(
                        f"  [Emigration] {emigrants} people left {player.name} "
                        f"(QoL {qol:.2f}) for {best_player.name} "
                        f"(QoL {qol_scores[best_player.player_id]:.2f})."
                    )

    def _process_capital_maintenance(self, year: int, season: int) -> None:
        """Expire end-of-life capital, then charge per-season maintenance.

        Expiry: any unit whose age (current_tick − acquired_tick) is at
        least its CapitalItem.service_life_seasons is removed from
        capital_inventory (oldest units first, FIFO).  The owner must
        re-purchase from the Manufacturer to restore that capacity.

        Maintenance: each surviving unit costs
        ``maintenance_per_season`` Dp (or DEFAULT_MAINTENANCE_FRACTION ×
        cost when not overridden) per season.  Paid per-unit; a unit
        the owner can't afford is flagged *unmaintained* and
        contributes 0 capacity this season via
        ``Player.effective_capital_inventory``.  The flag resets each
        season.
        """
        current_tick = year * len(SEASONS) + season
        catalogue = {it.item_id: it for it in CAPITAL_CATALOGUE}
        for player in self.players:
            self._process_rebuild_levy_payments(player)
            # Reset transient unmaintained state at the start of the season.
            player.unmaintained_capital = {}
            player.manufacturer_durable_output_used = 0
            self._complete_capital_repairs(player, current_tick, catalogue)
            self._attempt_pending_capital_repairs(player, current_tick, catalogue)
            if season == 0:
                self._process_equipment_warranty_premiums(player, catalogue)

            # 1) Expiry — remove units past their service life (oldest first).
            for item_id in list(player.capital_inventory.keys()):
                item = catalogue.get(item_id)
                if not item or item.service_life_seasons <= 0:
                    continue
                ticks = player.capital_acquired_ticks.get(item_id, [])
                service_life = effective_capital_service_life(
                    player, item.service_life_seasons
                )
                expired = sum(1 for t in ticks if current_tick - t >= service_life)
                if expired > 0:
                    player.remove_capital(item_id, expired)
                    self.io.print(
                        f"\n[CAPITAL EXPIRED] {player.name}: {expired} × "
                        f"{item.name} reached end of service life. "
                        f"Repurchase from the Manufacturer to restore capacity."
                    )

            # 2) Maintenance — pay per surviving unit; mark shortfalls.
            for item_id, count in list(player.capital_inventory.items()):
                item = catalogue.get(item_id)
                if not item:
                    continue
                if item.effects.get("maintenance_free", False):
                    continue
                per_unit = (
                    item.maintenance_per_season
                    if item.maintenance_per_season > 0
                    else DEFAULT_MAINTENANCE_FRACTION * item.cost
                )
                if per_unit <= 0:
                    continue
                unmaintained = 0
                for _ in range(count):
                    if player.dollops >= per_unit:
                        player.dollops -= per_unit
                    else:
                        unmaintained += 1
                if unmaintained > 0:
                    player.unmaintained_capital[item_id] = unmaintained
                    self.io.print(
                        f"\n[CAPITAL UNMAINTAINED] {player.name}: "
                        f"{unmaintained} × {item.name} unmaintained this "
                        f"season (insufficient Dp); contributes 0 capacity "
                        f"until paid."
                    )

            # Failure is rolled every season on the #188 per-quarter schedule
            # (was once a year under the old annual age-bucket model).
            self._process_equipment_failures(player, current_tick, catalogue)

    def _process_spoilage(self, year: int, season: int) -> None:
        """Destroy stock that has exceeded its unprotected shelf life."""
        current_tick = year * len(SEASONS) + season
        no_capacity_name = {
            ResourceType.GRAIN: "silo",
            ResourceType.FOOD: "food-store",
            ResourceType.SPARES: "warehouse",
        }
        for player in self.players:
            for resource, lost in player.process_spoilage(current_tick).items():
                self.io.print(
                    f"[SPOILAGE] {player.name}: {lost} {resource.value} perished "
                    f"— no {no_capacity_name[resource]} capacity."
                )

    def _role_player(self, role_name: str) -> Player | None:
        return next(
            (p for p in self.players if any(r.name == role_name for r in p.roles)),
            None,
        )

    def _capital_rng(self):
        if self.turn_manager is not None:
            return self.turn_manager._rng
        import random
        return random

    def _apply_business_cycle_event_effects(
        self,
        event_results: dict[int, object],
    ) -> None:
        for player in self.players:
            player._season_capital_failure_multiplier = 1.0
            event = event_results.get(player.player_id)
            if event is None:
                continue
            if getattr(event, "baby_boom", False):
                growth = max(1, round(player.population * 0.02 * BABY_BOOM_POPULATION_GROWTH_MULTIPLIER))
                player.population += growth
                event.qol_stability_delta += BABY_BOOM_QOL_STABILITY_DELTA
                self.io.print(
                    f"[BABY BOOM] {player.name}: +{growth} people; "
                    f"population now {player.population}."
                )
            player._season_capital_failure_multiplier = max(
                1.0,
                getattr(event, "capital_failure_multiplier", 1.0),
            )

    def _process_disaster_capital_impacts(
        self,
        year: int,
        season: int,
        event_results: dict[int, object],
    ) -> None:
        current_tick = year * len(SEASONS) + season
        catalogue = {it.item_id: it for it in CAPITAL_CATALOGUE}
        for player in self.players:
            event = event_results.get(player.player_id)
            if event is None:
                continue
            if getattr(event, "capital_failure_multiplier", 1.0) > 1.0:
                self._process_equipment_failures(player, current_tick, catalogue)
            levy_fraction = getattr(event, "rebuild_levy_fraction", 0.0)
            if levy_fraction > 0:
                self._apply_rebuild_levy(player, levy_fraction, event.event_name)

    def _capital_replacement_value(self, player: Player) -> float:
        catalogue = {it.item_id: it for it in CAPITAL_CATALOGUE}
        total = 0.0
        for item_id, count in player.capital_inventory.items():
            item = catalogue.get(item_id)
            if item is not None:
                total += item.cost * count
        return round(total, 2)

    def _apply_rebuild_levy(
        self,
        player: Player,
        levy_fraction: float,
        event_name: str,
    ) -> None:
        value = self._capital_replacement_value(player)
        if value <= 0:
            return
        total = max(REBUILD_LEVY_MIN_DOLLOPS, round(value * levy_fraction, 2))
        installment = round(total / REBUILD_LEVY_INSTALLMENTS, 2)
        existing = list(getattr(player, "_rebuild_levy_installments", []))
        existing.extend([installment] * REBUILD_LEVY_INSTALLMENTS)
        player._rebuild_levy_installments = existing
        self.io.print(
            f"[REBUILD LEVY] {player.name}: {event_name} levy "
            f"{CURRENCY_SYMBOL}{total:.2f} booked over "
            f"{REBUILD_LEVY_INSTALLMENTS} seasons."
        )

    def _process_rebuild_levy_payments(self, player: Player) -> None:
        installments = list(getattr(player, "_rebuild_levy_installments", []))
        if not installments:
            player._rebuild_levy_remaining = 0.0
            return
        due = installments.pop(0)
        paid = min(player.dollops, due)
        if paid > 0:
            player.dollops = round(player.dollops - paid, 2)
        unpaid = round(due - paid, 2)
        if unpaid > 0:
            installments.insert(0, unpaid)
        player._rebuild_levy_installments = installments
        player._rebuild_levy_remaining = round(sum(installments), 2)
        if due > 0:
            self.io.print(
                f"[REBUILD LEVY] {player.name}: paid "
                f"{CURRENCY_SYMBOL}{paid:.2f}; remaining "
                f"{CURRENCY_SYMBOL}{player._rebuild_levy_remaining:.2f}."
            )

    def rebuild_levy_blocked_reason(self, player: Player) -> str:
        """Repair-blocked message naming the levy amount and both payment
        routes (Wave 5.1) — the old wording implied a payment action that
        did not exist."""
        remaining = getattr(player, "_rebuild_levy_remaining", 0.0)
        return (
            f"Rebuild levy of {CURRENCY_SYMBOL}{remaining:.2f} is outstanding — "
            f"repairs resume once it is cleared. Pay it now with Pay Levy, or "
            f"wait for the automatic seasonal installments."
        )

    def _repair_in_progress_count(self, player: Player, item_id: str) -> int:
        return sum(
            int(entry.get("count", 1))
            for entry in player.capital_repair_in_progress
            if entry.get("item_id") == item_id
        )

    def _complete_capital_repairs(
        self,
        player: Player,
        current_tick: int,
        catalogue: dict[str, object],
    ) -> None:
        remaining: list[dict] = []
        # Fresh each season so the UI cue only reflects this season's repairs.
        player.recently_repaired = []
        for entry in player.capital_repair_in_progress:
            if int(entry.get("completes_at_tick", 0)) > current_tick:
                remaining.append(entry)
                continue
            item_id = str(entry.get("item_id", ""))
            count = int(entry.get("count", 1))
            repaired = player.complete_capital_repair(item_id, count)
            item = catalogue.get(item_id)
            if repaired and item is not None:
                self.io.print(
                    f"\n[CAPITAL REPAIRED] {player.name}: {repaired} × "
                    f"{item.name} returned to service."
                )
                player.recently_repaired.append({
                    "item_id": item_id,
                    "name": item.name,
                    "count": repaired,
                })
        player.capital_repair_in_progress = remaining

    def _process_equipment_warranty_premiums(
        self,
        player: Player,
        catalogue: dict[str, object],
    ) -> None:
        manufacturer = self._role_player("Manufacturer")
        if manufacturer is None or manufacturer.player_id == player.player_id:
            return
        for item_id, units in list(player.capital_units.items()):
            item = catalogue.get(item_id)
            # Units on an upfront #188 term contract (maintenance_term_years > 0)
            # already paid in full at order time — only legacy recurring
            # warranties (no term) are billed annually here.
            warranted_units = [
                u for u in units if u.warranty and u.maintenance_term_years == 0
            ]
            if not warranted_units:
                continue
            if item is None:
                # Item left the catalogue: drop stale coverage.
                for u in warranted_units:
                    u.warranty = False
                continue
            per_unit = round(item.cost * EQUIPMENT_WARRANTY_ANNUAL_RATE, 2)
            paid = 0
            for u in warranted_units:
                if player.dollops < per_unit:
                    u.warranty = False   # premium lapses — coverage drops
                    continue
                player.spend_dollops(per_unit)
                manufacturer.receive_dollops(per_unit)
                paid += 1
            if paid:
                self.io.print(
                    f"\n[WARRANTY] {player.name}: paid "
                    f"{CURRENCY_SYMBOL}{per_unit * paid:.2f} to "
                    f"{manufacturer.name} for {paid} × {item.name} warranty."
                )

    def _failure_probability_for_age(self, age_seasons: int) -> float:
        """Per-quarter Weibull failure probability (#188).

        ``age_seasons`` is the unit's age in seasons (0 in the season it is
        delivered), so the quarter of life is ``age_seasons + 1``.  Beyond the
        table's last quarter the final value is held.
        """
        quarter = max(1, age_seasons + 1)
        max_quarter = max(EQUIPMENT_FAILURE_PROB_BY_QUARTER)
        if quarter > max_quarter:
            quarter = max_quarter
        return EQUIPMENT_FAILURE_PROB_BY_QUARTER[quarter]

    def _capital_failure_multiplier(self, player: Player) -> float:
        """Event multiplier on the per-quarter failure probability (#188 seam).

        Natural disasters (earthquake, flood) and sabotage during strikes
        raise the base hazard.  Defaults to EQUIPMENT_FAILURE_EVENT_MULTIPLIER
        (1.0) until those events are wired in.
        """
        return max(
            EQUIPMENT_FAILURE_EVENT_MULTIPLIER,
            getattr(player, "_season_capital_failure_multiplier", 1.0),
        )

    def _process_equipment_failures(
        self,
        player: Player,
        current_tick: int,
        catalogue: dict[str, object],
    ) -> None:
        rng = self._capital_rng()
        multiplier = self._capital_failure_multiplier(player)
        for item_id, units in list(player.capital_units.items()):
            item = catalogue.get(item_id)
            if item is None:
                continue
            # Roll each in-service, uninsured unit on its own quarter (#188).
            for unit in list(units):
                age = max(0, current_tick - unit.acquired_tick)
                # An upfront term contract lapses once its term has elapsed,
                # after which the unit is failure-eligible again.
                if (unit.warranty and unit.maintenance_term_years > 0
                        and age >= unit.maintenance_term_years * len(SEASONS)):
                    unit.warranty = False
                if unit.warranty or unit.status != "in_service":
                    continue
                prob = self._failure_probability_for_age(age) * multiplier
                if rng.random() < prob:
                    unit.status = "failed"
                    self.io.print(
                        f"\n[CAPITAL FAILURE] {player.name}: 1 × {item.name} "
                        f"failed and is down until repaired."
                    )
                    self._settle_equipment_claim(
                        player, item_id, item, current_tick
                    )
                    self._attempt_capital_repair(player, item, current_tick, unit=unit)

    def _settle_equipment_claim(
        self, player, item_id: str, item, current_tick: int
    ) -> float:
        """Pay out an equipment policy when the insured unit fails (#196).

        A total-loss settlement: the Bank pays the agreed 90% of value and the
        policy is spent.  Repair still proceeds as normal — the payout is cash
        toward replacing the unit, not a repair service.
        """
        year, season_index = divmod(current_tick, len(SEASONS))
        policy = next(
            (
                p for p in player.insurance_policies
                if p.policy_type == "equipment"
                and p.item_id == item_id
                and p.is_valid(year, season_index)
            ),
            None,
        )
        if policy is None:
            return 0.0
        banker = next(
            (p for p in self.players if p.player_id == policy.banker_player_id),
            None,
        )
        if banker is None:
            return 0.0
        # #196: "For claims to be processed there needs to be an Insurance
        # Adjuster to process the claim." No adjuster, no settlement — the
        # policy stays open, so cover is not lost while the Bank rehires.
        if not banker_can_process_claims(banker):
            self.io.print(
                f"[CLAIM] {player.name}'s {item.name} claim cannot be settled: "
                f"{banker.name} has no Insurance Adjuster on staff. The policy "
                f"remains in force."
            )
            return 0.0
        # Round DOWN, never up: rounding a float balance up by a fraction of a
        # Dollop made spend_dollops raise "has 16.15 but needs 16.15" and killed
        # the game. A partial settlement must never exceed what the Bank holds.
        payout = math.floor(min(policy.insured_value, banker.dollops) * 100) / 100
        if payout <= 0:
            return 0.0
        banker.spend_dollops(payout)
        player.receive_dollops(payout)
        policy.active = False          # total loss — the cover is spent
        self.io.print(
            f"[CLAIM] {banker.name} paid {player.name} "
            f"{CURRENCY_SYMBOL}{payout:.2f} for the failed {item.name}; "
            f"that equipment policy is now closed."
        )
        return payout

    def _attempt_pending_capital_repairs(
        self,
        player: Player,
        current_tick: int,
        catalogue: dict[str, object],
    ) -> None:
        for item_id in list(player.capital_units.keys()):
            item = catalogue.get(item_id)
            if item is None:
                continue
            in_progress = self._repair_in_progress_count(player, item_id)
            failed_units = [
                u for u in player.capital_units.get(item_id, [])
                if u.status == "failed"
            ]
            # Skip units already covered by a queued ship repair; retry the rest.
            for unit in failed_units[in_progress:]:
                if not self._attempt_capital_repair(
                    player, item, current_tick, unit=unit
                ):
                    break

    def _has_air_repair_capacity(self) -> bool:
        transporter = self._role_player("Transporter")
        if transporter is None:
            return False
        return transporter.effective_capital_inventory().get(
            "transporter.cargo_plane", 0
        ) > 0

    def _repair_unit_for_preview(self, player: Player, item_id: str):
        queued = self._repair_in_progress_count(player, item_id)
        failed_units = [
            u for u in player.capital_units.get(item_id, [])
            if u.status == "failed"
        ]
        return failed_units[queued] if queued < len(failed_units) else None

    def _capital_repair_quote(self, player: Player, item, unit=None) -> dict:
        base_value = (
            unit.purchase_value if (unit is not None and unit.purchase_value)
            else item.cost
        )
        spares_required = max(1, int(getattr(item, "capacity_units", 1)))
        attached_available = unit.spares_attached if unit is not None else 0
        attached_to_use = min(attached_available, spares_required)
        generic_to_use = max(0, spares_required - attached_to_use)
        generic_available = player.inventory.get(ResourceType.SPARES)
        repair_fee = round(
            base_value * EQUIPMENT_FAILURE_REPAIR_FRACTION
            * EQUIPMENT_SPARES_REPAIR_DISCOUNT,
            2,
        )
        freight_qty = (
            EQUIPMENT_REPAIR_AIR_FREIGHT
            if self._has_air_repair_capacity()
            else EQUIPMENT_REPAIR_SHIP_FREIGHT
        )
        common = {
            "use_attached_spares": attached_to_use,
            "use_generic_spares": generic_to_use,
            "spares": spares_required,
            # Back-compat flags for older UI/tests.
            "use_attached_spare": attached_to_use > 0,
            "use_generic_spare": generic_to_use > 0,
        }
        if generic_available < generic_to_use:
            return {
                "dp": repair_fee,
                "freight": freight_qty,
                "repairable": False,
                "reason": (
                    f"Need {spares_required} Spares for {item.name}; "
                    f"available {attached_available + generic_available}."
                ),
                **common,
            }
        if player.dollops < repair_fee:
            return {
                "dp": repair_fee,
                "freight": freight_qty,
                "repairable": False,
                "reason": (
                    f"Need {CURRENCY_SYMBOL}{repair_fee:.2f}; "
                    f"available {CURRENCY_SYMBOL}{player.dollops:.2f}."
                ),
                **common,
            }
        if player.inventory.get(ResourceType.FREIGHT) < freight_qty:
            return {
                "dp": repair_fee,
                "freight": freight_qty,
                "repairable": False,
                "reason": (
                    f"Need {freight_qty} Freight; available "
                    f"{player.inventory.get(ResourceType.FREIGHT)}."
                ),
                **common,
            }
        return {
            "dp": repair_fee,
            "freight": freight_qty,
            "repairable": True,
            "reason": "",
            **common,
        }

    def capital_repair_preview(self, player: Player, item_id: str) -> dict:
        catalogue = {it.item_id: it for it in CAPITAL_CATALOGUE}
        item = catalogue.get(item_id)
        if item is None:
            return {
                "dp": 0.0,
                "freight": 0,
                "repairable": False,
                "reason": "Unknown capital item.",
            }
        unit = self._repair_unit_for_preview(player, item_id)
        if unit is None:
            return {
                "dp": 0.0,
                "freight": 0,
                "repairable": False,
                "reason": "No failed unit is awaiting repair.",
            }
        if getattr(player, "_rebuild_levy_remaining", 0.0) > 0:
            return {
                "dp": 0.0,
                "freight": 0,
                "spares": 0,
                "repairable": False,
                "reason": self.rebuild_levy_blocked_reason(player),
            }
        quote = self._capital_repair_quote(player, item, unit)
        return {
            "dp": quote["dp"],
            "freight": quote["freight"],
            "spares": quote.get("spares", 0),
            "repairable": quote["repairable"],
            "reason": quote["reason"],
        }

    def _credit_freight_to_transporter(self, freight_qty: int) -> None:
        transporter = self._role_player("Transporter")
        if transporter is None or freight_qty <= 0:
            return
        credit = round(self.market.current_price(ResourceType.FREIGHT) * freight_qty, 2)
        transporter.receive_dollops(credit)
        if self.resource_flow is not None:
            self.resource_flow.record_consumed(ResourceType.FREIGHT, freight_qty)
            self.resource_flow.record_traded(ResourceType.FREIGHT, freight_qty)

    def _attempt_capital_repair(
        self,
        player: Player,
        item,
        current_tick: int,
        unit=None,
    ) -> bool:
        manufacturer = self._role_player("Manufacturer")
        if getattr(player, "_rebuild_levy_remaining", 0.0) > 0:
            return False
        quote = self._capital_repair_quote(player, item, unit)
        repair_fee = quote["dp"]
        freight_qty = quote["freight"]
        air = self._has_air_repair_capacity()
        if not quote["repairable"]:
            return False

        # Consume proportional spares — attached kits first, then generic stock.
        attached = int(quote.get("use_attached_spares", 0))
        generic = int(quote.get("use_generic_spares", 0))
        if attached and unit is not None:
            unit.spares_attached -= attached
        if generic:
            player.give_resources(ResourceType.SPARES, generic)
        spares_consumed = attached + generic
        if spares_consumed > 0 and self.resource_flow is not None:
            self.resource_flow.record_consumed(ResourceType.SPARES, spares_consumed)

        player.spend_dollops(repair_fee)
        if manufacturer is not None:
            manufacturer.receive_dollops(repair_fee)
        player.give_resources(ResourceType.FREIGHT, freight_qty)
        self._credit_freight_to_transporter(freight_qty)

        if air:
            if unit is not None:
                unit.status = "in_service"
                unit.repair_completes_at_tick = None
            else:
                player.complete_capital_repair(item.item_id, 1)
            self.io.print(
                f"[CAPITAL REPAIR] {player.name}: repaired 1 × {item.name} "
                f"same-season by air for {CURRENCY_SYMBOL}{repair_fee:.2f} "
                f"+ {freight_qty} Freight."
            )
        else:
            player.capital_repair_in_progress.append({
                "item_id": item.item_id,
                "count": 1,
                "completes_at_tick": current_tick + 1,
            })
            self.io.print(
                f"[CAPITAL REPAIR] {player.name}: shipped repair parts for "
                f"1 × {item.name}; returns next season for "
                f"{CURRENCY_SYMBOL}{repair_fee:.2f} + {freight_qty} Freight."
            )
        return True

    def _process_retirements(self, year: int, season: int) -> None:
        """Age every island's workers one season; remove retirees.

        A worker away at training who retires is also dropped from its
        training batch so it cannot 'return' (it no longer exists).
        """
        for player in self.players:
            retired = player.workforce.advance_age_and_retire(
                WORKING_LIFE_SEASONS, DEFAULT_WORKING_LIFE_SEASONS
            )
            if not retired:
                continue
            for w in retired:
                if w.in_training:
                    self.training.drop_worker(w.worker_id)
            professions = ", ".join(sorted({w.profession for w in retired}))
            self.io.print(
                f"\n[RETIREMENT] {player.name}: {len(retired)} worker(s) "
                f"retired ({professions}). Recruit + retrain to replace."
            )
        self._reconcile_training_flags()

    def _reconcile_training_flags(self) -> None:
        for player in self.players:
            expected = self.training.dispatched_worker_ids(player.player_id)
            player.workforce.reconcile_training_flags(expected)

    def _advance_temporary_absences(self) -> None:
        for player in self.players:
            player.workforce.advance_absences()

    def _process_training_returns(self, year: int, season: int) -> None:
        self._reconcile_training_flags()
        player_map = {p.player_id: p for p in self.players}
        returned_batches = self.training.process_returns(year, season)
        for batch in returned_batches:
            player = player_map.get(batch.requester_id)
            if not player:
                self.io.print(
                    f"\n[Training] Request #{batch.batch_id} could not return: "
                    f"requester island {batch.requester_id} no longer exists."
                )
                continue
            self.io.print(
                f"\n[Training] Request #{batch.batch_id} complete: "
                f"{len(batch.worker_ids)} trainee(s) due back to {player.name} "
                f"as {batch.target_profession}."
            )
            returned = player.workforce.return_from_training(
                batch.worker_ids,
                batch.target_profession,
                batch.engineer_specialty,
                batch.settling_seasons_on_return,
            )
            if returned:
                self.io.print(
                    f"[Training] {player.name}: {len(returned)} worker(s) returned "
                    f"as {batch.target_profession}. "
                    f"New avg efficiency: {player.workforce.average_efficiency*100:.1f}%"
                )
            if len(returned) != len(batch.worker_ids):
                missing = sorted(
                    set(batch.worker_ids) - {worker.worker_id for worker in returned}
                )
                missing_text = ", ".join(str(worker_id) for worker_id in missing)
                self.io.print(
                    f"[Training] Return warning for request #{batch.batch_id}: "
                    f"{len(batch.worker_ids) - len(returned)} trainee(s) did not "
                    f"rejoin the roster"
                    f"{f' ({missing_text})' if missing_text else ''}."
                )
        self._reconcile_training_flags()

    def _process_staffing_returns(self, year: int, season: int) -> None:
        """Return visiting medical staff to their home island at contract end."""
        if not self.staffing:
            return
        player_map = {p.player_id: p for p in self.players}
        returned = self.staffing.process_returns(year, season)
        for contract in returned:
            provider = player_map.get(contract.provider_id)
            requester = player_map.get(contract.requester_id)
            if not provider:
                continue
            # Return worker IDs to the provider's workforce active pool
            for wid in contract.staff_worker_ids:
                w = next(
                    (w for w in provider.workforce.workers if w.worker_id == wid), None
                )
                if w is not None:
                    # Re-activate the worker (they were marked as on_contract)
                    w.on_contract = False
            provider_name = provider.name if provider else f"Player {contract.provider_id}"
            host_name = requester.name if requester else f"Player {contract.requester_id}"
            self.io.print(
                f"\n[Staffing] Contract #{contract.contract_id} complete: "
                f"{contract.staff_count}× {contract.profession} returned "
                f"from {host_name} to {provider_name}."
            )

    def compute_summary(self) -> GameSummary:
        prices = self.market.current_prices()
        final_tick = max(0, self.config.num_years * len(SEASONS) - 1)
        rankings = sorted(
            [
                (p, p.total_wealth(prices, self.loan_ledger, CAPITAL_CATALOGUE, final_tick))
                for p in self.players
            ],
            key=lambda x: x[1],
            reverse=True,
        )
        return GameSummary(
            winner=rankings[0][0],
            final_rankings=rankings,
            deal_count=len(self.ledger.deals),
            price_history=self.market.price_history,
            money_supply=list(self._money_supply_history),
            resource_flow=self.resource_flow,
            brownout_count=sum(getattr(p, "_brownout_count", 0) for p in self.players),
            ce_factor_samples=list(self._ce_factor_samples),
        )

    def _record_ce_factor_samples(self) -> None:
        for player in self.players:
            if player.ce_manager_count() > 0:
                self._ce_factor_samples.append(player.ce_manager_efficiency_multiplier())

    def _year_end_summary(self, year: int, prices: dict[ResourceType, float],
                          current_tick: int) -> str:
        sym = CURRENCY_SYMBOL
        lines = [f"\n{'*'*50}", f"  End of Year {year + 1} — Leaderboard", f"{'*'*50}"]
        ranked = sorted(
            self.players,
            key=lambda p: p.total_wealth(
                prices, self.loan_ledger, CAPITAL_CATALOGUE, current_tick
            ),
            reverse=True,
        )
        for i, p in enumerate(ranked, 1):
            ws = p.workforce.summary()
            lines.append(
                f"  {i}. {p.name} ({p.role_names()}) — "
                f"{p.total_wealth(prices, self.loan_ledger, CAPITAL_CATALOGUE, current_tick):.1f} {sym}  "
                f"[workers: {ws['active']}/{ws['total']}, pop: {p.population}, "
                f"eff: {ws['avg_efficiency_pct']}%]"
            )
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Save / Load
    # ------------------------------------------------------------------

    def _auto_save(self, completed_year: int, next_season: int) -> None:
        try:
            self.save(self.save_path, resume_year=completed_year, resume_season=next_season)
        except Exception:
            pass

    def save(self, path: str, resume_year: int = 0, resume_season: int = 0) -> None:
        if resume_season >= len(SEASONS):
            resume_year += 1
            resume_season = 0

        state = {
            "save_version": SAVE_VERSION,
            "save_id": str(uuid.uuid4()),
            "resume_year": resume_year,
            "resume_season": resume_season,
            "config": {
                "num_years": self.config.num_years,
                "starting_dollops": self.config.starting_dollops,
                "event_charts_path": self.config.event_charts_path,
                "player_specs": [
                    {"name": s.name, "role_names": s.role_names, "is_human": s.is_human}
                    for s in self.config.player_specs
                ],
            },
            "players": [self._serialise_player(p) for p in self.players],
            "owners": [owner.to_dict() for owner in self.owners.values()],
            "market": self._serialise_market(),
            "training": self._serialise_training(),
            "capital_negotiations": self._serialise_capital_negotiations(),
            "order_book": self.order_book.to_dict(),
            "transfer_offers": [offer.to_dict() for offer in self.transfer_offers],
            "staffing": self._serialise_staffing(),
            "loan_ledger": self._serialise_loans(),
            "lease_ledger": self._serialise_leases(),
            "storage_contract_ledger": self._serialise_storage_contracts(),
            "damage_counters": {
                str(k): v for k, v in self.turn_manager._damage_counters.items()
            } if self.turn_manager else {},
        }
        Path(path).write_text(json.dumps(state, indent=2))

    def _serialise_player(self, p: Player) -> dict:
        return {
            "player_id": p.player_id,
            "name": p.name,
            "role_names": [r.name for r in p.roles],
            "is_human": p.is_human,
            "dollops": p.dollops,
            "household_cash": p.household_cash,
            "production_capacity": p.production_capacity,
            "population": p.population,
            "inventory": {r.value: p.inventory.get(r) for r in ResourceType if p.inventory.get(r) > 0},
            "spoilage_buckets": {
                resource: [dict(bucket) for bucket in buckets]
                for resource, buckets in p.spoilage_buckets.items()
            },
            "wealth_history": p.wealth_history,
            "capital_units": {
                item_id: [u.to_dict() for u in units]
                for item_id, units in p.capital_units.items()
            },
            # Legacy aggregate views kept for back-compat readers; derived from
            # capital_units above and re-migrated into units on load.
            "capital_inventory": dict(p.capital_inventory),
            "capital_acquired_ticks": {
                item_id: list(ticks) for item_id, ticks in p.capital_acquired_ticks.items()
            },
            "capital_in_transit": list(p.capital_in_transit),
            "capital_warranties": dict(p.capital_warranties),
            "failed_capital": dict(p.failed_capital),
            "capital_repair_in_progress": list(p.capital_repair_in_progress),
            "active_patents": {k: list(v) for k, v in p.active_patents.items()},
            "personal_cash": p.personal_cash,
            "holdings": dict(p.holdings),
            "cap_table": p.cap_table.to_dict() if p.cap_table is not None else None,
            "owner_id": p.owner_id,
            "shareholder_loans": dict(p.shareholder_loans),
            "ce_history": list(p._normalised_ce_history()),
            "ce_penalty": float(getattr(p, "ce_penalty", 0.0)),
            "season_revenue": round(getattr(p, "_season_revenue", 0.0), 2),
            "season_costs": round(getattr(p, "_season_costs", 0.0), 2),
            "pl_history": list(getattr(p, "_pl_history", [])),
            "workforce": {
                "next_id": p.workforce._next_id,
                "workers": [
                    {
                        "worker_id": w.worker_id,
                        "training_level": w.training_level,
                        "experience_seasons": w.experience_seasons,
                        "in_training": w.in_training,
                        "on_contract": w.on_contract,
                        "absent_seasons": w.absent_seasons,
                        "settling_seasons": w.settling_seasons,
                        "age_seasons": w.age_seasons,
                        "has_mba": w.has_mba,
                        "profession": w.profession,
                        "engineer_specialty": w.engineer_specialty,
                    }
                    for w in p.workforce.workers
                ],
            },
        }

    def _serialise_market(self) -> dict:
        return {
            "supply": {r.value: v for r, v in self.market.supply.items()},
            "demand": {r.value: v for r, v in self.market.demand.items()},
            "shocks": [
                {"resource": s.resource.value, "multiplier": s.multiplier, "remaining": s.seasons_remaining}
                for s in self.market._shocks
            ],
            "price_history": [
                {"year": snap.year, "season": snap.season,
                 "prices": {r.value: p for r, p in snap.prices.items()}}
                for snap in self.market.price_history
            ],
        }

    def _serialise_capital_negotiations(self) -> dict:
        ledger = self.capital_negotiations or CapitalNegotiationLedger()
        return {
            "next_id": ledger._next_id,
            "negotiations": [
                {
                    "negotiation_id": n.negotiation_id,
                    "buyer_id": n.buyer_id,
                    "manufacturer_id": n.manufacturer_id,
                    "item_id": n.item_id,
                    "maintenance_term_years": n.maintenance_term_years,
                    "predictive_maintenance": n.predictive_maintenance,
                    "spares_kits": n.spares_kits,
                    "expedited_eligible": n.expedited_eligible,
                    "financing": n.financing,
                    "list_price": n.list_price,
                    "recommended_total": n.recommended_total,
                    "buyer_offer": n.buyer_offer,
                    "units_required": n.units_required,
                    "units_short_at_order": n.units_short_at_order,
                    "counter_total": n.counter_total,
                    "status": n.status.value,
                    "awaiting_id": n.awaiting_id,
                }
                for n in ledger.negotiations
            ],
        }

    def _serialise_training(self) -> dict:
        return {
            "next_id": self.training._next_id,
            "requests": [
                {
                    "batch_id": r.batch_id,
                    "requester_id": r.requester_id,
                    "worker_ids": r.worker_ids,
                    "educator_id": r.educator_id,
                    "transporter_id": r.transporter_id,
                    "dollops_to_educator": r.dollops_to_educator,
                    "dollops_to_transporter": r.dollops_to_transporter,
                    "target_profession": r.target_profession,
                    "engineer_specialty": r.engineer_specialty,
                    "duration_seasons": r.duration_seasons,
                    "settling_seasons_on_return": r.settling_seasons_on_return,
                    "proposed_year": r.proposed_year,
                    "proposed_season": r.proposed_season,
                    "status": r.status.value,
                    "dispatched_year": r.dispatched_year,
                    "dispatched_season": r.dispatched_season,
                    "return_year": r.return_year,
                    "return_season": r.return_season,
                    "transport_mode": r.transport_mode,
                    "tickets_supplied_by_requester": r.tickets_supplied_by_requester,
                    "counter_message": r.counter_message,
                    "priority": r.priority,
                    "decline_reason": r.decline_reason,
                    "decline_year": r.decline_year,
                    "decline_season": r.decline_season,
                    "original_dollops_to_educator": r.original_dollops_to_educator,
                    "decision_acknowledged": r.decision_acknowledged,
                    "student_loan_requested": r.student_loan_requested,
                    "loan_financed": r.loan_financed,
                }
                for r in self.training.all_requests()
            ],
        }

    def _serialise_staffing(self) -> dict:
        if not self.staffing:
            return {"next_id": 0, "contracts": []}
        return {
            "next_id": self.staffing._next_id,
            "contracts": [
                {
                    "contract_id": c.contract_id,
                    "requester_id": c.requester_id,
                    "provider_id": c.provider_id,
                    "profession": c.profession,
                    "staff_count": c.staff_count,
                    "duration_seasons": c.duration_seasons,
                    "fee_total": c.fee_total,
                    "tickets_required": c.tickets_required,
                    "tickets_supplied_by_requester": c.tickets_supplied_by_requester,
                    "status": c.status.value,
                    "proposed_year": c.proposed_year,
                    "proposed_season": c.proposed_season,
                    "dispatched_year": c.dispatched_year,
                    "dispatched_season": c.dispatched_season,
                    "return_year": c.return_year,
                    "return_season": c.return_season,
                    "staff_worker_ids": c.staff_worker_ids,
                    "counter_fee": c.counter_fee,
                    "counter_message": c.counter_message,
                    "decline_reason": c.decline_reason,
                    "decision_acknowledged": c.decision_acknowledged,
                    "original_fee": c.original_fee,
                }
                for c in self.staffing.all_contracts()
            ],
        }

    def _serialise_loans(self) -> dict:
        return {
            "next_id": self.loan_ledger._next_id,
            "loans": [
                {
                    "loan_id": l.loan_id,
                    "borrower_id": l.borrower_id,
                    "lender_id": l.lender_id,
                    "principal": l.principal,
                    "interest_rate": l.interest_rate,
                    "issued_year": l.issued_year,
                    "issued_season": l.issued_season,
                    "maturity_year": l.maturity_year,
                    "maturity_season": l.maturity_season,
                    "term_years": l.term_years,
                    "status": l.status.value,
                    "rolled_over_from_loan_id": l.rolled_over_from_loan_id,
                    "rolled_over_from_loan_ids": list(l.rolled_over_from_loan_ids),
                    "rolled_over_to_loan_id": l.rolled_over_to_loan_id,
                    "own_committed": l.own_committed,
                    "external_funded": l.external_funded,
                    "posted_at_issue": l.posted_at_issue,
                    "reserve_ratio_at_issue": l.reserve_ratio_at_issue,
                    "collateral_item_id": l.collateral_item_id,
                    "secured": l.secured,
                }
                for l in self.loan_ledger.all_loans()
            ],
        }

    def _serialise_leases(self) -> dict:
        return {
            "next_id": self.lease_ledger._next_id,
            "leases": [
                {
                    "lease_id": l.lease_id,
                    "item_id": l.item_id,
                    "lessee_id": l.lessee_id,
                    "lessor_id": l.lessor_id,
                    "started_year": l.started_year,
                    "started_season": l.started_season,
                    "term_years": l.term_years,
                    "annual_payment": l.annual_payment,
                    "buyout_payment": l.buyout_payment,
                    "locked_lease_rate": l.locked_lease_rate,
                    "payments_made": l.payments_made,
                    "last_payment_year": l.last_payment_year,
                    "status": l.status.value,
                    "repossessed_year": l.repossessed_year,
                    "repossessed_season": l.repossessed_season,
                    "return_year": l.return_year,
                    "return_season": l.return_season,
                }
                for l in self.lease_ledger.all_leases()
            ],
        }

    def _serialise_storage_contracts(self) -> dict:
        ledger = self.storage_contract_ledger or StorageContractLedger()
        return {
            "next_id": ledger._next_id,
            "contracts": [
                {
                    "contract_id": contract.contract_id,
                    "transporter_id": contract.transporter_id,
                    "renter_id": contract.renter_id,
                    "item_id": contract.item_id,
                    "resource": contract.resource,
                    "capacity": contract.capacity,
                    "fee_per_season": contract.fee_per_season,
                    "started_year": contract.started_year,
                    "started_season": contract.started_season,
                    "status": contract.status.value,
                    "payments_made": contract.payments_made,
                    "last_payment_year": contract.last_payment_year,
                    "last_payment_season": contract.last_payment_season,
                    "ended_year": contract.ended_year,
                    "ended_season": contract.ended_season,
                }
                for contract in ledger.contracts
            ],
        }

    @classmethod
    def load(cls, path: str, io_adapter) -> "Game":
        from ..models.market import PriceShock, PriceSnapshot
        data = json.loads(Path(path).read_text())
        save_version = int(data.get("save_version", 0))
        if save_version < SAVE_VERSION:
            raise ValueError(
                f"Save version {save_version} predates per-island owner books; "
                f"expected version {SAVE_VERSION}."
            )

        cfg_data = data["config"]
        specs = [
            PlayerSpec(name=s["name"], role_names=s["role_names"], is_human=s["is_human"])
            for s in cfg_data["player_specs"]
        ]
        config = GameConfig(
            player_specs=specs,
            num_years=cfg_data["num_years"],
            starting_dollops=cfg_data.get("starting_dollops", STARTING_DOLLOPS),
            event_charts_path=cfg_data.get("event_charts_path"),
        )
        game = cls(config, io_adapter, save_path=path)
        game.owners = {
            owner.owner_id: owner
            for owner in (
                Owner.from_dict(od) for od in data.get("owners", [])
            )
        }
        if not game.owners:
            raise ValueError("Save is missing owner records.")

        for pd in data["players"]:
            roles = [ROLES[rn] for rn in pd["role_names"]]
            p = Player(
                player_id=pd["player_id"],
                name=pd["name"],
                roles=roles,
                dollops=pd["dollops"],
                household_cash=pd.get("household_cash", 0.0),
                is_human=pd["is_human"],
                wealth_history=pd.get("wealth_history", []),
                production_capacity=pd.get("production_capacity", 0.5),
                population=pd.get("population", STARTING_POPULATION),
                capital_units=_migrate_capital_units(pd),
                capital_in_transit=_migrate_capital_in_transit(
                    pd.get("capital_in_transit", [])
                ),
                capital_repair_in_progress=_migrate_capital_in_transit(
                    pd.get("capital_repair_in_progress", [])
                ),
                active_patents={k: list(v) for k, v in pd.get("active_patents", {}).items()},
                personal_cash=pd.get("personal_cash", 0.0),
                holdings=dict(pd.get("holdings", {})),
                cap_table=(
                    CapTable.from_dict(pd["cap_table"])
                    if pd.get("cap_table") is not None else None
                ),
                owner_id=pd.get("owner_id"),
                shareholder_loans=dict(pd.get("shareholder_loans", {})),
                ce_history=list(pd.get("ce_history", [0.0] * len(SEASONS))),
                ce_penalty=float(pd.get("ce_penalty", 0.0)),
                spoilage_buckets={
                    str(resource): [
                        {"acquired_tick": int(bucket.get("acquired_tick", 0)),
                         "qty": int(bucket.get("qty", 0))}
                        for bucket in buckets
                        if int(bucket.get("qty", 0)) > 0
                    ]
                    for resource, buckets in pd.get("spoilage_buckets", {}).items()
                },
            )
            if p.owner_id and p.owner_id in game.owners:
                p.owner = game.owners[p.owner_id]
            for r_str, qty in pd.get("inventory", {}).items():
                # Save-migration: the consumable "LaboratoryEquipment" was
                # renamed to "Reagents" (2026-06-02); fold legacy keys forward.
                r_str = LEGACY_RESOURCE_IDS.get(r_str, r_str)
                p.receive_resources(
                    ResourceType(r_str), qty, track_spoilage=False
                )
            p._season_revenue = float(pd.get("season_revenue", 0.0))
            p._season_costs = float(pd.get("season_costs", 0.0))
            p._pl_history = list(pd.get("pl_history", []))[-4:]
            wf_data = pd.get("workforce", {})
            p.workforce._next_id = wf_data.get("next_id", 0)
            p.workforce.workers = [
                Worker(
                    worker_id=w["worker_id"],
                    training_level=w["training_level"],
                    experience_seasons=w["experience_seasons"],
                    in_training=w.get("in_training", False),
                    on_contract=w.get("on_contract", False),
                    absent_seasons=w.get("absent_seasons", 0),
                    settling_seasons=w.get("settling_seasons", 0),
                    age_seasons=w.get("age_seasons", 0),
                    has_mba=w.get("has_mba", False),
                    profession=w.get("profession", Profession.UNSKILLED.value),
                    engineer_specialty=w.get("engineer_specialty", ""),
                )
                for w in wf_data.get("workers", [])
            ]
            game.players.append(p)

        md = data["market"]
        game.market = Market()
        game.market.supply = {ResourceType(k): v for k, v in md.get("supply", {}).items()}
        game.market.demand = {ResourceType(k): v for k, v in md.get("demand", {}).items()}
        from ..models.market import PriceShock, PriceSnapshot
        game.market._shocks = [
            PriceShock(ResourceType(s["resource"]), s["multiplier"], s["remaining"])
            for s in md.get("shocks", [])
        ]
        game.market.price_history = [
            PriceSnapshot(
                year=snap["year"],
                season=snap["season"],
                prices={ResourceType(r): p for r, p in snap["prices"].items()},
            )
            for snap in md.get("price_history", [])
        ]

        game.ledger = DealLedger()
        game.loan_ledger = LoanLedger()
        ld = data.get("loan_ledger", {})
        game.loan_ledger._next_id = ld.get("next_id", 0)
        for loan_d in ld.get("loans", []):
            rolled_from_id = loan_d.get("rolled_over_from_loan_id")
            rolled_from_ids = list(loan_d.get("rolled_over_from_loan_ids", []))
            if rolled_from_id is not None and not rolled_from_ids:
                rolled_from_ids = [rolled_from_id]
            loan = Loan(
                loan_id=loan_d["loan_id"],
                borrower_id=loan_d["borrower_id"],
                lender_id=loan_d["lender_id"],
                principal=loan_d["principal"],
                interest_rate=loan_d["interest_rate"],
                issued_year=loan_d["issued_year"],
                issued_season=loan_d["issued_season"],
                maturity_year=loan_d["maturity_year"],
                maturity_season=loan_d["maturity_season"],
                status=LoanStatus(loan_d["status"]),
                term_years=loan_d.get(
                    "term_years",
                    max(1, loan_d["maturity_year"] - loan_d["issued_year"]),
                ),
                rolled_over_from_loan_id=rolled_from_id,
                rolled_over_from_loan_ids=rolled_from_ids,
                rolled_over_to_loan_id=loan_d.get("rolled_over_to_loan_id"),
                own_committed=loan_d.get("own_committed", 0.0),
                external_funded=loan_d.get("external_funded", 0.0),
                posted_at_issue=loan_d.get("posted_at_issue", 0.0),
                reserve_ratio_at_issue=loan_d.get("reserve_ratio_at_issue", 0.0),
                collateral_item_id=loan_d.get("collateral_item_id"),
                secured=bool(loan_d.get("secured", False)),
            )
            game.loan_ledger.loans.append(loan)
        game.lease_ledger = LeaseLedger()
        lease_data = data.get("lease_ledger", {})
        game.lease_ledger._next_id = lease_data.get("next_id", 0)
        for lease_d in lease_data.get("leases", []):
            game.lease_ledger.leases.append(Lease(
                lease_id=lease_d["lease_id"],
                item_id=lease_d["item_id"],
                lessee_id=lease_d["lessee_id"],
                lessor_id=lease_d["lessor_id"],
                started_year=lease_d["started_year"],
                started_season=lease_d["started_season"],
                term_years=lease_d["term_years"],
                annual_payment=lease_d["annual_payment"],
                buyout_payment=lease_d["buyout_payment"],
                locked_lease_rate=lease_d["locked_lease_rate"],
                payments_made=lease_d.get("payments_made", 0),
                last_payment_year=lease_d.get("last_payment_year", -1),
                status=LeaseStatus(lease_d.get("status", LeaseStatus.ACTIVE.value)),
                repossessed_year=lease_d.get("repossessed_year", -1),
                repossessed_season=lease_d.get("repossessed_season", -1),
                return_year=lease_d.get("return_year", -1),
                return_season=lease_d.get("return_season", -1),
            ))
        game.storage_contract_ledger = StorageContractLedger()
        storage_data = data.get("storage_contract_ledger", {})
        game.storage_contract_ledger._next_id = storage_data.get("next_id", 0)
        for contract_d in storage_data.get("contracts", []):
            game.storage_contract_ledger.contracts.append(StorageContract(
                contract_id=contract_d["contract_id"],
                transporter_id=contract_d["transporter_id"],
                renter_id=contract_d["renter_id"],
                item_id=contract_d["item_id"],
                resource=contract_d["resource"],
                capacity=contract_d["capacity"],
                fee_per_season=contract_d["fee_per_season"],
                started_year=contract_d["started_year"],
                started_season=contract_d["started_season"],
                status=StorageContractStatus(contract_d.get(
                    "status", StorageContractStatus.ACTIVE.value
                )),
                payments_made=contract_d.get("payments_made", 0),
                last_payment_year=contract_d.get("last_payment_year", -1),
                last_payment_season=contract_d.get("last_payment_season", -1),
                ended_year=contract_d.get("ended_year", -1),
                ended_season=contract_d.get("ended_season", -1),
            ))
        game.training = TrainingRegistry()
        td = data.get("training", {})
        game.training._next_id = td.get("next_id", 0)
        player_by_id = {player.player_id: player for player in game.players}
        for rd in td.get("requests", []):
            target_profession = rd.get(
                "target_profession", Profession.UNSKILLED.value
            )
            if "settling_seasons_on_return" in rd:
                settling_on_return = rd.get("settling_seasons_on_return", 0)
            else:
                campus = player_by_id.get(rd.get("educator_id"))
                settling_on_return = settling_seasons_on_return(
                    target_profession,
                    has_technical_workshop=(
                        campus_has_technical_workshop(campus)
                        if campus is not None else True
                    ),
                )
            req = TrainingRequest(
                batch_id=rd["batch_id"],
                requester_id=rd["requester_id"],
                worker_ids=rd["worker_ids"],
                educator_id=rd["educator_id"],
                transporter_id=rd.get("transporter_id"),
                dollops_to_educator=rd.get("dollops_to_educator", 0),
                dollops_to_transporter=rd.get("dollops_to_transporter", 0),
                target_profession=target_profession,
                engineer_specialty=rd.get("engineer_specialty", ""),
                duration_seasons=rd.get("duration_seasons", 0),
                settling_seasons_on_return=settling_on_return,
                proposed_year=rd.get("proposed_year", 0),
                proposed_season=rd.get("proposed_season", 0),
                status=TrainingStatus(rd["status"]),
                dispatched_year=rd.get("dispatched_year", -1),
                dispatched_season=rd.get("dispatched_season", -1),
                return_year=rd.get("return_year", -1),
                return_season=rd.get("return_season", -1),
                transport_mode=rd.get("transport_mode", "transporter"),
                tickets_supplied_by_requester=rd.get("tickets_supplied_by_requester", 0),
                counter_message=rd.get("counter_message", ""),
                priority=rd.get("priority", 0),
                decline_reason=rd.get("decline_reason", ""),
                decline_year=rd.get("decline_year", -1),
                decline_season=rd.get("decline_season", -1),
                original_dollops_to_educator=rd.get(
                    "original_dollops_to_educator",
                    rd.get("dollops_to_educator", 0),
                ),
                decision_acknowledged=rd.get("decision_acknowledged", False),
                student_loan_requested=bool(rd.get("student_loan_requested", False)),
                loan_financed=rd.get("loan_financed"),
            )
            game.training._requests.append(req)

        game.capital_negotiations = CapitalNegotiationLedger()
        cnd = data.get("capital_negotiations", {})
        game.capital_negotiations._next_id = cnd.get("next_id", 0)
        for nd in cnd.get("negotiations", []):
            game.capital_negotiations.negotiations.append(CapitalOrderNegotiation(
                negotiation_id=nd["negotiation_id"],
                buyer_id=nd["buyer_id"],
                manufacturer_id=nd["manufacturer_id"],
                item_id=nd["item_id"],
                maintenance_term_years=nd.get("maintenance_term_years", 0),
                predictive_maintenance=bool(nd.get("predictive_maintenance", False)),
                spares_kits=nd.get("spares_kits", 0),
                expedited_eligible=bool(nd.get("expedited_eligible", False)),
                financing=bool(nd.get("financing", False)),
                list_price=nd.get("list_price", 0.0),
                recommended_total=nd.get("recommended_total", 0.0),
                buyer_offer=nd.get("buyer_offer", 0.0),
                units_required=nd.get("units_required", 0),
                units_short_at_order=nd.get("units_short_at_order", 0),
                counter_total=nd.get("counter_total"),
                status=CapitalNegotiationStatus(nd.get(
                    "status", CapitalNegotiationStatus.PROPOSED.value
                )),
                awaiting_id=nd.get("awaiting_id"),
            ))
        game.order_book = ManufacturerOrderBook.from_dict(data.get("order_book"))
        game.transfer_offers = [
            WorkerTransferOffer.from_dict(raw)
            for raw in data.get("transfer_offers", [])
        ]

        game._resume_year = data.get("resume_year", 0)
        game._resume_season = data.get("resume_season", 0)

        # Staffing registry (added 2026-05-28; older saves won't have this section)
        game.staffing = StaffingRegistry()
        staffing_data = data.get("staffing", {})
        game.staffing._next_id = staffing_data.get("next_id", 0)
        for cd in staffing_data.get("contracts", []):
            from ..models.staffing import StaffingContract, StaffingStatus
            contract = StaffingContract(
                contract_id=cd["contract_id"],
                requester_id=cd["requester_id"],
                provider_id=cd["provider_id"],
                profession=cd["profession"],
                staff_count=cd["staff_count"],
                duration_seasons=cd["duration_seasons"],
                fee_total=cd["fee_total"],
                tickets_required=cd["tickets_required"],
                tickets_supplied_by_requester=cd.get("tickets_supplied_by_requester", 0),
                status=StaffingStatus(cd["status"]),
                proposed_year=cd.get("proposed_year", -1),
                proposed_season=cd.get("proposed_season", -1),
                dispatched_year=cd.get("dispatched_year", -1),
                dispatched_season=cd.get("dispatched_season", -1),
                return_year=cd.get("return_year", -1),
                return_season=cd.get("return_season", -1),
                staff_worker_ids=cd.get("staff_worker_ids", []),
                counter_fee=cd.get("counter_fee", 0.0),
                counter_message=cd.get("counter_message", ""),
                decline_reason=cd.get("decline_reason", ""),
                decision_acknowledged=cd.get("decision_acknowledged", False),
                original_fee=cd.get("original_fee", cd["fee_total"]),
            )
            game.staffing._contracts.append(contract)

        charts = (
            EventChartLoader.from_yaml(config.event_charts_path)
            if config.event_charts_path
            else EventChartLoader.default_charts()
        )
        game.event_resolver = SeasonEventResolver(charts)
        production = ProductionEngine()
        trading = TradingEngine(game.market, game.ledger, game.players)
        game.turn_manager = TurnManager(
            game.players, production, trading, game.market, io_adapter, game.training,
            game.staffing, game.loan_ledger, game.lease_ledger,
            storage_contract_ledger=game.storage_contract_ledger,
        )
        game.turn_manager._damage_counters = {
            int(k): v for k, v in data.get("damage_counters", {}).items()
        }

        return game
