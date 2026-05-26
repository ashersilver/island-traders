from __future__ import annotations
import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from ..models.player import Player
from ..models.market import Market
from ..models.deal import DealLedger
from ..models.loan import LoanLedger, Loan, LoanStatus
from ..models.lease import LeaseLedger, Lease, LeaseStatus
from ..models.resource import ResourceType
from ..models.role import ROLES
from ..models.profession import Profession, band_of
from ..models.training import TrainingRegistry, TrainingRequest, TrainingStatus
from ..models.workforce import Workforce, Worker
from ..engine.events import EventChartLoader, SeasonEventResolver
from ..engine.production import ProductionEngine
from ..engine.trading import TradingEngine
from ..engine.turn import TurnManager
from ..constants import (
    SEASONS, STARTING_DOLLOPS, STARTING_INVENTORY,
    STARTING_WORKFORCE, STARTING_TRAINED_FRACTION,
    STARTING_WORKERS_BY_PROFESSION,
    WORKING_LIFE_SEASONS, DEFAULT_WORKING_LIFE_SEASONS, STARTING_WORKER_AGES,
    DEFAULT_MAINTENANCE_FRACTION, STARTING_AGED_CAPITAL,
    BASE_BIRTH_RATE,
    STARTING_PRODUCTION_CAPACITY,
    STARTING_POPULATION,
    TOTAL_STARTING_DOLLOPS, TOTAL_STARTING_POPULATION,
    CURRENCY_SYMBOL,
    BASE_PRICES,
)
from ..constants_capacity import CAPITAL_CATALOGUE

SAVE_VERSION = 5

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
        self.turn_manager: TurnManager | None = None
        self._resume_year: int = 0
        self._resume_season: int = 0

    def setup(self) -> None:
        self.market = Market()
        self.ledger = DealLedger()
        self.loan_ledger = LoanLedger()
        self.lease_ledger = LeaseLedger()
        self.training = TrainingRegistry()

        num_players = len(self.config.player_specs)
        default_dollops = TOTAL_STARTING_DOLLOPS / num_players
        default_population = TOTAL_STARTING_POPULATION // num_players
        workforce_scale = 7 / num_players

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
        trading = TradingEngine(self.market, self.ledger)
        self.turn_manager = TurnManager(
            self.players, production, trading, self.market, self.io, self.training,
            self.loan_ledger, self.lease_ledger,
        )

    def run(self) -> GameSummary:
        for year in range(self._resume_year, self.config.num_years):
            start_season = self._resume_season if year == self._resume_year else 0
            for season_index in range(start_season, len(SEASONS)):
                self._process_training_returns(year, season_index)
                self._process_retirements(year, season_index)
                self._process_capital_maintenance(year, season_index)
                event_results = self.event_resolver.resolve_all(
                    self.players, self.turn_manager._damage_counters
                )
                # Optional hooks — set by the server to install/clear the
                # per-season Ready timer in simultaneous-play mode.
                cb = getattr(self, "before_season", None)
                if cb:
                    try:
                        cb(year, season_index)
                    except Exception:
                        pass
                self.turn_manager.run_season(year, season_index, event_results)
                cb = getattr(self, "after_season", None)
                if cb:
                    try:
                        cb(year, season_index)
                    except Exception:
                        pass
                self._auto_save(year, season_index + 1)

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

            # 1) Expiry — remove units past their service life (oldest first).
            for item_id in list(player.capital_inventory.keys()):
                item = catalogue.get(item_id)
                if not item or item.service_life_seasons <= 0:
                    continue
                ticks = player.capital_acquired_ticks.get(item_id, [])
                expired = sum(
                    1 for t in ticks
                    if current_tick - t >= item.service_life_seasons
                )
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

    def _process_training_returns(self, year: int, season: int) -> None:
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
                batch.worker_ids, batch.target_profession
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
            "production_capacity": p.production_capacity,
            "population": p.population,
            "inventory": {r.value: p.inventory.get(r) for r in ResourceType if p.inventory.get(r) > 0},
            "wealth_history": p.wealth_history,
            "capital_inventory": dict(p.capital_inventory),
            "capital_acquired_ticks": {
                item_id: list(ticks) for item_id, ticks in p.capital_acquired_ticks.items()
            },
            "capital_in_transit": list(p.capital_in_transit),
            "active_patents": {k: list(v) for k, v in p.active_patents.items()},
            "workforce": {
                "next_id": p.workforce._next_id,
                "workers": [
                    {
                        "worker_id": w.worker_id,
                        "training_level": w.training_level,
                        "experience_seasons": w.experience_seasons,
                        "in_training": w.in_training,
                        "settling_seasons": w.settling_seasons,
                        "age_seasons": w.age_seasons,
                        "has_mba": w.has_mba,
                        "profession": w.profession,
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
                active_patents={k: list(v) for k, v in pd.get("active_patents", {}).items()},
            )
            for r_str, qty in pd.get("inventory", {}).items():
                p.receive_resources(ResourceType(r_str), qty)
            wf_data = pd.get("workforce", {})
            p.workforce._next_id = wf_data.get("next_id", 0)
            p.workforce.workers = [
                Worker(
                    worker_id=w["worker_id"],
                    training_level=w["training_level"],
                    experience_seasons=w["experience_seasons"],
                    in_training=w.get("in_training", False),
                    settling_seasons=w.get("settling_seasons", 0),
                    age_seasons=w.get("age_seasons", 0),
                    has_mba=w.get("has_mba", False),
                    profession=w.get("profession", Profession.UNSKILLED.value),
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

        charts = (
            EventChartLoader.from_yaml(config.event_charts_path)
            if config.event_charts_path
            else EventChartLoader.default_charts()
        )
        game.event_resolver = SeasonEventResolver(charts)
        production = ProductionEngine()
        trading = TradingEngine(game.market, game.ledger)
        game.turn_manager = TurnManager(
            game.players, production, trading, game.market, io_adapter, game.training,
            game.loan_ledger, game.lease_ledger,
        )
        game.turn_manager._damage_counters = {
            int(k): v for k, v in data.get("damage_counters", {}).items()
        }

        return game
