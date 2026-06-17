from __future__ import annotations
import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from ..models.player import Player
from ..models.equity import CapTable, AUCTIONED_SHARES
from ..models.market import Market
from ..models.deal import DealLedger
from ..models.loan import LoanLedger, Loan, LoanStatus
from ..models.lease import LeaseLedger, Lease, LeaseStatus
from ..models.resource import ResourceType
from ..models.role import ROLES
from ..models.profession import Profession, band_of
from ..models.training import TrainingRegistry, TrainingRequest, TrainingStatus
from ..models.staffing import StaffingRegistry, StaffingContract, StaffingStatus
from ..models.workforce import Workforce, Worker
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
    EQUIPMENT_FAILURE_PROB_BY_AGE_YEAR,
    EQUIPMENT_FAILURE_REPAIR_FRACTION,
    EQUIPMENT_REPAIR_AIR_FREIGHT,
    EQUIPMENT_REPAIR_SHIP_FREIGHT,
    EQUIPMENT_WARRANTY_ANNUAL_RATE,
    BASE_BIRTH_RATE,
    STARTING_PRODUCTION_CAPACITY,
    STARTING_POPULATION,
    TOTAL_STARTING_DOLLOPS, TOTAL_STARTING_POPULATION,
    CURRENCY_SYMBOL,
    BASE_PRICES,
    PAYROLL_WAGE_BY_BAND,
    HOUSEHOLD_ACTIVITY_STIMULUS_PER_CAPITA,
)
from ..constants_capacity import CAPITAL_CATALOGUE

SAVE_VERSION = 7

# Renamed resources: old save inventory key -> current key (2026-06-02).
LEGACY_RESOURCE_IDS: dict[str, str] = {
    "LaboratoryEquipment": "Reagents",
}

LEGACY_CAPITAL_ITEM_IDS: dict[str, str] = {
    "educator.apprenticeship_programme": "educator.technical_workshop",
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


class Game:
    def __init__(self, config: GameConfig, io_adapter, save_path: str = "island_traders_save.json"):
        self.config = config
        self.io = io_adapter
        self.save_path = save_path
        self.players: list[Player] = []
        self.market: Market | None = None
        self.ledger: DealLedger | None = None
        self.loan_ledger: LoanLedger | None = None
        self.lease_ledger: LeaseLedger | None = None
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

    def setup(self) -> None:
        self.market = Market()
        self.ledger = DealLedger()
        self.loan_ledger = LoanLedger()
        self.lease_ledger = LeaseLedger()
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
        workforce_scale = 1.0

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
        self.turn_manager = TurnManager(
            self.players, production, trading, self.market, self.io, self.training,
            self.staffing, self.loan_ledger, self.lease_ledger,
        )

    def _total_money_supply(self) -> float:
        """Total liquid Dollops in circulation: every island's operating
        treasury, every investor's personal cash, and resident household cash.
        Loans, payroll, and player trades only move Dollops between these
        balances, so this is conserved except where the formula market mints
        (sell) or burns (buy) cash."""
        return sum(p.dollops + p.personal_cash + p.household_cash for p in self.players)

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
            start_season = self._resume_season if year == self._resume_year else 0
            for season_index in range(start_season, len(SEASONS)):
                self._process_training_returns(year, season_index)
                self._process_staffing_returns(year, season_index)
                self._process_retirements(year, season_index)
                self._process_capital_maintenance(year, season_index)
                self._process_payroll(year, season_index)
                self._process_household_activity_stimulus(year, season_index)
                event_results = self.event_resolver.resolve_all(
                    self.players, self.turn_manager._damage_counters, year=year,
                )
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
                self._advance_temporary_absences()
                cb = getattr(self, "after_season", None)
                if cb:
                    try:
                        cb(year, season_index)
                    except Exception:
                        pass
                self._auto_save(year, season_index + 1)
                self._money_supply_history.append(
                    round(self._total_money_supply(), 2)
                )

            prices = self.market.current_prices()
            year_end_tick = year * len(SEASONS) + (len(SEASONS) - 1)
            wealthies = [
                p.total_wealth(prices, self.loan_ledger, CAPITAL_CATALOGUE, year_end_tick)
                for p in self.players
            ]
            max_wealth = max(wealthies) if wealthies else 1.0

            for player, wealth in zip(self.players, wealthies):
                player.record_year_wealth(
                    prices, self.loan_ledger, CAPITAL_CATALOGUE, year_end_tick
                )
                wealth_ratio = wealth / max_wealth if max_wealth > 0 else 0.0
                birth_rate = BASE_BIRTH_RATE * max(0.0, 1.0 - wealth_ratio)
                new_people = max(0, round(player.population * birth_rate))
                if new_people:
                    player.population += new_people
                    self.io.print(
                        f"  [Population] {player.name}: +{new_people} people born  "
                        f"(island population now {player.population}; "
                        f"{player.available_unskilled} recruitable)"
                    )

            self.io.print(self._year_end_summary(year, prices, year_end_tick))

        Path(self.save_path).unlink(missing_ok=True)
        return self.compute_summary()

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
            # Reset transient unmaintained state at the start of the season.
            player.unmaintained_capital = {}
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

            if season == len(SEASONS) - 1:
                self._process_equipment_failures(player, current_tick, catalogue)

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
        player.capital_repair_in_progress = remaining

    def _process_equipment_warranty_premiums(
        self,
        player: Player,
        catalogue: dict[str, object],
    ) -> None:
        manufacturer = self._role_player("Manufacturer")
        if manufacturer is None or manufacturer.player_id == player.player_id:
            return
        for item_id, count in list(player.capital_warranties.items()):
            item = catalogue.get(item_id)
            owned = player.capital_inventory.get(item_id, 0)
            covered = min(count, owned)
            if item is None or covered <= 0:
                player.capital_warranties.pop(item_id, None)
                continue
            per_unit = round(item.cost * EQUIPMENT_WARRANTY_ANNUAL_RATE, 2)
            paid = 0
            for _ in range(covered):
                if player.dollops < per_unit:
                    break
                player.spend_dollops(per_unit)
                manufacturer.receive_dollops(per_unit)
                paid += 1
            if paid < count:
                if paid:
                    player.capital_warranties[item_id] = paid
                else:
                    player.capital_warranties.pop(item_id, None)
            if paid:
                self.io.print(
                    f"\n[WARRANTY] {player.name}: paid "
                    f"{CURRENCY_SYMBOL}{per_unit * paid:.2f} to "
                    f"{manufacturer.name} for {paid} × {item.name} warranty."
                )

    def _failure_probability_for_age(self, age_seasons: int) -> float:
        age_year = max(1, age_seasons // len(SEASONS) + 1)
        max_year = max(EQUIPMENT_FAILURE_PROB_BY_AGE_YEAR)
        return EQUIPMENT_FAILURE_PROB_BY_AGE_YEAR.get(
            age_year,
            EQUIPMENT_FAILURE_PROB_BY_AGE_YEAR[max_year],
        )

    def _process_equipment_failures(
        self,
        player: Player,
        current_tick: int,
        catalogue: dict[str, object],
    ) -> None:
        rng = self._capital_rng()
        for item_id, count in list(player.capital_inventory.items()):
            item = catalogue.get(item_id)
            if item is None:
                continue
            warranted = min(player.capital_warranties.get(item_id, 0), count)
            failed = min(player.failed_capital.get(item_id, 0), count)
            in_service_uninsured = max(0, count - warranted - failed)
            if in_service_uninsured <= 0:
                continue
            ticks = list(player.capital_acquired_ticks.get(item_id, []))
            if len(ticks) < count:
                ticks.extend([0] * (count - len(ticks)))
            candidate_ticks = ticks[warranted:warranted + in_service_uninsured]
            failures = 0
            for acquired_tick in candidate_ticks:
                age = max(0, current_tick - acquired_tick)
                if rng.random() < self._failure_probability_for_age(age):
                    failures += 1
            for _ in range(failures):
                if player.mark_capital_failed(item_id, 1):
                    self.io.print(
                        f"\n[CAPITAL FAILURE] {player.name}: 1 × {item.name} "
                        f"failed and is down until repaired."
                    )
                    self._attempt_capital_repair(player, item, current_tick)

    def _attempt_pending_capital_repairs(
        self,
        player: Player,
        current_tick: int,
        catalogue: dict[str, object],
    ) -> None:
        for item_id, failed in list(player.failed_capital.items()):
            unresolved = failed - self._repair_in_progress_count(player, item_id)
            if unresolved <= 0:
                continue
            item = catalogue.get(item_id)
            if item is None:
                continue
            for _ in range(unresolved):
                if not self._attempt_capital_repair(player, item, current_tick):
                    break

    def _has_air_repair_capacity(self) -> bool:
        transporter = self._role_player("Transporter")
        if transporter is None:
            return False
        return transporter.effective_capital_inventory().get(
            "transporter.cargo_plane", 0
        ) > 0

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
    ) -> bool:
        manufacturer = self._role_player("Manufacturer")
        repair_fee = round(item.cost * EQUIPMENT_FAILURE_REPAIR_FRACTION, 2)
        air = self._has_air_repair_capacity()
        freight_qty = (
            EQUIPMENT_REPAIR_AIR_FREIGHT if air else EQUIPMENT_REPAIR_SHIP_FREIGHT
        )
        if player.dollops < repair_fee:
            return False
        if player.inventory.get(ResourceType.FREIGHT) < freight_qty:
            return False

        player.spend_dollops(repair_fee)
        if manufacturer is not None:
            manufacturer.receive_dollops(repair_fee)
        player.give_resources(ResourceType.FREIGHT, freight_qty)
        self._credit_freight_to_transporter(freight_qty)

        if air:
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
                batch.worker_ids, batch.target_profession, batch.engineer_specialty
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
        )

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
            "market": self._serialise_market(),
            "training": self._serialise_training(),
            "staffing": self._serialise_staffing(),
            "loan_ledger": self._serialise_loans(),
            "lease_ledger": self._serialise_leases(),
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
            "wealth_history": p.wealth_history,
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
            "shareholder_loans": dict(p.shareholder_loans),
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

    @classmethod
    def load(cls, path: str, io_adapter) -> "Game":
        from ..models.market import PriceShock, PriceSnapshot
        data = json.loads(Path(path).read_text())

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
                capital_inventory=_migrate_capital_inventory(
                    pd.get("capital_inventory", {})
                ),
                capital_acquired_ticks=_migrate_capital_ticks(
                    pd.get("capital_acquired_ticks", {})
                ),
                capital_in_transit=_migrate_capital_in_transit(
                    pd.get("capital_in_transit", [])
                ),
                capital_warranties=_migrate_capital_inventory(
                    pd.get("capital_warranties", {})
                ),
                failed_capital=_migrate_capital_inventory(
                    pd.get("failed_capital", {})
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
                shareholder_loans=dict(pd.get("shareholder_loans", {})),
            )
            for r_str, qty in pd.get("inventory", {}).items():
                # Save-migration: the consumable "LaboratoryEquipment" was
                # renamed to "Reagents" (2026-06-02); fold legacy keys forward.
                r_str = LEGACY_RESOURCE_IDS.get(r_str, r_str)
                p.receive_resources(ResourceType(r_str), qty)
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
        game.training = TrainingRegistry()
        td = data.get("training", {})
        game.training._next_id = td.get("next_id", 0)
        for rd in td.get("requests", []):
            req = TrainingRequest(
                batch_id=rd["batch_id"],
                requester_id=rd["requester_id"],
                worker_ids=rd["worker_ids"],
                educator_id=rd["educator_id"],
                transporter_id=rd.get("transporter_id"),
                dollops_to_educator=rd.get("dollops_to_educator", 0),
                dollops_to_transporter=rd.get("dollops_to_transporter", 0),
                target_profession=rd.get("target_profession", Profession.UNSKILLED.value),
                engineer_specialty=rd.get("engineer_specialty", ""),
                duration_seasons=rd.get("duration_seasons", 0),
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
            )
            game.training._requests.append(req)

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
        )
        game.turn_manager._damage_counters = {
            int(k): v for k, v in data.get("damage_counters", {}).items()
        }

        return game
