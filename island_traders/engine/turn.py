from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from ..models.player import Player
from ..models.market import Market
from ..models.resource import ResourceType
from ..models.training import (
    TrainingRegistry, TrainingStatus, TrainingCapacityError, away_seasons,
)
from ..engine.events import EventResult
from ..engine.production import ProductionEngine
from ..engine.trading import TradingEngine
from ..engine.ai import AIStrategy
from ..models.insurance import InsurancePolicy
from ..models.loan import LoanLedger, LoanStatus, banker_quote_rate, posted_funding_rates
from ..models.lease import LeaseLedger, LeaseStatus, lease_quote
from ..models.profession import Profession, PROFESSION_LABEL, WorkerBand, band_of
from ..engine.workforce_events import apply_workplace_risks
from ..constants import (
    SEASONS, CURRENCY_SYMBOL, UNIVERSITY_CAPACITY,
    STARTING_WORKERS_BY_PROFESSION,
    MANUFACTURER_PRODUCT_LINES, MAX_CLASS_SIZE_PER_COURSE,
    TRAINEE_FOOD_ACCOM_PER_SEASON,
    MBA_RESERVE_RATIO_BASE, MBA_RESERVE_RATIO_QUALIFIED, MBA_QUALIFIED_THRESHOLD,
    INSURANCE_BASE_PREMIUM, INSURANCE_DURATION_SEASONS, LIFE_INSURANCE_DEATH_BENEFIT,
    MEDICAL_INSURANCE_INJURY_REDUCTION, WORKPLACE_RISK,
)
from ..constants_capacity import CAPITAL_CATALOGUE
from ..models.capacity import items_for_role, find_item, technical_workshop_trainee_capacity
# ActionCancelled is raised by IO adapters when the user explicitly cancels a
# prompt chain; the main action loop catches it to abort the action cleanly.
# Imported from .cli.signals (dependency-free) to avoid a circular import via
# cli/prompts.py which itself imports TurnAction from this module.
from ..cli.signals import ActionCancelled


class TurnAction(Enum):
    PRODUCE            = "produce"
    MARKET_BUY         = "market_buy"
    MARKET_SELL        = "market_sell"
    PROPOSE_DEAL       = "propose_deal"
    REQUEST_TRAINING   = "request_training"    # any player: send workers to Educator
    REVIEW_TRAINING    = "review_training"     # Educator: approve/reject requests
    ARRANGE_TRANSPORT  = "arrange_transport"   # Transporter: accept transport jobs
    RECRUIT_WORKERS    = "recruit_workers"     # draw unskilled from island population
    SELL_INSURANCE     = "sell_insurance"      # Banker: sell policy to another player
    BUY_INSURANCE      = "buy_insurance"       # any player: buy policy from Banker
    MANAGE_INSURANCE   = "manage_insurance"    # any holder: review/cancel active policies (#5)
    PURCHASE_CAPITAL   = "purchase_capital"    # any player: buy named equipment from Manufacturer
    LEASE_CAPITAL      = "lease_capital"       # any player: lease eligible equipment from the Bank
    INVEST             = "invest"              # take up an opening-catalogue item not yet owned (immediate, no transit)
    OFFER_LOAN         = "offer_loan"          # Banker: offer a loan to another player
    TAKE_LOAN          = "take_loan"           # any player: borrow from the Banker
    ROLLOVER_LOAN      = "rollover_loan"       # borrower: refinance an active loan (#6)
    VIEW_LOANS         = "view_loans"          # view outstanding loans
    PAY_LEASE          = "pay_lease"           # pay due lease annual/buyout/catch-up amount
    APPLY_PATENT       = "apply_patent"        # any producer: activate a Patent on one output
    VIEW_MARKET        = "view_market"
    VIEW_PLAYERS       = "view_players"
    INVENTORY          = "inventory"
    END_TURN           = "end_turn"


@dataclass
class TurnResult:
    player_id: int
    season: int
    year: int
    actions_taken: list[str] = field(default_factory=list)
    dollops_delta: float = 0.0
    resources_delta: dict[str, int] = field(default_factory=dict)


class TurnManager:
    def __init__(
        self,
        players: list[Player],
        production_engine: ProductionEngine,
        trading_engine: TradingEngine,
        market: Market,
        io_adapter,
        training: TrainingRegistry | None = None,
        loan_ledger: LoanLedger | None = None,
        lease_ledger: LeaseLedger | None = None,
        rng=None,
    ):
        import random as _random
        import threading as _threading
        self.players = players
        self.production = production_engine
        self.trading = trading_engine
        self.market = market
        self.io = io_adapter
        self.training = training or TrainingRegistry()
        self.loan_ledger = loan_ledger or LoanLedger()
        self.lease_ledger = lease_ledger or LeaseLedger()
        self._ai = AIStrategy()
        self._damage_counters: dict[int, int] = {}
        self._rng: _random.Random = rng if rng is not None else _random.Random()
        # Simultaneous-play hooks: when set, run_season() spawns one thread
        # per human player instead of running them sequentially. engine_lock
        # is exposed for future hardening of shared-state mutations
        # (market, trading, loans). For this first cut we rely on the GIL
        # and blocking-IO serialisation to keep things sane.
        self.parallel_mode: bool = False
        self.engine_lock: _threading.RLock = _threading.RLock()
        # Optional callback fired with player.player_id when their turn thread
        # completes (used by the server to track ready/done state).
        self.on_player_turn_complete = None

    def run_season(
        self,
        year: int,
        season_index: int,
        event_results: dict[int, EventResult],
    ) -> list[TurnResult]:
        season_name = SEASONS[season_index]
        self.market.set_season(year, season_index)
        self._process_lease_reinstatements(year, season_index)
        self._process_lease_payments(year, season_index)
        self.io.print(f"\n{'='*50}")
        self.io.print(f"  Year {year + 1}  —  {season_name}")
        self.io.print(f"{'='*50}")

        # Apply workplace injuries/fatalities before turns begin
        banker_players = [p for p in self.players if any(r.name == "Banker" for r in p.roles)]
        risk_reports = apply_workplace_risks(
            self.players, year, season_index, banker_players, rng=self._rng
        )
        for report in risk_reports:
            if report.has_events:
                self.io.print(f"\n[WORKPLACE] {report.player_name}: {report.describe()}")

        self._process_loan_repayments(year, season_index)
        self._consume_and_post_sustenance()

        if self.parallel_mode:
            results = self._run_season_parallel(year, season_index, event_results)
        else:
            results = self._run_season_sequential(year, season_index, event_results)

        self.market.snapshot_prices(year, season_index)
        self.market.reset_period_signals()
        self.market.tick_shocks()
        return results

    def _apply_event(self, player: Player, event: EventResult) -> None:
        """Pre-turn event application (announce, damage counters, price shocks)."""
        if not event.is_normal:
            self.io.print(f"\n[EVENT] {player.name}: {event.describe()}")
        if event.damage_seasons > 0:
            self._damage_counters[player.player_id] = (
                self._damage_counters.get(player.player_id, 0) + event.damage_seasons
            )
        if event.price_shock_resource and event.price_shock_multiplier != 1.0:
            self.market.apply_price_shock(
                event.price_shock_resource,
                event.price_shock_multiplier,
                duration_seasons=event.damage_seasons or 1,
            )

    def _run_season_sequential(
        self, year: int, season_index: int,
        event_results: dict[int, EventResult],
    ) -> list[TurnResult]:
        results = []
        for player in self.players:
            event = event_results.get(player.player_id, EventResult("Normal Operations"))
            self._apply_event(player, event)
            results.append(self.execute_turn(player, event, year, season_index))
        return results

    def _run_season_parallel(
        self, year: int, season_index: int,
        event_results: dict[int, EventResult],
    ) -> list[TurnResult]:
        """Run human turns concurrently, AI turns sequentially first.

        AI turns are deterministic and fast — running them up-front means
        their market activity is visible to humans immediately when the
        season opens. Human turns then run on per-player threads; each
        thread blocks on its own player-scoped IO adapter prompts.
        """
        import threading as _threading

        results: list[TurnResult] = []
        results_lock = _threading.Lock()

        # 1. AI turns first (sequential — fast and deterministic).
        for player in self.players:
            if player.is_human:
                continue
            event = event_results.get(player.player_id, EventResult("Normal Operations"))
            self._apply_event(player, event)
            r = self.execute_turn(player, event, year, season_index)
            results.append(r)
            cb = self.on_player_turn_complete
            if cb:
                try:
                    cb(player.player_id)
                except Exception:
                    pass

        # 2. Apply events for humans up-front (so they see them immediately)
        humans = [p for p in self.players if p.is_human]
        for player in humans:
            event = event_results.get(player.player_id, EventResult("Normal Operations"))
            self._apply_event(player, event)

        # 3. Spawn one thread per human player.
        threads: list[_threading.Thread] = []
        for player in humans:
            event = event_results.get(player.player_id, EventResult("Normal Operations"))

            def _run(p=player, e=event):
                try:
                    r = self.execute_turn(p, e, year, season_index)
                    with results_lock:
                        results.append(r)
                except Exception as exc:   # noqa: BLE001
                    self.io.print(f"[ERROR] turn for {p.name} failed: {exc}")
                finally:
                    cb = self.on_player_turn_complete
                    if cb:
                        try:
                            cb(p.player_id)
                        except Exception:
                            pass

            t = _threading.Thread(target=_run, name=f"turn-{player.name}", daemon=True)
            threads.append(t)
            t.start()

        # 4. Wait for every human turn thread to complete.
        for t in threads:
            t.join()
        return results

    def execute_turn(
        self, player: Player, event_result: EventResult, year: int, season_index: int
    ) -> TurnResult:
        dollops_before = player.dollops
        result = TurnResult(player_id=player.player_id, season=season_index, year=year)
        season_name = SEASONS[season_index]

        if not player.is_human:
            self._ai_review_training_queue(player, result, season_name, year)
            self._ai_arrange_transport_queue(player, result, season_name, year)
            training_actions = list(result.actions_taken)
            actions = self._ai.take_turn(
                player, self.market, self.players, self.production, self.trading,
                event_result, season_name, year, season_index, self.loan_ledger,
            )
            result.actions_taken = training_actions + actions
            for a in actions:
                self.io.print(a)
        else:
            self._human_turn(player, event_result, result, season_name, year, season_index)

        for message in self.production.run_kitchens(player):
            self.io.print(f"  [Kitchen] {message}")
            result.actions_taken.append(f"kitchen:{message}")

        result.dollops_delta = player.dollops - dollops_before
        return result

    def _human_turn(
        self,
        player: Player,
        event_result: EventResult,
        result: TurnResult,
        season_name: str,
        year: int,
        season_index: int = 0,
    ) -> None:
        sym = CURRENCY_SYMBOL
        # Per-player action section header.  All humans run concurrently
        # within a season (parallel_mode); this header just frames one
        # island's actions in the shared log.
        self.io.print(f"\n--- {player.name} ({player.role_names()}) — actions this season ---")
        prices = self.market.current_prices()
        current_tick = year * len(SEASONS) + season_index
        self.io.print(
            f"    Dollops: {player.dollops:.1f} {sym}  |  "
            f"Net Wealth: "
            f"{player.total_wealth(prices, self.loan_ledger, CAPITAL_CATALOGUE, current_tick):.1f} {sym}  |  "
            f"Workers: {player.workforce.count} "
            f"({player.workforce.average_efficiency*100:.0f}% eff  |  "
            f"capacity: {player.production_capacity*100:.0f}%)"
        )
        self._review_pending_deals(player, result)
        self._review_training_counteroffers(player, result, season_name, year)
        while True:
            action = self.io.choose_action(player, list(TurnAction))
            if action == TurnAction.END_TURN:
                break
            try:
                if action == TurnAction.INVENTORY:
                    self.io.print(player.inventory_report(
                        self.market.current_prices(), self.loan_ledger,
                        CAPITAL_CATALOGUE, current_tick
                    ))
                elif action == TurnAction.VIEW_MARKET:
                    self.io.print(self._format_market())
                elif action == TurnAction.VIEW_PLAYERS:
                    self.io.print(self._format_players(player, year, season_index))
                elif action == TurnAction.PRODUCE:
                    self._action_produce(player, event_result, result, season_name)
                elif action == TurnAction.MARKET_BUY:
                    self._action_market_buy(player, result)
                elif action == TurnAction.MARKET_SELL:
                    self._action_market_sell(player, result)
                elif action == TurnAction.PROPOSE_DEAL:
                    self._action_propose_deal(player, result)
                elif action == TurnAction.REQUEST_TRAINING:
                    self._action_request_training(player, result, season_name, year)
                elif action == TurnAction.REVIEW_TRAINING:
                    self._action_review_training(player, result, season_name, year)
                elif action == TurnAction.ARRANGE_TRANSPORT:
                    self._action_arrange_transport(player, result, season_name, year)
                elif action == TurnAction.RECRUIT_WORKERS:
                    self._action_recruit_workers(player, result)
                elif action == TurnAction.SELL_INSURANCE:
                    self._action_sell_insurance(player, result, year, season_index)
                elif action == TurnAction.BUY_INSURANCE:
                    self._action_buy_insurance(player, result, year, season_index)
                elif action == TurnAction.MANAGE_INSURANCE:
                    self._action_manage_insurance(player, result, year, season_index)
                elif action == TurnAction.PURCHASE_CAPITAL:
                    self._action_purchase_capital(player, result, year, season_index)
                elif action == TurnAction.LEASE_CAPITAL:
                    self._action_lease_capital(player, result, year, season_index)
                elif action == TurnAction.INVEST:
                    self._action_invest(player, result, year, season_index)
                elif action == TurnAction.OFFER_LOAN:
                    self._action_offer_loan(player, result, year, season_index)
                elif action == TurnAction.TAKE_LOAN:
                    self._action_take_loan(player, result, year, season_index)
                elif action == TurnAction.ROLLOVER_LOAN:
                    self._action_rollover_loan(player, result, year, season_index)
                elif action == TurnAction.VIEW_LOANS:
                    self._action_view_loans(player)
                elif action == TurnAction.PAY_LEASE:
                    self._action_pay_lease(player, result, year, season_index)
                elif action == TurnAction.APPLY_PATENT:
                    self._action_apply_patent(player, result)
            except ActionCancelled:
                # User pressed Cancel mid-prompt-chain — abort cleanly without
                # falling back to default values that would partially execute
                # the action (e.g. training 1 worker by default when the user
                # clearly meant "abandon this action").
                self.io.print("  Action cancelled.")
            except Exception as exc:
                self.io.print(f"  Action failed: {exc}")
            finally:
                if hasattr(self.io, "on_action_complete") and self.io.on_action_complete:
                    self.io.on_action_complete()

    def _consume_and_post_sustenance(self) -> None:
        """Per-season sustenance: each island consumes its population's
        meals from inventory, then posts any shortfall to the market as
        a basket demand.

        Sustenance basket model (2026-05-25): each ``PEOPLE_PER_MEAL``
        residents need one meal per season; meal = 1 Food OR
        (1 Grain + 1 Produce + 1 (Fish or Meat)) with 2:1 cross-
        substitution between raw ingredients.  See
        ``Player.consume_sustenance`` / ``_allocate_raw_meals``.

        The Education Island also feeds visiting trainees on campus
        ("campus load") — transient extra mouths above its residents
        until they return home (Education Phase 3 ↔ §21).
        """
        for player in self.players:
            extra_residents = (
                self.training.visiting_trainees(player.player_id)
                if any(r.name == "Educator" for r in player.roles) else 0
            )
            absent_residents = self.training.trainees_away_from_home(player.player_id)
            meals = player.meals_needed(
                extra_residents=extra_residents,
                absent_residents=absent_residents,
            )
            if meals <= 0:
                continue
            satisfied, _used, shortfall = player.consume_sustenance(meals)
            # Post unmet basket demand so AI sellers see the signal on
            # every component that could fill the gap.  Overcounting in
            # absolute units is intentional — it's signal, price
            # elasticity sorts out which seller fills which slot.
            if shortfall > 0:
                for resource in (
                    ResourceType.FOOD, ResourceType.GRAIN,
                    ResourceType.PRODUCE, ResourceType.FISH,
                    ResourceType.MEAT,
                ):
                    self.market.post_demand(resource, shortfall)

    def _manufactured_resource_for_capital_item(self, item) -> ResourceType:
        role_map = {
            "Farmer": ResourceType.FARM_MACHINERY,
            "Miner": ResourceType.MINING_EQUIPMENT,
            "Transporter": ResourceType.TRANSPORT_EQUIPMENT,
            "Educator": ResourceType.LABORATORY_EQUIPMENT,
            "Banker": ResourceType.LABORATORY_EQUIPMENT,
            "Manufacturer": ResourceType.TRANSPORT_EQUIPMENT,
            "Doctor": ResourceType.MEDICAL_DEVICES,
        }
        return role_map[item.role]

    def _action_purchase_capital(
        self, player: Player, result: TurnResult, year: int, season_index: int
    ) -> None:
        """Buy a named capital item from the Manufacturing island's equipment output."""
        available_items = []
        seen: set[str] = set()
        for role in player.roles:
            for item in items_for_role(CAPITAL_CATALOGUE, role.name):
                if item.item_id in seen:
                    continue
                seen.add(item.item_id)
                available_items.append(item)
        if not available_items:
            self.io.print("  No capital equipment is available for your roles.")
            return

        sym = CURRENCY_SYMBOL
        self.io.print("\n  Capital equipment available:")
        for idx, item in enumerate(available_items, 1):
            cash_only = item.effects.get("cash_only", False)
            manufactured_resource = (
                None if cash_only else self._manufactured_resource_for_capital_item(item)
            )
            arrival = (
                "arrives now"
                if item.delivery_seasons == 0
                else f"arrives in {item.delivery_seasons} season(s)"
            )
            requirement = (
                "cash-only"
                if cash_only
                else f"requires 1x {manufactured_resource.value}"
            )
            self.io.print(
                f"    {idx}. {item.name} ({item.role}) — {item.cost:.0f} {sym}; "
                f"{requirement}; {arrival}"
            )

        choice = self.io.choose_quantity("Choose capital item", 1, len(available_items))
        item = available_items[choice - 1]
        cash_only = item.effects.get("cash_only", False)
        manufacturer = None
        manufactured_resource = None
        if not cash_only:
            manufacturers = [
                p for p in self.players
                if any(r.name == "Manufacturer" for r in p.roles)
            ]
            if not manufacturers:
                self.io.print("  No Manufacturing island is available to build capital equipment.")
                return
            manufacturer = self.io.choose_player("Buy from which Manufacturer?", manufacturers)
            manufactured_resource = self._manufactured_resource_for_capital_item(item)
            if manufacturer.inventory.get(manufactured_resource) <= 0:
                self.io.print(
                    f"  {manufacturer.name} has no {manufactured_resource.value} available "
                    f"to build {item.name}."
                )
                return
        if player.dollops < item.cost and (cash_only or manufacturer.player_id != player.player_id):
            self.io.print(f"  You need {item.cost:.0f} {sym} to buy {item.name}.")
            return
        if not self.io.confirm(
            (
                f"Buy {item.name} for {item.cost:.0f} {sym}?"
                if cash_only
                else f"Buy {item.name} from {manufacturer.name} for {item.cost:.0f} {sym}?"
            )
        ):
            return

        if not cash_only:
            manufacturer.give_resources(manufactured_resource, 1)
        if cash_only or manufacturer.player_id != player.player_id:
            player.spend_dollops(item.cost)
        if not cash_only and manufacturer.player_id != player.player_id:
            manufacturer.receive_dollops(item.cost)
        current_tick = year * len(SEASONS) + season_index
        if item.delivery_seasons <= 0:
            player.add_capital(item.item_id, acquired_tick=current_tick)
            arrival = "delivered immediately"
        else:
            arrives_at = current_tick + item.delivery_seasons
            player.capital_in_transit.append({
                "item_id": item.item_id,
                "arrives_at_tick": arrives_at,
            })
            arrival = f"arriving Year {arrives_at // len(SEASONS) + 1}, {SEASONS[arrives_at % len(SEASONS)]}"
        consumed = "cash-only purchase" if cash_only else f"consumed 1x {manufactured_resource.value}"
        self.io.print(f"  Purchased {item.name}; {consumed}; {arrival}.")
        counterparty = "cash" if cash_only else manufacturer.name
        result.actions_taken.append(f"purchase_capital:{item.item_id}:{counterparty}")

    def _create_equipment_lease(
        self,
        lessee: Player,
        item,
        year: int,
        season_index: int,
        lessor: Player | None = None,
        immediate_delivery: bool = True,
    ):
        quote = lease_quote(item, year, season_index)
        if lessee.dollops < quote["annual_payment"]:
            raise ValueError(
                f"{lessee.name} needs {quote['annual_payment']:.1f} {CURRENCY_SYMBOL} "
                f"for the first lease payment."
            )
        banker = lessor or self._find_banker()
        lessor_id = banker.player_id if banker else -1
        lessee.dollops -= quote["annual_payment"]
        if banker and banker.player_id != lessee.player_id:
            banker.dollops += quote["annual_payment"]
        current_tick = year * len(SEASONS) + season_index
        if immediate_delivery or item.delivery_seasons <= 0:
            lessee.add_capital(item.item_id, 1, acquired_tick=current_tick)
        else:
            arrives_at = current_tick + item.delivery_seasons
            lessee.capital_in_transit.append({
                "item_id": item.item_id,
                "arrives_at_tick": arrives_at,
            })
        return self.lease_ledger.create_lease(
            item_id=item.item_id,
            lessee_id=lessee.player_id,
            lessor_id=lessor_id,
            year=year,
            season=season_index,
            term_years=quote["term_years"],
            annual_payment=quote["annual_payment"],
            buyout_payment=quote["buyout_payment"],
            locked_lease_rate=quote["locked_lease_rate"],
            payments_made=1,
            last_payment_year=year,
        )

    def _action_lease_capital(
        self, player: Player, result: TurnResult, year: int, season_index: int
    ) -> None:
        """Lease an eligible capital item from the Bank."""
        sym = CURRENCY_SYMBOL
        seen: set[str] = set()
        available = []
        for role in player.roles:
            for item in items_for_role(CAPITAL_CATALOGUE, role.name):
                if item.item_id in seen or not item.lease_terms:
                    continue
                seen.add(item.item_id)
                available.append(item)
        if not available:
            self.io.print("  No lease-eligible equipment is available for your roles.")
            return
        options = []
        for item in available:
            quote = lease_quote(item, year, season_index)
            options.append({
                "value": item.item_id,
                "label": (
                    f"{item.name} — {quote['annual_payment']:.1f} {sym}/year "
                    f"for {quote['term_years']} years + "
                    f"{quote['buyout_payment']:.1f} {sym} buyout"
                ),
            })
        chosen_id = self.io.choose_option("Lease which equipment?", options)
        item = next((it for it in available if it.item_id == chosen_id), None)
        if item is None:
            self.io.print("  Unknown lease selection.")
            return
        quote = lease_quote(item, year, season_index)
        if not self.io.confirm(
            f"Lease {item.name} for {quote['annual_payment']:.1f} {sym}/year "
            f"with {quote['buyout_payment']:.1f} {sym} buyout?"
        ):
            return
        try:
            lease = self._create_equipment_lease(
                player, item, year, season_index, immediate_delivery=False
            )
        except ValueError as exc:
            self.io.print(f"  {exc}")
            return
        self.io.print(
            f"  Lease #{lease.lease_id} started for {item.name}; first payment made."
        )
        result.actions_taken.append(f"lease_capital:{item.item_id}:lease#{lease.lease_id}")

    def _action_invest(
        self, player: Player, result: TurnResult, year: int, season_index: int
    ) -> None:
        """Take up an opening-catalogue item the island didn't pick.

        Items from the player's role catalogue that they don't currently
        own are still on offer (the "opening investments remain
        available if not chosen" rule).  Investing here is immediate
        delivery + cost paid in Dp — no Manufacturer transit, no
        Manufacturer side-effects (the Investing Phase already treats
        opening picks as immediately available).
        """
        sym = CURRENCY_SYMBOL
        seen: set[str] = set()
        available: list = []
        for role in player.roles:
            for item in items_for_role(CAPITAL_CATALOGUE, role.name):
                if item.item_id in seen:
                    continue
                seen.add(item.item_id)
                if player.capital_inventory.get(item.item_id, 0) <= 0:
                    available.append(item)
        if not available:
            self.io.print(
                "  No remaining opening investments — your roles' catalogues "
                "are fully taken up (or expired items can be repurchased via "
                "Purchase Equipment from the Manufacturer)."
            )
            return
        self.io.print(
            "\n  Open investments — choices from your opening catalogue you "
            "haven't taken yet (immediate delivery, paid in Dp):"
        )
        options = []
        for item in available:
            options.append({
                "value": item.item_id,
                "label": (
                    f"{item.name} — {item.cost:.0f} {sym}  "
                    f"({item.description})"
                ),
            })
        chosen_id = self.io.choose_option(
            "Invest in which item?", options
        )
        if chosen_id is None:
            self.io.print("  No selection — cancelled.")
            return
        item = next((it for it in available if it.item_id == chosen_id), None)
        if item is None:
            self.io.print("  Unknown selection.")
            return
        if player.dollops < item.cost:
            self.io.print(
                f"  Cannot afford {item.name}: cost {item.cost:.0f} {sym}, "
                f"you have {player.dollops:.1f} {sym}."
            )
            return
        player.dollops -= item.cost
        current_tick = year * len(SEASONS) + season_index
        player.add_capital(item.item_id, 1, acquired_tick=current_tick)
        self.io.print(
            f"  Invested {item.cost:.0f} {sym} in {item.name} "
            f"— delivered now."
        )
        result.actions_taken.append(f"invest:{item.item_id}")

    def _choose_product_line_human(self) -> str:
        """Prompt the human Manufacturer player to choose a product line.

        Presented as named choices (Issue #21), not a numeric index.
        """
        lines = list(MANUFACTURER_PRODUCT_LINES.items())
        picker_options = []
        for key, line in lines:
            freight_note = (
                "  (no freight surcharge)"
                if line["freight_per_unit"] == 0
                else f"  (+{line['freight_per_unit']} Freight/unit shipped)"
            )
            label = (
                f"{line['desc']} — Inputs: {line['inputs']} "
                f"→ {line['qty']}x {line['output']}{freight_note}"
            )
            picker_options.append({"value": key, "label": label})
        chosen = self.io.choose_option("Choose product line", picker_options)
        # `chosen` is a product-line key; fall back to the first if anything
        # unexpected comes back.
        valid_keys = {k for k, _ in lines}
        return chosen if chosen in valid_keys else lines[0][0]

    def _action_produce(
        self, player: Player, event_result: EventResult, result: TurnResult, season_name: str
    ) -> None:
        if event_result.outage:
            self.io.print(f"  Event: {event_result.event_name}")
            self.io.print("  Production halted this season.")
            return

        options = self.production.production_options(player, event_result, season_name)
        self.io.print(f"  Event: {event_result.event_name}")
        if not options:
            self.io.print("  Cannot produce anything right now — production is blocked by equipment, workforce, or inputs.")
            return

        # Present the production choices as named options (Issue #21) — the
        # player picks "Farm Machinery", not an index number.
        picker_options = []
        for idx, option in enumerate(options):
            output = option["output"].value
            line = ""
            if option["product_line"]:
                line_info = MANUFACTURER_PRODUCT_LINES[option["product_line"]]
                line = f" — {line_info['desc']}"
            cap = option["capacity_limit"]
            cap_note = "" if cap is None else f" (capacity cap {cap})"
            label = (
                f"{option['role']}: {output}{line} "
                f"— up to {option['max_qty']} now{cap_note}"
            )
            picker_options.append({"value": idx, "label": label})

        chosen = self.io.choose_option("Choose product to produce", picker_options)
        try:
            option = options[int(chosen)]
        except (TypeError, ValueError, IndexError):
            option = options[0]
        qty = self.io.choose_quantity(
            f"How many {option['output'].value}? (max {option['max_qty']})",
            1,
            option["max_qty"],
        )
        inputs = self.production._inputs_for_selected_output(
            player=player,
            role_name=option["role"],
            output=option["output"],
            qty=qty,
            preview_qty=option["preview_qty"],
            season_name=season_name,
            product_line=option["product_line"],
        )
        inputs_summary = ", ".join(f"{amount}x {r.value}" for r, amount in inputs.items()) or "no inputs"
        self.io.print(f"  Producing {qty}x {option['output'].value} will consume: {inputs_summary}")
        if self.io.confirm("Produce?"):
            produced = self.production.produce_product(
                player=player,
                event_result=event_result,
                season_name=season_name,
                role_name=option["role"],
                output=option["output"],
                qty=qty,
                product_line=option["product_line"],
            )
            summary = ", ".join(f"{amount}x {r.value}" for r, amount in produced.items())
            self.io.print(f"  Produced: {summary}")
            result.actions_taken.append(f"produce:{summary}")

    def _action_request_training(
        self, player: Player, result: TurnResult, season_name: str, year: int
    ) -> None:
        """Player proposes to send workers to the Education Island for one season."""
        season_index = SEASONS.index(season_name)

        # Build list of professions with remaining capacity.  Also surface
        # exhausted professions so the player can SEE why one isn't selectable
        # (previously a profession just vanished from the menu after its
        # annual cap was reached — confusing the user when, say, "Banker"
        # disappeared after 2 graduates).
        capacity_map = self.training.capacity_summary(year, season_index)
        available_professions = [
            prof for prof, info in capacity_map.items() if info["remaining"] > 0
        ]
        exhausted_professions = [
            prof for prof, info in capacity_map.items() if info["remaining"] <= 0
        ]

        skill_deficits = self._training_skill_deficits(player)
        self.io.print("  Skill deficits against your island staffing plan:")
        if skill_deficits:
            for prof, qty in skill_deficits.items():
                cap = capacity_map.get(prof, {}).get("remaining", 0)
                suffix = f"{cap} university slot(s) available now" if cap > 0 else "no university slots available now"
                self.io.print(f"    {prof:<24}  need {qty}  ({suffix})")
        else:
            self.io.print("    None — formal staffing plan is currently covered.")

        # Show capacity report — both available and exhausted lines so the
        # player can see the full picture.
        self.io.print("  University capacity this year:")
        for prof in available_professions:
            info = capacity_map[prof]
            seasonal_note = (
                f"  (max {info['seasonal_cap']}/season)" if info["seasonal_cap"] else ""
            )
            self.io.print(
                f"    {prof:<24}  {info['remaining']:>2} slot(s) left "
                f"(of {info['annual_cap']} annual){seasonal_note}"
            )
        for prof in exhausted_professions:
            info = capacity_map[prof]
            self.io.print(
                f"    {prof:<24}   FULL — {info['trained']}/{info['annual_cap']} "
                f"already requested this year"
            )

        if not available_professions:
            self.io.print("  University is fully booked for this year across all professions.")
            return

        # For the chosen profession, decide which workers are eligible
        # Unskilled workers → enter profession at Basic; professionals → advance level
        unskilled_ids = player.workforce.get_unskilled_ids(player.workforce.active_count)
        other_trainable = [
            wid for wid in player.workforce.get_trainable_ids(player.workforce.active_count)
            if wid not in unskilled_ids
        ]
        reserved_worker_ids = self.training.reserved_worker_ids(player.player_id)
        unskilled_ids = [wid for wid in unskilled_ids if wid not in reserved_worker_ids]
        other_trainable = [wid for wid in other_trainable if wid not in reserved_worker_ids]
        # Prefer unskilled (entering profession) for new professions, or existing workers to advance
        trainable_ids = unskilled_ids + other_trainable
        if not trainable_ids:
            self.io.print(
                "  No eligible workers to send (all expert, already at college, "
                "or already committed to a pending training request)."
            )
            return

        bundle_plan = {
            prof: min(qty, capacity_map.get(prof, {}).get("remaining", 0))
            for prof, qty in skill_deficits.items()
            if capacity_map.get(prof, {}).get("remaining", 0) > 0
        }
        bundle_plan = {prof: qty for prof, qty in bundle_plan.items() if qty > 0}
        bundle_option = "All visible skill deficits"
        profession_choices = list(available_professions)
        if bundle_plan:
            profession_choices.append(bundle_option)

        target_profession = self.io.choose_profession(
            "Train workers into which profession?", profession_choices
        )
        if target_profession == bundle_option:
            training_plan: dict[str, int] = {}
            remaining_workers = len(trainable_ids)
            for prof, qty in bundle_plan.items():
                if remaining_workers <= 0:
                    break
                send = min(qty, remaining_workers)
                if send > 0:
                    training_plan[prof] = send
                    remaining_workers -= send
            if not training_plan:
                self.io.print("  No visible skill deficits can be requested right now.")
                return
            count = sum(training_plan.values())
            summary = ", ".join(f"{qty} × {prof}" for prof, qty in training_plan.items())
            self.io.print(f"  Bundle request: {summary}")
            unsent = sum(bundle_plan.values()) - count
            if unsent > 0:
                self.io.print(
                    f"  {unsent} additional deficit slot(s) remain unsent because only "
                    f"{len(trainable_ids)} eligible worker(s) are available now."
                )
        else:
            remaining_capacity = capacity_map[target_profession]["remaining"]
            max_send = min(len(trainable_ids), remaining_capacity)
            count = self.io.choose_quantity(
                f"How many workers to train as {target_profession}? (max {max_send})", 1, max_send
            )
            training_plan = {target_profession: count}
        worker_ids = trainable_ids[:count]

        # Self-training: if THIS player is the Educator, they're training their
        # own workforce on-island.  Skip the educator picker, the fee prompt,
        # and the air-ticket requirement.  The training request is still
        # registered against University capacity and still takes 1 season to
        # complete.
        is_self_training = any(r.name == "Educator" for r in player.roles)
        sym = CURRENCY_SYMBOL
        if is_self_training:
            educator = player
            dollops_educator = 0.0
            transport_mode = "self_training"
            self.io.print(
                f"  Self-training: {count} of your own worker(s) will train as "
                f"{target_profession} on-island.  No fee, no transport ticket."
            )
        else:
            # Find Educator players (excluding self — already handled above)
            educators = [
                p for p in self.players
                if p.player_id != player.player_id
                and any(r.name == "Educator" for r in p.roles)
            ]
            if not educators:
                self.io.print("  No Educator player in this game.")
                return

            educator = self.io.choose_player("Which Educator?", educators)
            self.io.print(
                f"  Travel: Air ticket — Education supplies {count} PassengerSeats "
                f"for {count} trainee(s); return travel is included."
            )
            self.io.print(
                "  Sea travel would add one extra season, but the current rule uses "
                "Educator-supplied air tickets for standard training."
            )
            requester_ticket_pool = player.inventory.get(ResourceType.PASSENGER_SEATS)
            tickets_supplied_by_requester = 0
            if requester_ticket_pool > 0:
                tickets_supplied_by_requester = self.io.choose_quantity(
                    "How many PassengerSeats will you supply yourself "
                    "(saves on Educator fee)?",
                    0,
                    min(count, requester_ticket_pool),
                )
            ticket_price = self.market.current_price(ResourceType.PASSENGER_SEATS)
            course_duration = away_seasons(target_profession)
            is_manager = band_of(target_profession) == WorkerBand.MANAGER
            # Expertise is burned per Course per season — Manager-tier only;
            # apprenticeships (Technician) are not Course/Expertise gated.
            courses = self.courses_needed(count) if is_manager else 0
            expertise_price = self.market.current_price(ResourceType.EXPERTISE)
            base_fee = 20.0 * count
            food_accom = TRAINEE_FOOD_ACCOM_PER_SEASON * count * course_duration
            educator_ticket_count = count - tickets_supplied_by_requester
            tickets = ticket_price * educator_ticket_count
            expertise_cost = expertise_price * courses * course_duration
            suggested_total = base_fee + food_accom + tickets + expertise_cost
            self.io.print(
                f"  Fee components — base {base_fee:.0f}, food/accom "
                f"{food_accom:.0f} ({count}×{course_duration}s @ "
                f"{TRAINEE_FOOD_ACCOM_PER_SEASON:.0f} {sym}), Educator-supplied "
                f"tickets {tickets:.0f} ({educator_ticket_count}×), "
                f"expertise {expertise_cost:.0f}."
            )
            fee_prompt = (
                f"Offer total training fee to Educator ({educator.name}) in {sym}? "
                f"(suggested total: {suggested_total:.0f} {sym})"
            )
            try:
                dollops_educator = self.io.ask_dollop_amount(
                    fee_prompt,
                    player.dollops,
                    prefill=suggested_total,
                )
            except TypeError:
                dollops_educator = self.io.ask_dollop_amount(fee_prompt, player.dollops)
            transport_mode = "air_ticket"
        if is_self_training:
            tickets_supplied_by_requester = 0
        dollops_transport = 0.0

        player_names = {p.player_id: p.name for p in self.players}
        requests = []
        worker_offset = 0
        ticket_offset = 0
        for profession, profession_count in training_plan.items():
            batch_worker_ids = worker_ids[worker_offset:worker_offset + profession_count]
            worker_offset += profession_count
            batch_requester_tickets = 0
            if transport_mode == "air_ticket" and tickets_supplied_by_requester:
                batch_requester_tickets = min(
                    profession_count,
                    tickets_supplied_by_requester - ticket_offset,
                )
                ticket_offset += batch_requester_tickets
            batch_fee = (
                dollops_educator * profession_count / count
                if count else 0.0
            )
            try:
                req = self.training.propose(
                    requester_id=player.player_id,
                    worker_ids=batch_worker_ids,
                    educator_id=educator.player_id,
                    dollops_to_educator=batch_fee,
                    dollops_to_transporter=dollops_transport,
                    target_profession=profession,
                    year=year,
                    season=season_index,
                    transport_mode=transport_mode,
                    tickets_supplied_by_requester=batch_requester_tickets,
                )
            except TrainingCapacityError as e:
                self.io.print(f"  {e}")
                continue
            requests.append(req)
            self.io.print(f"  Training request #{req.batch_id} submitted:")
            self.io.print(f"    {req.describe(player_names)}")
            result.actions_taken.append(f"request_training:batch#{req.batch_id}")
        if not requests:
            return

        if is_self_training:
            # Self-training: each batch is auto-approved + dispatched
            # on-island (no fee, no transport ticket).  A bundled request
            # is several batches; Manager-tier batches consume a Course
            # slot, Technician-tier batches an apprenticeship slot (and
            # need an Instructor) — Phase 3 band-aware gate.  We commit
            # each ready batch immediately (so capacity is never debited
            # without a dispatch) and leave any blocked batch pending
            # until its capacity frees up.
            for req in requests:
                ok, gate_msg = self._training_capacity_status(player, req)
                if not ok:
                    self.io.print(
                        f"  Self-training request #{req.batch_id} "
                        f"({self._profession_label(req.target_profession)}) "
                        f"submitted but on hold: {gate_msg} It will start "
                        f"once that capacity frees up."
                    )
                    continue
                used_desc = self._consume_training_capacity(player, req)
                self.training.educator_approve(req.batch_id)
                self.training.dispatch(req.batch_id, year, season_index)
                # Mark workers as in-training on the workforce side too.
                # Without this, _process_training_returns at the return tick
                # is a no-op for these workers (return_from_training requires
                # in_training == True), so a self-trained worker would never
                # graduate / advance their training_level — observed in
                # playtest 2026-05-24.  On-island training still means the
                # worker is in class for the duration, not at their job.
                player.workforce.dispatch_for_training(req.worker_ids)
                self.io.print(
                    f"  {len(req.worker_ids)} worker(s) entered on-island "
                    f"training as {self._profession_label(req.target_profession)} "
                    f"({used_desc}); return: {self._format_training_return(req)}."
                )
            return

        self.io.print(
            f"  Awaiting {educator.name}'s approval. "
            f"{educator.name} must supply "
            f"{count - tickets_supplied_by_requester} PassengerSeats air ticket(s); "
            f"requester supplies {tickets_supplied_by_requester}."
        )

        # AI Educator auto-responds immediately
        if not educator.is_human:
            for req in requests:
                self._ai_educator_respond(educator, player, req, season_name, year)

    def _training_skill_deficits(self, player: Player) -> dict[str, int]:
        """Formal-profession gaps against the player's role staffing blueprint."""
        required: dict[str, int] = {}
        for role in player.roles:
            for profession, count in STARTING_WORKERS_BY_PROFESSION.get(role.name, []):
                required[profession] = required.get(profession, 0) + count

        current: dict[str, int] = {}
        for worker in player.workforce.workers:
            current[worker.profession] = current.get(worker.profession, 0) + 1
        workers_by_id = {worker.worker_id: worker for worker in player.workforce.workers}
        for req in self.training.active_for_player(player.player_id):
            incoming = sum(
                1
                for worker_id in req.worker_ids
                if workers_by_id.get(worker_id)
                and workers_by_id[worker_id].profession == Profession.UNSKILLED.value
            )
            current[req.target_profession] = current.get(req.target_profession, 0) + incoming

        return {
            profession: needed - current.get(profession, 0)
            for profession, needed in required.items()
            if needed > current.get(profession, 0)
        }

    def _ai_educator_respond(
        self, educator, requester, req, season_name: str, year: int
    ) -> None:
        """Educator AI: accept if the Dollops offered cover a fair rate per worker."""
        required_offer = self._ai_training_required_offer(req)
        educator_tickets = self._educator_ticket_count(req)
        if req.dollops_to_educator >= required_offer:
            # Peek training capacity before burning air tickets.
            ok, gate_msg = self._training_capacity_status(educator, req)
            if not ok:
                self.io.print(
                    f"  [AI] {educator.name} cannot approve training request #{req.batch_id} yet: "
                    f"{gate_msg} Pending."
                )
                return
            if not self._ensure_training_air_tickets(educator, req, requester):
                self.io.print(
                    f"  [AI] {educator.name} cannot approve training request #{req.batch_id}: "
                    f"needs PassengerSeats air ticket(s): requester supplies "
                    f"{req.tickets_supplied_by_requester}, Educator supplies {educator_tickets}."
                )
                return
            self._consume_training_capacity(educator, req)
            self.training.educator_approve(req.batch_id)
            requester.spend_dollops(req.dollops_to_educator)
            educator.receive_dollops(req.dollops_to_educator)
            self.io.print(
                f"  [AI] {educator.name} approved training request #{req.batch_id} "
                f"(received {req.dollops_to_educator:.0f} Dp)."
            )
            if req.transport_mode == "air_ticket":
                self._dispatch_training(requester, req, season_name, year)
            elif req.transport_mode in ("flight", "cargo"):
                self._dispatch_training(requester, req, season_name, year)
            else:
                self._auto_arrange_transport(requester, req, season_name, year)
        else:
            self.training.educator_reject(req.batch_id)
            self.io.print(
                f"  [AI] {educator.name} rejected training request #{req.batch_id}. "
                f"Offer at least {required_offer:.0f} Dp to cover training and tickets."
            )

    def _ai_review_training_queue(
        self, educator: Player, result: TurnResult, season_name: str, year: int
    ) -> None:
        """Let AI Educators revisit pending requests every season.

        Requests can be blocked by capacity or PassengerSeats when first
        submitted. Without this seasonal pass, those requests never restart
        after the blocking condition clears.
        """
        if not any(role.name == "Educator" for role in educator.roles):
            return
        player_map = {player.player_id: player for player in self.players}
        pending = list(self.training.pending_for_educator(educator.player_id))
        if not pending:
            return
        self.io.print(
            f"  [AI] {educator.name} reviewing {len(pending)} pending training request(s)."
        )
        for req in pending:
            requester = player_map.get(req.requester_id)
            if requester is None:
                self.training.educator_reject(req.batch_id)
                self.io.print(
                    f"  [Training] Request #{req.batch_id} rejected: requester is no longer available."
                )
                result.actions_taken.append(f"training_rejected_missing_requester:batch#{req.batch_id}")
                continue
            before = req.status
            self._ai_educator_respond(educator, requester, req, season_name, year)
            if req.status != before:
                result.actions_taken.append(f"ai_training_review:batch#{req.batch_id}:{req.status.value}")

    def _ai_arrange_transport_queue(
        self, transporter: Player, result: TurnResult, season_name: str, year: int
    ) -> None:
        """Let AI Transporters revisit old non-ticket transport jobs."""
        if not any(role.name == "Transporter" for role in transporter.roles):
            return
        pending = [
            req for req in self.training.pending_transport()
            if req.transport_mode not in ("air_ticket", "self_training")
        ]
        if not pending:
            return
        player_map = {player.player_id: player for player in self.players}
        for req in pending:
            requester = player_map.get(req.requester_id)
            if requester is None:
                continue
            fair_rate = 5.0 * len(req.worker_ids)
            if req.dollops_to_transporter < fair_rate:
                self.io.print(
                    f"  [AI] {transporter.name} left transport request #{req.batch_id} pending: "
                    f"offer {req.dollops_to_transporter:.0f} Dp below {fair_rate:.0f} Dp floor."
                )
                continue
            if not self._training_workers_ready(requester, req):
                continue
            requester.spend_dollops(req.dollops_to_transporter)
            transporter.receive_dollops(req.dollops_to_transporter)
            self.training.arrange_transport(req.batch_id, transporter.player_id)
            if self._dispatch_training(requester, req, season_name, year):
                result.actions_taken.append(f"ai_transport_arranged:batch#{req.batch_id}")

    def _ai_training_required_offer(self, req) -> float:
        fair_rate = 20.0 * len(req.worker_ids)
        educator_tickets = self._educator_ticket_count(req)
        ticket_cost = self.market.current_price(ResourceType.PASSENGER_SEATS) * educator_tickets
        return fair_rate + ticket_cost

    def _auto_arrange_transport(self, requester, req, season_name: str, year: int) -> None:
        """Find an AI Transporter to handle the logistics, or flag for human turn."""
        transporters = [
            p for p in self.players
            if any(r.name == "Transporter" for r in p.roles)
        ]
        if not transporters:
            self.io.print(
                "  No Transporter player — workers cannot depart until transport is arranged."
            )
            return
        transporter = transporters[0]
        fair_rate = 5.0 * len(req.worker_ids)
        if not transporter.is_human and req.dollops_to_transporter >= fair_rate:
            if not self._training_workers_ready(requester, req):
                return
            self.training.arrange_transport(req.batch_id, transporter.player_id)
            requester.spend_dollops(req.dollops_to_transporter)
            transporter.receive_dollops(req.dollops_to_transporter)
            self.io.print(
                f"  [AI] {transporter.name} arranged transport for batch #{req.batch_id} "
                f"(received {req.dollops_to_transporter:.0f} Dp)."
            )
            self._dispatch_training(requester, req, season_name, year)
        else:
            self.io.print(
                f"  Transport needed for batch #{req.batch_id}. "
                f"{transporter.name} must agree on their turn."
            )

    def _training_workers_ready(self, requester: Player, req) -> bool:
        active_ids = {worker.worker_id for worker in requester.workforce.active_workers}
        missing = [worker_id for worker_id in req.worker_ids if worker_id not in active_ids]
        if missing:
            ids = ", ".join(str(worker_id) for worker_id in missing)
            self.io.print(
                f"  [Training] Cannot dispatch request #{req.batch_id}: "
                f"worker(s) not active on {requester.name}'s island: {ids}. "
                "The request remains pending."
            )
            return False
        return True

    def _dispatch_training(self, requester, req, season_name: str, year: int) -> bool:
        """Workers physically depart; mark them absent for the season."""
        if not self._training_workers_ready(requester, req):
            return False
        season_index = SEASONS.index(season_name)
        self.training.dispatch(req.batch_id, year=year, season=season_index, num_seasons=len(SEASONS))
        departed = requester.workforce.dispatch_for_training(req.worker_ids)
        if len(departed) != len(req.worker_ids):
            self.io.print(
                f"  [Training] Dispatch failed for request #{req.batch_id}: "
                f"expected {len(req.worker_ids)} trainee(s), moved {len(departed)}. "
                "The batch may not return correctly; check workforce state."
            )
            return False
        self.io.print(
            f"  {len(departed)} worker(s) from {requester.name}'s island departed for "
            f"Education Island. Return scheduled: {self._format_training_return(req)}."
        )
        return True

    def _educator_ticket_count(self, req) -> int:
        requester_share = max(0, min(req.tickets_supplied_by_requester, len(req.worker_ids)))
        return len(req.worker_ids) - requester_share

    def _ensure_training_air_tickets(
        self, educator: Player, req, requester: Player | None = None
    ) -> bool:
        """Consume PassengerSeats for a training batch.

        Requester-supplied tickets are spent from the requester; the
        Educator only covers the remaining seats.
        """
        requester_share = max(0, min(req.tickets_supplied_by_requester, len(req.worker_ids)))
        educator_share = len(req.worker_ids) - requester_share
        if requester is not None and requester_share > 0:
            if requester.inventory.get(ResourceType.PASSENGER_SEATS) < requester_share:
                return False
        if educator.inventory.get(ResourceType.PASSENGER_SEATS) < educator_share:
            return False
        if requester is not None and requester_share > 0:
            requester.give_resources(ResourceType.PASSENGER_SEATS, requester_share)
        if educator_share > 0:
            educator.give_resources(ResourceType.PASSENGER_SEATS, educator_share)
        return True

    @staticmethod
    def courses_needed(num_trainees: int) -> int:
        """How many Course slots a training batch consumes.

        A Course is a classroom of up to MAX_CLASS_SIZE_PER_COURSE
        trainees; larger batches auto-split across multiple Courses.
        """
        if num_trainees <= 0:
            return 0
        return -(-num_trainees // MAX_CLASS_SIZE_PER_COURSE)  # ceil division

    def _training_capacity_status(self, educator: Player, req) -> tuple[bool, str]:
        """Can this batch be admitted?  Pure check — no side effects.

        Manager-tier and Technician-tier training are gated by per-course
        staffing commitments. Staff are not debited, but approved or
        dispatched requests hold capacity until they complete or reject.
        Returns (ok, reason); reason is empty when ok.
        """
        band = band_of(req.target_profession)
        n_courses = 1
        need_courses = self.courses_needed(len(req.worker_ids))
        if band == WorkerBand.MANAGER:
            prof = educator.workforce.count_profession(Profession.PROFESSOR.value)
            lect = educator.workforce.count_profession(Profession.LECTURER.value)
            max_concurrent = self._manager_course_capacity(educator)
            in_flight = self.training.manager_courses_in_flight(educator.player_id)
            if max_concurrent - in_flight < n_courses:
                return False, (
                    f"Manager-course staffing full: {in_flight}/{max_concurrent} "
                    f"concurrent courses (need 0.5 Professor + 1 Lecturer per course; "
                    f"have {prof} Professor(s), {lect} Lecturer(s))."
                )
            if educator.inventory.get(ResourceType.EXPERTISE) < 2 * n_courses:
                return False, f"needs {2 * n_courses} Expertise for this course."
            have = educator.inventory.get(ResourceType.COURSES)
            if have < need_courses:
                return False, (
                    f"needs {need_courses} Course slot(s) "
                    f"({have} on hand)."
                )
            return True, ""
        if band == WorkerBand.TECHNICIAN:
            td = educator.workforce.count_profession(Profession.TECHNICAL_DIRECTOR.value)
            inst = educator.workforce.count_profession(Profession.INSTRUCTOR.value)
            workshop_seats = technical_workshop_trainee_capacity(
                CAPITAL_CATALOGUE, educator.capital_inventory
            )
            if workshop_seats <= 0:
                return False, (
                    "no Technical Workshop on the Education Island "
                    "(prerequisite for technical courses)."
                )
            # Staffing gate — per-course (Technical Director supervises 2
            # concurrent courses; Instructor leads 1).
            max_concurrent = self._technical_course_capacity(educator)
            courses_in_flight = self.training.technical_courses_in_flight(educator.player_id)
            if max_concurrent - courses_in_flight < n_courses:
                return False, (
                    f"Technical-course staffing full: {courses_in_flight}/{max_concurrent} "
                    f"concurrent courses (need 0.5 Technical Director + 1 Instructor per course; "
                    f"have {td} Technical Director(s), {inst} Instructor(s))."
                )
            # Workshop gate — per-trainee (each workshop holds 6 trainees
            # at once; sum trainee headcount across all in-flight batches).
            trainees_in_flight = self.training.technical_trainees_in_flight(educator.player_id)
            batch_trainees = len(req.worker_ids)
            if workshop_seats - trainees_in_flight < batch_trainees:
                return False, (
                    f"Technical Workshop capacity full: "
                    f"{trainees_in_flight}/{workshop_seats} trainee seat(s) "
                    f"already in training (need {batch_trainees} more for this batch)."
                )
            if educator.inventory.get(ResourceType.EXPERTISE) < n_courses:
                return False, f"needs {n_courses} Expertise for this course."
            have = educator.inventory.get(ResourceType.COURSES)
            if have < need_courses:
                return False, (
                    f"needs {need_courses} Course slot(s) "
                    f"({have} on hand)."
                )
            return True, ""
        return True, ""

    def _manager_course_capacity(self, educator: Player) -> int:
        prof = educator.workforce.count_profession(Profession.PROFESSOR.value)
        lect = educator.workforce.count_profession(Profession.LECTURER.value)
        return min(prof * 2, lect)

    def _technical_course_capacity(self, educator: Player) -> int:
        """Staffing-only capacity (per concurrent course).  The workshop
        cap is a separate per-trainee gate — see ``_training_capacity_status``."""
        td = educator.workforce.count_profession(Profession.TECHNICAL_DIRECTOR.value)
        inst = educator.workforce.count_profession(Profession.INSTRUCTOR.value)
        return min(td * 2, inst)

    def _consume_training_capacity(self, educator: Player, req) -> str:
        """Debit the capacity this batch uses; return a human description.

        Staffing capacity is held by the request's in-flight status. Course
        and Expertise resources are spent at approval/dispatch.
        """
        band = band_of(req.target_profession)
        n_courses = 1
        need_courses = self.courses_needed(len(req.worker_ids))
        if need_courses > 0:
            educator.give_resources(ResourceType.COURSES, need_courses)
        if band == WorkerBand.MANAGER:
            educator.give_resources(ResourceType.EXPERTISE, 2 * n_courses)
            return (
                f"{need_courses} Course slot(s) + 2 Expertise "
                "for the Manager-tier course"
            )
        if band == WorkerBand.TECHNICIAN:
            educator.give_resources(ResourceType.EXPERTISE, n_courses)
            return (
                f"{need_courses} Course slot(s) + 1 Expertise "
                "for the technical course"
            )
        return f"{need_courses} Course slot(s)"

    def _profession_label(self, profession: str) -> str:
        try:
            return PROFESSION_LABEL.get(Profession(profession), profession)
        except ValueError:
            return profession

    def _format_training_return(self, req) -> str:
        if req.return_year >= 0 and req.return_season >= 0:
            return f"Year {req.return_year + 1}, {SEASONS[req.return_season]}"
        if req.status == TrainingStatus.AWAITING_EDUCATOR:
            return "pending Educator approval"
        if req.status == TrainingStatus.COUNTERED:
            return "pending requester approval"
        if req.status == TrainingStatus.AWAITING_TRANSPORT:
            return "pending transport"
        return "not scheduled"

    def _print_training_status_for_player(self, player: Player) -> None:
        active = self.training.active_for_player(player.player_id)
        if not active:
            self.io.print("  No workers are currently in training or awaiting departure.")
            return

        self.io.print("  Current training pipeline:")
        grouped: dict[tuple[str, str, TrainingStatus], int] = {}
        for req in active:
            key = (
                self._profession_label(req.target_profession),
                self._format_training_return(req),
                req.status,
            )
            grouped[key] = grouped.get(key, 0) + len(req.worker_ids)

        for (profession, return_text, status), count in sorted(grouped.items()):
            self.io.print(
                f"    {profession:<22} {count:>2} worker(s)  "
                f"| return: {return_text}  | status: {status.value}"
            )

    def _training_request_details(self, req, player_names: dict[int, str], requester: Player | None = None) -> str:
        sym = CURRENCY_SYMBOL
        requester_tickets = max(0, min(req.tickets_supplied_by_requester, len(req.worker_ids)))
        educator_tickets = len(req.worker_ids) - requester_tickets
        ticket_need = len(req.worker_ids) if req.transport_mode == "air_ticket" else 0
        travel = (
            f"{ticket_need} PassengerSeats total: requester supplies "
            f"{requester_tickets}, Education Island supplies {educator_tickets}"
            if req.transport_mode == "air_ticket"
            else req.transport_mode
        )
        funds = f" | requester cash: {requester.dollops:.1f} {sym}" if requester else ""
        msg = f" | message: {req.counter_message}" if req.counter_message else ""
        return (
            f"{req.describe(player_names)}\n"
            f"    Workers: {len(req.worker_ids)}  | Profession: {self._profession_label(req.target_profession)}\n"
            f"    Offered educator fee: {req.dollops_to_educator:.1f} {sym}{funds}\n"
            f"    Travel: {travel}{msg}"
        )

    def _training_request_summary(
        self, req, player_names: dict[int, str], requester: Player | None = None
    ) -> dict:
        sym = CURRENCY_SYMBOL
        requester_name = player_names.get(req.requester_id, f"Player{req.requester_id}")
        band = band_of(req.target_profession)
        away = away_seasons(req.target_profession)
        requester_tickets = max(0, min(req.tickets_supplied_by_requester, len(req.worker_ids)))
        educator_tickets = len(req.worker_ids) - requester_tickets
        ticket_price = self.market.current_price(ResourceType.PASSENGER_SEATS)
        suggested_floor = 20.0 * len(req.worker_ids) + ticket_price * educator_tickets
        fields = [
            ("Requester:", requester_name),
            ("Trainees:", f"{len(req.worker_ids)} worker(s)"),
            (
                "Target profession:",
                f"{self._profession_label(req.target_profession)} "
                f"({band.value}, {away} season(s) away)",
            ),
            ("Educator fee:", f"{req.dollops_to_educator:.1f} {sym} offered"),
            (
                "Transport:",
                (
                    f"Air ticket — requester supplies {requester_tickets} of "
                    f"{len(req.worker_ids)}, Educator supplies {educator_tickets}"
                    if req.transport_mode == "air_ticket"
                    else req.transport_mode
                ),
            ),
            (
                "Suggested floor:",
                (
                    f"20 × {len(req.worker_ids)} + "
                    f"price(PassengerSeats) × {educator_tickets} = "
                    f"{suggested_floor:.0f} {sym}"
                ),
            ),
            ("Status:", req.status.value),
        ]
        if requester is not None:
            fields.append(
                (
                    "Workforce impact:",
                    f"{len(req.worker_ids)} of {requester.workforce.active_count} "
                    f"active worker(s) depart for {away} season(s)",
                )
            )
        if req.counter_message:
            fields.append(("Message:", req.counter_message))
        return {
            "title": f"Training request #{req.batch_id} from {requester_name}",
            "batch_id": req.batch_id,
            "requester_id": req.requester_id,
            "requester_name": requester_name,
            "trainee_count": len(req.worker_ids),
            "target_profession": self._profession_label(req.target_profession),
            "target_profession_value": req.target_profession,
            "worker_band": band.value,
            "away_seasons": away,
            "transport_mode": req.transport_mode,
            "tickets_supplied_by_requester": requester_tickets,
            "tickets_supplied_by_educator": educator_tickets,
            "dollops_to_educator": round(req.dollops_to_educator, 1),
            "suggested_floor": round(suggested_floor, 1),
            "status": req.status.value,
            "fields": fields,
        }

    def _confirm_with_request_summary(self, prompt: str, summary: dict) -> bool:
        try:
            return self.io.confirm(prompt, request_summary=summary)
        except TypeError:
            return self.io.confirm(prompt)

    def _approve_training_request(
        self,
        educator: Player,
        requester: Player,
        req,
        result: TurnResult,
        season_name: str,
        year: int,
    ) -> bool:
        if not self._training_workers_ready(requester, req):
            return False
        # Peek training capacity BEFORE consuming any air tickets so a
        # capacity shortfall doesn't burn the Educator's PassengerSeats.
        ok, gate_msg = self._training_capacity_status(educator, req)
        if not ok:
            self.io.print(
                f"  Cannot approve yet — Education Island {gate_msg} "
                f"The request stays pending."
            )
            return False
        if req.transport_mode == "air_ticket" and not self._ensure_training_air_tickets(educator, req, requester):
            requester_tickets = max(0, min(req.tickets_supplied_by_requester, len(req.worker_ids)))
            educator_tickets = len(req.worker_ids) - requester_tickets
            educator_short = max(
                0,
                educator_tickets - educator.inventory.get(ResourceType.PASSENGER_SEATS),
            )
            requester_short = max(
                0,
                requester_tickets - requester.inventory.get(ResourceType.PASSENGER_SEATS),
            )
            self.io.print(
                f"  Cannot approve yet — PassengerSeats shortfall; requester needs "
                f"{requester_short} more and Education Island needs {educator_short} more "
                f"PassengerSeats. Requester must supply {requester_tickets}; "
                f"Education Island must supply {educator_tickets}."
            )
            return False
        # Tickets secured; now consume Course and Expertise resources.
        self._consume_training_capacity(educator, req)
        requester.spend_dollops(req.dollops_to_educator)
        educator.receive_dollops(req.dollops_to_educator)
        if req.status == TrainingStatus.COUNTERED:
            self.training.requester_accept_counter(req.batch_id)
        else:
            self.training.educator_approve(req.batch_id)
        self.io.print(
            f"  Approved. Received {req.dollops_to_educator:.0f} Dp from {requester.name}."
        )
        if req.transport_mode == "air_ticket":
            self.io.print(
                f"  Used {req.tickets_supplied_by_requester} requester PassengerSeats "
                f"and {self._educator_ticket_count(req)} Educator PassengerSeats for trainee travel."
            )
            self._dispatch_training(requester, req, season_name, year)
        elif req.transport_mode in ("flight", "cargo"):
            if req.transport_mode == "flight" and req.dollops_to_transporter > 0:
                requester.spend_dollops(req.dollops_to_transporter)
                self.io.print(
                    f"  Flight booked — {req.dollops_to_transporter:.0f} Dp deducted from {requester.name}."
                )
            self._dispatch_training(requester, req, season_name, year)
        else:
            self._auto_arrange_transport(requester, req, season_name, year)
        result.actions_taken.append(f"approved_training:batch#{req.batch_id}")
        return True

    def _review_training_counteroffers(
        self, player: Player, result: TurnResult, season_name: str, year: int
    ) -> None:
        counters = self.training.countered_for_requester(player.player_id)
        if not counters:
            return
        player_names = {p.player_id: p.name for p in self.players}
        player_map = {p.player_id: p for p in self.players}
        self.io.print(f"  You have {len(counters)} training counter-offer(s).")
        for req in counters:
            educator = player_map.get(req.educator_id)
            if not educator:
                self.training.requester_reject_counter(req.batch_id)
                self.io.print(f"  Counter-offer #{req.batch_id} expired — Educator is no longer available.")
                continue
            self.io.print(f"\n  Counter-offer: {self._training_request_details(req, player_names, player)}")
            summary = self._training_request_summary(req, player_names, player)
            if self._confirm_with_request_summary("Accept this training counter-offer?", summary):
                try:
                    self._approve_training_request(educator, player, req, result, season_name, year)
                except Exception as exc:
                    self.io.print(f"  Could not accept counter-offer #{req.batch_id}: {exc}")
            else:
                self.training.requester_reject_counter(req.batch_id)
                self.io.print(f"  Rejected training counter-offer #{req.batch_id}.")
                result.actions_taken.append(f"rejected_training_counter:batch#{req.batch_id}")

    def _action_review_training(
        self, player: Player, result: TurnResult, season_name: str, year: int
    ) -> None:
        """Educator reviews pending training requests and approves or rejects them."""
        if not any(r.name == "Educator" for r in player.roles):
            self._print_training_status_for_player(player)
            return
        on_campus = self.training.visiting_trainees(player.player_id)
        if on_campus:
            self.io.print(
                f"  Campus load: {on_campus} visiting trainee(s) on the Education "
                f"Island this season → +{on_campus} Food demand until they return."
            )
        pending = self.training.pending_for_educator(player.player_id)
        if not pending:
            self.io.print("  No training requests awaiting your approval.")
            return
        player_names = {p.player_id: p.name for p in self.players}
        player_map = {p.player_id: p for p in self.players}
        for req in pending:
            requester = player_map[req.requester_id]
            self.io.print(f"\n  Request: {self._training_request_details(req, player_names, requester)}")
            summary = self._training_request_summary(req, player_names, requester)
            if self._confirm_with_request_summary("Approve this training request?", summary):
                self._approve_training_request(player, requester, req, result, season_name, year)
            else:
                counter = self.io.ask_dollop_amount(
                    "Counter price to Educator in Dp? (0 = reject request)",
                    1_000_000.0,
                )
                if counter > 0:
                    message = self.io.ask_text(
                        "Message to requester",
                        "I can train them at this revised price.",
                    )
                    self.training.educator_counter(req.batch_id, counter, message)
                    self.io.print(
                        f"  Countered request #{req.batch_id} at {counter:.0f} Dp. "
                        f"{requester.name} will respond on their turn."
                    )
                    result.actions_taken.append(f"countered_training:batch#{req.batch_id}")
                else:
                    self.training.educator_reject(req.batch_id)
                    self.io.print("  Rejected.")
                    result.actions_taken.append(f"rejected_training:batch#{req.batch_id}")

    def _action_arrange_transport(
        self, player: Player, result: TurnResult, season_name: str, year: int
    ) -> None:
        """Transporter reviews pending transport jobs and accepts them."""
        if not any(r.name == "Transporter" for r in player.roles):
            self.io.print("  Only the Transporter can arrange worker transport.")
            return
        pending = self.training.pending_transport()
        if not pending:
            self.io.print("  No transport requests awaiting arrangement.")
            return
        player_names = {p.player_id: p.name for p in self.players}
        player_map = {p.player_id: p for p in self.players}
        for req in pending:
            self.io.print(f"\n  Transport job: {req.describe(player_names)}")
            dollops_offered = req.dollops_to_transporter
            counter = self.io.ask_dollop_amount(
                f"Accept {dollops_offered:.0f} Dp, or enter counter-offer? (0 = accept as-is)",
                1_000_000.0,
            )
            if counter > 0:
                dollops_offered = counter
            if self.io.confirm(f"Arrange transport for {dollops_offered:.0f} Dp?"):
                requester = player_map[req.requester_id]
                if requester.dollops < dollops_offered:
                    self.io.print(f"  {requester.name} cannot afford {dollops_offered:.0f} Dp.")
                    continue
                if not self._training_workers_ready(requester, req):
                    continue
                requester.spend_dollops(dollops_offered)
                player.receive_dollops(dollops_offered)
                self.training.arrange_transport(req.batch_id, player.player_id, dollops_offered)
                if self._dispatch_training(requester, req, season_name, year):
                    result.actions_taken.append(f"transport_arranged:batch#{req.batch_id}")
            else:
                self.io.print("  Declined.")

    def _action_recruit_workers(self, player: Player, result: TurnResult) -> None:
        """Draw unskilled workers from the island's population pool."""
        available = player.available_unskilled
        if available <= 0:
            self.io.print(
                f"  No unskilled residents available to recruit right now. "
                f"(Population: {player.population}, employed: {player.workforce.count})"
            )
            return
        self.io.print(
            f"  Available unskilled recruits: {available} "
            f"(population {player.population}, employed {player.workforce.count})"
        )
        try:
            count = self.io.choose_quantity("How many workers to recruit?", 1, available)
            if count <= 0:
                self.io.print("  Recruitment cancelled.")
                return
            recruited = player.recruit_workers(count)
        except Exception as exc:
            self.io.print(f"  Recruitment failed: {exc}")
            return
        self.io.print(
            f"  Recruited {recruited} unskilled worker(s). "
            f"Workforce now: {player.workforce.count}"
        )
        result.actions_taken.append(f"recruit:{recruited}_workers")

    def _action_sell_insurance(
        self, player: Player, result: TurnResult, year: int, season_index: int
    ) -> None:
        """Banker sells a life or medical insurance policy to another player."""
        if not any(r.name == "Banker" for r in player.roles):
            self.io.print("  Only the Banker can sell insurance policies.")
            return
        sym = CURRENCY_SYMBOL
        eligible = [p for p in self.players if p.player_id != player.player_id]
        if not eligible:
            self.io.print("  No other players to sell insurance to.")
            return

        self.io.print("\n  Insurance Products Available:")
        self.io.print(
            f"    1. Life Insurance     — pays {LIFE_INSURANCE_DEATH_BENEFIT:.0f} {sym} death benefit per fatality\n"
            f"       Base premium: {INSURANCE_BASE_PREMIUM['life']:.0f} {sym}  |  covers 1 year (4 seasons)"
        )
        self.io.print(
            f"    2. Medical Insurance  — halves seasonal injury-absence rate ({MEDICAL_INSURANCE_INJURY_REDUCTION*100:.0f}% reduction)\n"
            f"       Base premium: {INSURANCE_BASE_PREMIUM['medical']:.0f} {sym}  |  covers 1 year (4 seasons)"
        )
        self.io.print("\n  High-hazard roles: Farmer, Miner, Transporter, Manufacturer")

        choice = self.io.choose_quantity("Policy type [1=Life / 2=Medical]:", 1, 2)
        policy_type = "life" if choice == 1 else "medical"
        base = INSURANCE_BASE_PREMIUM[policy_type]

        buyer = self.io.choose_player("Sell to which player?", eligible)

        # Show current cover for buyer
        existing = buyer.active_policies(year, season_index)
        existing_same = [p for p in existing if p.policy_type == policy_type]
        if existing_same:
            self.io.print(
                f"  Note: {buyer.name} already holds an active {policy_type} policy."
            )

        premium = self.io.ask_dollop_amount(
            f"Set premium ({sym})? [base: {base:.0f} {sym}]", buyer.dollops
        )
        if premium <= 0:
            self.io.print("  Premium must be positive.")
            return
        if buyer.dollops < premium:
            self.io.print(f"  {buyer.name} cannot afford {premium:.0f} {sym}.")
            return
        if not self.io.confirm(
            f"Sell {policy_type} insurance to {buyer.name} for {premium:.0f} {sym}?"
        ):
            return

        buyer.spend_dollops(premium)
        player.receive_dollops(premium)
        policy_id = len(buyer.insurance_policies) + 1
        purchased_tick = year * 4 + season_index
        policy = InsurancePolicy(
            policy_id=policy_id,
            policy_type=policy_type,
            holder_player_id=buyer.player_id,
            banker_player_id=player.player_id,
            premium_paid=premium,
            purchased_tick=purchased_tick,
            expires_at_tick=purchased_tick + INSURANCE_DURATION_SEASONS,
        )
        buyer.add_insurance_policy(policy)
        self.io.print(
            f"  Policy issued: {policy.describe()}  "
            f"— {buyer.name} paid {premium:.0f} {sym}"
        )
        result.actions_taken.append(f"sell_insurance:{policy_type}:{buyer.name}")

    def _action_buy_insurance(
        self, player: Player, result: TurnResult, year: int, season_index: int
    ) -> None:
        """Any player buys an insurance policy from an available Banker."""
        sym = CURRENCY_SYMBOL
        # Check player is at risk
        risk = {}
        for role in player.roles:
            r = WORKPLACE_RISK.get(role.name, {})
            if r.get("injury_rate", 0) or r.get("fatality_rate", 0):
                risk = r
                break
        if not risk:
            self.io.print(
                "  Your island has no workplace hazards — insurance is not applicable."
            )
            return

        bankers = [p for p in self.players if any(r.name == "Banker" for r in p.roles)]
        if not bankers:
            self.io.print("  No Banker player in this game.")
            return
        banker = self.io.choose_player("Buy from which Banker?", bankers)

        self.io.print("\n  Available policies:")
        self.io.print(
            f"    1. Life Insurance     — {LIFE_INSURANCE_DEATH_BENEFIT:.0f} {sym}/fatality benefit\n"
            f"       (fatality rate this role: ~{risk.get('fatality_rate',0)*100:.0f}%/season/worker)"
        )
        self.io.print(
            f"    2. Medical Insurance  — {MEDICAL_INSURANCE_INJURY_REDUCTION*100:.0f}% injury-rate reduction\n"
            f"       (injury rate this role: ~{risk.get('injury_rate',0)*100:.0f}%/season/worker)"
        )
        # Show existing cover
        existing = player.active_policies(year, season_index)
        if existing:
            self.io.print("  Current active policies:")
            for pol in existing:
                self.io.print(f"    {pol.describe()}")

        choice = self.io.choose_quantity("Policy type [1=Life / 2=Medical]:", 1, 2)
        policy_type = "life" if choice == 1 else "medical"
        base = INSURANCE_BASE_PREMIUM[policy_type]

        premium = self.io.ask_dollop_amount(
            f"Offer premium to {banker.name} ({sym})? [base: {base:.0f}]", player.dollops
        )
        if premium <= 0:
            self.io.print("  Premium must be positive.")
            return

        # If Banker is AI, auto-accept if premium >= base
        if not banker.is_human:
            if premium < base * 0.9:
                self.io.print(
                    f"  [AI] {banker.name} declined — offer at least {base:.0f} {sym}."
                )
                return
        elif not self.io.confirm(
            f"Confirm: {banker.name} issues {policy_type} policy for {premium:.0f} {sym}?"
        ):
            return

        if player.dollops < premium:
            self.io.print(f"  You cannot afford {premium:.0f} {sym}.")
            return

        player.spend_dollops(premium)
        banker.receive_dollops(premium)
        policy_id = len(player.insurance_policies) + 1
        purchased_tick = year * 4 + season_index
        policy = InsurancePolicy(
            policy_id=policy_id,
            policy_type=policy_type,
            holder_player_id=player.player_id,
            banker_player_id=banker.player_id,
            premium_paid=premium,
            purchased_tick=purchased_tick,
            expires_at_tick=purchased_tick + INSURANCE_DURATION_SEASONS,
        )
        player.add_insurance_policy(policy)
        self.io.print(f"  Issued: {policy.describe()}")
        result.actions_taken.append(f"buy_insurance:{policy_type}")

    def _action_market_buy(self, player: Player, result: TurnResult) -> None:
        sym = CURRENCY_SYMBOL
        summary = self.market.market_summary()
        offered = {
            ResourceType(k): v for k, v in summary.items()
            if v.get("ask_quantity", v.get("quantity", 0)) > 0
        }
        if hasattr(self.io, 'market_buy_bulk'):
            payload = self.io.market_buy_bulk(player, summary)
            if not payload:
                return
            if "buy" in payload or "bids" in payload:
                orders = payload.get("buy", {}) or {}
                bids = payload.get("bids", {}) or {}
            else:
                orders = payload
                bids = {}
            for rtype_str, qty in orders.items():
                if qty <= 0:
                    continue
                rtype = ResourceType(rtype_str)
                try:
                    cost, bought = self.market.buy_from_offers(player, rtype, qty)
                    self.io.print(
                        f"  Bought {bought}x {rtype.value} for {cost:.2f} {sym}"
                    )
                    result.actions_taken.append(f"buy:{bought}x{rtype.value}")
                except Exception as e:
                    self.io.print(f"  Buy {rtype.value} failed: {e}")
            for rtype_str, bid_data in bids.items():
                try:
                    rtype = ResourceType(rtype_str)
                    qty = int(bid_data.get("quantity", 0))
                    price = float(bid_data.get("price", 0))
                    if qty <= 0 or price <= 0:
                        continue
                    bid = self.market.post_bid(player, rtype, price, qty)
                    self.io.print(
                        f"  Bid posted for {qty}x {rtype.value} at "
                        f"{bid.price_per_unit:.2f} {sym}/unit"
                    )
                    result.actions_taken.append(
                        f"bid:{qty}x{rtype.value}@{bid.price_per_unit:.2f}"
                    )
                    filled = bid.quantity - bid.remaining
                    if filled > 0:
                        self.io.print(
                            f"  Bought {filled}x {rtype.value} immediately from matching asks "
                            f"for {filled * bid.price_per_unit:.2f} {sym}"
                        )
                        result.actions_taken.append(f"buy:{filled}x{rtype.value}")
                except Exception as e:
                    self.io.print(f"  Bid {rtype_str} failed: {e}")
        else:
            if not offered and not self.io.confirm("No asks are available. Place a bid instead?"):
                return
            if not offered or self.io.confirm("Place a bid instead of buying from asks?"):
                rtype = self.io.choose_resource("Bid for which resource?", list(ResourceType))
                max_qty = 99
                qty = self.io.choose_quantity(f"How many {rtype.value}?", 1, max_qty)
                ref_price = self.market.current_price(rtype)
                price = self.io.ask_dollop_amount(
                    f"Your bid price per unit (ref: {ref_price:.2f})?", player.dollops
                )
                try:
                    bid = self.market.post_bid(player, rtype, price, qty)
                    self.io.print(
                        f"  Bid posted for {qty}x {rtype.value} at "
                        f"{bid.price_per_unit:.2f} {sym}/unit"
                    )
                    result.actions_taken.append(
                        f"bid:{qty}x{rtype.value}@{bid.price_per_unit:.2f}"
                    )
                    filled = bid.quantity - bid.remaining
                    if filled > 0:
                        self.io.print(
                            f"  Bought {filled}x {rtype.value} immediately from matching asks "
                            f"for {filled * bid.price_per_unit:.2f} {sym}"
                        )
                        result.actions_taken.append(f"buy:{filled}x{rtype.value}")
                except Exception as e:
                    self.io.print(f"  Bid failed: {e}")
                return
            rtype = self.io.choose_resource(
                "Buy which resource?",
                [ResourceType(k) for k, v in summary.items()
                 if v.get("ask_quantity", v.get("quantity", 0)) > 0],
            )
            offers = self.market.available_offers(rtype)
            total_avail = sum(o.remaining for o in offers)
            best = offers[0] if offers else None
            if best:
                self.io.print(
                    f"  Best price: {best.price_per_unit:.2f} {sym}/unit  "
                    f"({total_avail} available)"
                )
            qty = self.io.choose_quantity(f"How many {rtype.value}?", 1, total_avail)
            if self.io.confirm("Confirm buy?"):
                try:
                    cost, bought = self.market.buy_from_offers(player, rtype, qty)
                    self.io.print(f"  Bought {bought}x {rtype.value} for {cost:.2f} {sym}")
                    result.actions_taken.append(f"buy:{bought}x{rtype.value}")
                except Exception as e:
                    self.io.print(f"  Failed: {e}")

    def _action_market_sell(self, player: Player, result: TurnResult) -> None:
        sym = CURRENCY_SYMBOL
        has = {r: player.inventory.get(r) for r in ResourceType if player.inventory.get(r) > 0}
        if not has:
            self.io.print("  You have nothing to sell.")
            return
        rtype = self.io.choose_resource("Sell which resource?", list(has.keys()))
        max_qty = has[rtype]
        qty = self.io.choose_quantity(f"How many {rtype.value}?", 1, max_qty)
        best_bid = self.market.best_bid(rtype)
        if best_bid:
            total_bid_qty = sum(b.remaining for b in self.market.available_bids(rtype))
            self.io.print(
                f"  Best bid: {best_bid.price_per_unit:.2f} {sym}/unit "
                f"({total_bid_qty} wanted)"
            )
            if qty <= total_bid_qty and self.io.confirm("Sell immediately into bids?"):
                try:
                    paid, sold = self.market.sell_to_bids(player, rtype, qty, self.players)
                    self.io.print(f"  Sold {sold}x {rtype.value} for {paid:.2f} {sym}")
                    result.actions_taken.append(f"sell_bid:{sold}x{rtype.value}")
                except Exception as e:
                    self.io.print(f"  Failed: {e}")
                return
        ref_price = self.market.current_price(rtype)
        # #22.4 — if a bid exists, pre-fill the asking price with the best
        # bid so the seller starts from a price that would clear immediately.
        prefill = best_bid.price_per_unit if best_bid else ref_price
        self.io.print(
            f"  Reference price: {ref_price:.2f} {sym}/unit"
            + (f"  |  best bid: {best_bid.price_per_unit:.2f} {sym}/unit"
               if best_bid else "")
        )
        price = self.io.ask_dollop_amount(
            f"Your asking price per unit (ref: {ref_price:.2f})?",
            ref_price * 5,
            prefill=prefill,
        )
        if price <= 0:
            self.io.print("  Cancelled — price must be positive.")
            return
        try:
            offer = self.market.post_offer(player, rtype, price, qty)
            self.io.print(
                f"  Listed {qty}x {rtype.value} at {price:.2f} {sym}/unit "
                f"(total {offer.total_cost:.2f} {sym})"
            )
            result.actions_taken.append(f"sell:{qty}x{rtype.value}@{price:.2f}")
        except Exception as e:
            self.io.print(f"  Failed: {e}")

    def _action_propose_deal(self, player: Player, result: TurnResult) -> None:
        sym = CURRENCY_SYMBOL
        others = [p for p in self.players if p.player_id != player.player_id]
        if not others:
            self.io.print("  No other players to deal with.")
            return
        target = self.io.choose_player("Deal with which player?", others)
        if target is None:
            self.io.print("  Deal cancelled.")
            return
        has = [r for r in ResourceType if player.inventory.get(r) > 0]
        offer_r = self.io.choose_resource("Offer which resource?", has) if has else None
        offer_qty = (
            self.io.choose_quantity("Offer quantity?", 0, player.inventory.get(offer_r))
            if offer_r else 0
        )
        wants = [r for r in ResourceType if target.inventory.get(r) > 0]
        req_r = self.io.choose_resource("Request which resource?", wants) if wants else None
        req_qty = (
            self.io.choose_quantity("Request quantity?", 0, target.inventory.get(req_r))
            if req_r else 0
        )
        sweetener = self.io.ask_dollop_amount(
            f"Dollop sweetener (positive=you pay, negative=you receive)?", player.dollops
        )
        if not offer_r and not req_r and sweetener == 0:
            self.io.print("  Deal cancelled — nothing offered or requested.")
            return
        if (offer_qty <= 0 and req_qty <= 0 and sweetener == 0):
            self.io.print("  Deal cancelled — nothing offered or requested.")
            return
        try:
            deal = self.trading.propose_deal(
                player, target, offer_r, offer_qty, req_r, req_qty, sweetener
            )
            self.io.print(f"  Proposed: {deal.summary(player.name, target.name)}")
            if not target.is_human:
                prices = self.market.current_prices()
                offered_val = (
                    offer_qty * prices.get(offer_r, 0) if offer_r else 0
                ) + max(sweetener, 0)
                requested_val = (
                    req_qty * prices.get(req_r, 0) if req_r else 0
                ) + max(-sweetener, 0)
                if requested_val <= offered_val * 1.1:
                    self.trading.accept_deal(deal, target, player)
                    self.io.print(f"  {target.name} accepted the deal.")
                    result.actions_taken.append("deal:accepted")
                else:
                    self.trading.reject_deal(deal)
                    self.io.print(f"  {target.name} rejected the deal.")
            else:
                self.io.print(f"  Waiting for {target.name} to respond on their turn.")
        except Exception as e:
            self.io.print(f"  Deal failed: {e}")

    def _review_pending_deals(self, player: Player, result: TurnResult) -> None:
        pending = self.trading.ledger.pending_for_player(player.player_id)
        if not pending:
            return

        player_map = {p.player_id: p for p in self.players}
        player_names = {p.player_id: p.name for p in self.players}
        self.io.print(f"  You have {len(pending)} pending deal proposal(s).")
        for deal in pending:
            proposer = player_map.get(deal.proposer_id)
            if proposer is None:
                self.trading.ledger.expire(deal.deal_id)
                self.io.print(f"  Deal #{deal.deal_id} expired — proposer is no longer available.")
                result.actions_taken.append(f"deal:expired:{deal.deal_id}")
                continue

            summary = deal.summary(
                player_names.get(deal.proposer_id, f"Player {deal.proposer_id}"),
                player.name,
            )
            if self.io.confirm(f"{summary}\nAccept this deal?"):
                try:
                    self.trading.accept_deal(deal, acceptor=player, proposer=proposer)
                    self.io.print(f"  Accepted deal #{deal.deal_id}.")
                    result.actions_taken.append(f"deal:accepted:{deal.deal_id}")
                except Exception as exc:
                    self.trading.ledger.expire(deal.deal_id)
                    self.io.print(f"  Deal #{deal.deal_id} expired — {exc}")
                    result.actions_taken.append(f"deal:expired:{deal.deal_id}")
            else:
                self.trading.reject_deal(deal)
                self.io.print(f"  Rejected deal #{deal.deal_id}.")
                result.actions_taken.append(f"deal:rejected:{deal.deal_id}")

    def _format_market(self) -> str:
        sym = CURRENCY_SYMBOL
        lines = ["\n  Market Prices:"]
        for r in ResourceType:
            price = self.market.current_price(r)
            supply = self.market.supply.get(r, 0)
            lines.append(f"    {r.value:<18} {price:>7.2f} {sym}  supply:{supply}")
        return "\n".join(lines)

    def _format_players(self, current: Player, year: int = 0, season_index: int = 0) -> str:
        """Show all players: roles, island, produces, capacity, Dollops, wealth, workers."""
        from ..models.role import ROLES
        sym = CURRENCY_SYMBOL
        prices = self.market.current_prices()
        current_tick = year * len(SEASONS) + season_index
        lines = ["\n  ┌── ALL PLAYERS ─────────────────────────────────────────┐"]
        for p in self.players:
            marker = " ◀ YOU" if p.player_id == current.player_id else ""
            lines.append(
                f"  │  {p.name}{marker}"
            )
            lines.append(
                f"  │    Roles: {p.role_names()}"
            )
            # Show island name and what each role produces / needs
            for role in p.roles:
                produces_str = ", ".join(r.value for r in role.produces) or "—"
                needs_str = ", ".join(r.value for r in role.needs) or "—"
                lines.append(
                    f"  │      [{role.island}]  "
                    f"produces: {produces_str}  |  needs: {needs_str}"
                )
            ws = p.workforce.summary()
            lines.append(
                f"  │    Dollops: {p.dollops:.1f} {sym}  |  "
                f"Net Wealth: "
                f"{p.total_wealth(prices, self.loan_ledger, CAPITAL_CATALOGUE, current_tick):.1f} {sym}  |  "
                f"Workers: {ws['active']}/{ws['total']}  |  "
                f"Capacity: {p.production_capacity*100:.0f}%"
            )
            lines.append("  │")
        lines[-1] = "  └" + "─" * 56 + "┘"
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Loans
    # ------------------------------------------------------------------

    def _lease_item_name(self, item_id: str) -> str:
        item = find_item(CAPITAL_CATALOGUE, item_id)
        return item.name if item else item_id

    def _transfer_lease_payment(self, lessee: Player, lessor: Player | None, amount: float) -> None:
        lessee.dollops -= amount
        if lessor and lessor.player_id != lessee.player_id:
            lessor.dollops += amount

    def _remove_leased_item(self, lessee: Player, item_id: str) -> None:
        if lessee.capital_inventory.get(item_id, 0) > 0:
            lessee.remove_capital(item_id, 1)

    def _process_lease_reinstatements(self, year: int, season: int) -> None:
        player_map = {p.player_id: p for p in self.players}
        for lease in self.lease_ledger.all_leases():
            if (
                lease.status == LeaseStatus.REPOSSESSED
                and lease.return_year == year
                and lease.return_season == season
            ):
                lessee = player_map.get(lease.lessee_id)
                if not lessee:
                    continue
                lessee.add_capital(lease.item_id, 1, acquired_tick=year * len(SEASONS) + season)
                self.lease_ledger.reinstate(lease.lease_id, year, season)
                self.io.print(
                    f"\n[LEASE] {self._lease_item_name(lease.item_id)} returned to {lessee.name}."
                )

    def _process_lease_payments(self, year: int, season: int) -> None:
        if season != 0:
            return
        for lease in list(self.lease_ledger.due_leases(year, season)):
            self._settle_due_lease(lease, year, season, prompt_humans=True)

    def _settle_due_lease(self, lease, year: int, season: int, prompt_humans: bool = False) -> bool:
        player_map = {p.player_id: p for p in self.players}
        lessee = player_map.get(lease.lessee_id)
        lessor = player_map.get(lease.lessor_id)
        if not lessee:
            lease.status = LeaseStatus.CANCELLED
            return False
        item_name = self._lease_item_name(lease.item_id)
        if lease.status == LeaseStatus.AWAITING_BUYOUT:
            amount = lease.buyout_payment
            should_pay = (not lessee.is_human) and lessee.dollops >= amount
            if lessee.is_human and prompt_humans:
                if hasattr(self.io, "set_active_player"):
                    self.io.set_active_player(lessee.player_id)
                should_pay = lessee.dollops >= amount and self.io.confirm(
                    f"Lease buyout due for {item_name}: pay {amount:.1f} {CURRENCY_SYMBOL} now?"
                )
            if should_pay:
                self._transfer_lease_payment(lessee, lessor, amount)
                self.lease_ledger.complete(lease.lease_id)
                self.io.print(f"\n[LEASE] {lessee.name} bought out {item_name}.")
                return True
            self._remove_leased_item(lessee, lease.item_id)
            self.lease_ledger.buyout_default(lease.lease_id)
            self.io.print(f"\n[LEASE] {lessee.name} defaulted on the {item_name} buyout.")
            return False

        amount = lease.annual_payment
        should_pay = (not lessee.is_human) and lessee.dollops >= amount
        if lessee.is_human and prompt_humans:
            if hasattr(self.io, "set_active_player"):
                self.io.set_active_player(lessee.player_id)
            should_pay = lessee.dollops >= amount and self.io.confirm(
                f"Lease payment due for {item_name}: pay {amount:.1f} {CURRENCY_SYMBOL} now?"
            )
        if should_pay:
            self._transfer_lease_payment(lessee, lessor, amount)
            self.lease_ledger.make_payment(lease.lease_id, year, season)
            self.io.print(f"\n[LEASE] {lessee.name} paid {amount:.1f} {CURRENCY_SYMBOL} for {item_name}.")
            return True
        self._remove_leased_item(lessee, lease.item_id)
        self.lease_ledger.repossess(lease.lease_id, year, season)
        self.io.print(f"\n[LEASE] {lessee.name} missed a payment; {item_name} was repossessed.")
        return False

    def _action_pay_lease(
        self, player: Player, result: TurnResult, year: int, season_index: int
    ) -> None:
        leases = [
            l for l in self.lease_ledger.all_leases()
            if l.lessee_id == player.player_id
            and l.status in (LeaseStatus.REPOSSESSED, LeaseStatus.AWAITING_BUYOUT)
        ]
        if not leases:
            self.io.print("  No lease payments are currently actionable.")
            return
        options = []
        for lease in leases:
            amount = lease.buyout_payment if lease.status == LeaseStatus.AWAITING_BUYOUT else lease.annual_payment
            options.append({
                "value": lease.lease_id,
                "label": f"{self._lease_item_name(lease.item_id)} — {amount:.1f} {CURRENCY_SYMBOL} ({lease.status.value})",
            })
        lease_id = self.io.choose_option("Pay which lease?", options)
        lease = self.lease_ledger.get(int(lease_id))
        player_map = {p.player_id: p for p in self.players}
        lessor = player_map.get(lease.lessor_id)
        if lease.status == LeaseStatus.REPOSSESSED:
            amount = lease.annual_payment
            if player.dollops < amount:
                self.io.print(f"  Need {amount:.1f} {CURRENCY_SYMBOL} to catch up this lease.")
                return
            self._transfer_lease_payment(player, lessor, amount)
            self.lease_ledger.schedule_reinstatement(lease.lease_id, year, season_index)
            self.io.print("  Catch-up paid. The item returns next season.")
            result.actions_taken.append(f"pay_lease:lease#{lease.lease_id}")
            return
        if lease.status == LeaseStatus.AWAITING_BUYOUT:
            if player.dollops < lease.buyout_payment:
                self.io.print(f"  Need {lease.buyout_payment:.1f} {CURRENCY_SYMBOL} for the buyout.")
                return
            self._transfer_lease_payment(player, lessor, lease.buyout_payment)
            self.lease_ledger.complete(lease.lease_id)
            self.io.print("  Buyout paid. You now own the item outright.")
            result.actions_taken.append(f"pay_lease_buyout:lease#{lease.lease_id}")

    def _process_loan_repayments(self, year: int, season: int) -> None:
        sym = CURRENCY_SYMBOL
        player_map = {p.player_id: p for p in self.players}
        due = self.loan_ledger.due_loans(year, season)
        for loan in due:
            borrower = player_map.get(loan.borrower_id)
            lender = player_map.get(loan.lender_id)
            if not borrower or (not lender and loan.lender_id >= 0):
                loan.status = LoanStatus.DEFAULTED
                continue
            amount = loan.repayment_amount
            lender_name = lender.name if lender else "external depositors"
            if borrower.dollops >= amount:
                borrower.dollops -= amount
                if lender and lender.player_id != borrower.player_id:
                    lender.dollops += amount
                loan.status = LoanStatus.REPAID
                self.io.print(
                    f"\n[LOAN] {borrower.name} repaid {amount:.1f} {sym} to {lender_name} "
                    f"(principal {loan.principal:.1f} + interest {loan.interest_amount:.1f})"
                )
            else:
                paid = borrower.dollops
                borrower.dollops = 0
                if lender and lender.player_id != borrower.player_id:
                    lender.dollops += paid
                loan.status = LoanStatus.DEFAULTED
                shortfall = amount - paid
                self.io.print(
                    f"\n[LOAN DEFAULT] {borrower.name} could not repay {amount:.1f} {sym} "
                    f"to {lender_name}. Paid {paid:.1f} {sym}, shortfall {shortfall:.1f} {sym}."
                )

    def _find_banker(self) -> Player | None:
        for p in self.players:
            if any(r.name == "Banker" for r in p.roles):
                return p
        return None

    def _mba_banker_count(self, banker: Player) -> int:
        """Active Banker-profession Manager workers holding an MBA."""
        return sum(
            1 for w in banker.workforce.active_workers
            if w.profession == Profession.BANKER.value and getattr(w, "has_mba", False)
        )

    def _banker_reserve_ratio(self, banker: Player) -> float:
        """5% below the MBA threshold; 2% at/above (wholesale funding)."""
        if self._mba_banker_count(banker) >= MBA_QUALIFIED_THRESHOLD:
            return MBA_RESERVE_RATIO_QUALIFIED
        return MBA_RESERVE_RATIO_BASE

    def _banker_active_loan_cap(self, banker: Player) -> int:
        """Max simultaneous active customer loans this Bank can hold."""
        n_bankers = banker.workforce.count_profession(Profession.BANKER.value)
        return max(1, 2 * n_bankers)

    def _banker_active_loan_count(self, banker: Player) -> int:
        """Active customer loans where this banker is lender.

        Synthetic depositor funding loans use ``lender_id=-1`` and are the
        bank's liability side, not customer lending; they do not count here.
        """
        return sum(
            1 for loan in self.loan_ledger.loans
            if loan.lender_id == banker.player_id
            and loan.status == LoanStatus.ACTIVE
        )

    def _banker_can_issue_loan(self, banker: Player) -> tuple[bool, int, int]:
        active = self._banker_active_loan_count(banker)
        cap = self._banker_active_loan_cap(banker)
        return active < cap, active, cap

    def _print_banker_cap_refusal(self, active: int, cap: int) -> None:
        self.io.print(
            "  Cannot issue loan: Bank already at active-loan cap "
            f"({active}/{cap}). Wait for a loan to be repaid, or train another "
            "Banker Manager to raise the cap."
        )

    def _fund_bank_external_portion(
        self,
        banker: Player,
        external_share: float,
        cost_rate: float,
        term_years: int,
        year: int,
        season_index: int,
    ) -> float:
        """Source the depositor portion of a loan at the posted funding rate.

        Phase D: every loan is funded as ``own + external``; this helper
        creates the synthetic depositor obligation (lender_id=-1) for the
        external share and credits the bank with the cash so it can hand
        the borrower the full principal.  Repaid at maturity via the
        existing `_process_loan_repayments` path.
        """
        if external_share <= 0:
            return 0.0
        funding = self.loan_ledger.create_loan(
            borrower_id=banker.player_id,
            lender_id=-1,
            principal=external_share,
            interest_rate=cost_rate,
            issued_year=year,
            issued_season=season_index,
            term_years=term_years,
        )
        banker.receive_dollops(external_share)
        self.io.print(
            f"  Bank sourced {external_share:.1f} {CURRENCY_SYMBOL} externally "
            f"at {cost_rate*100:.1f}% (depositor loan #{funding.loan_id})."
        )
        return external_share

    def _action_offer_loan(self, player: Player, result: TurnResult,
                           year: int, season_index: int) -> None:
        sym = CURRENCY_SYMBOL
        if not any(r.name == "Banker" for r in player.roles):
            self.io.print("  Only the Banker island can offer loans.")
            return
        others = [p for p in self.players if p.player_id != player.player_id]
        if not others:
            self.io.print("  No other players to lend to.")
            return
        can_issue, active, cap = self._banker_can_issue_loan(player)
        if not can_issue:
            self._print_banker_cap_refusal(active, cap)
            return
        target = self.io.choose_player("Offer loan to which player?", others)
        principal = self.io.ask_dollop_amount(
            f"Loan principal? (Bank cash {player.dollops:.1f} {sym}; can fund externally)",
            1_000_000.0,
        )
        if principal <= 0:
            self.io.print("  Cancelled — principal must be positive.")
            return
        term_years = self.io.choose_quantity("Loan term in years", 1, 3)
        funding_rate = posted_funding_rates(year, season_index)[term_years]
        rate = banker_quote_rate(
            target, self.loan_ledger, principal, term_years, year, season_index
        )
        rate_pct = rate * 100
        rate = rate_pct / 100.0
        repay = round(principal * (1 + rate), 1)
        # Phase D — reserve check: bank must hold r·P of own capital.
        r = self._banker_reserve_ratio(player)
        own_share = r * principal
        external_share = max(0.0, principal - own_share)
        if player.dollops < own_share:
            mba = self._mba_banker_count(player)
            self.io.print(
                f"  Bank cannot back this loan at {r:.0%} reserve: needs "
                f"{own_share:.1f} {sym} of own capital but has only "
                f"{player.dollops:.1f} {sym} (MBA-qualified Banker Managers: "
                f"{mba}/{MBA_QUALIFIED_THRESHOLD}). Reduce principal or train MBAs."
            )
            return
        self.io.print(
            f"  Offering {principal:.1f} {sym} to {target.name} "
            f"at {rate_pct:.1f}% — bank cost {funding_rate*100:.1f}%, "
            f"repayment {repay:.1f} {sym} after {term_years} year(s).\n"
            f"  Reserve {r:.0%}: bank locks {own_share:.1f} {sym} own capital "
            f"+ {external_share:.1f} {sym} sourced externally."
        )
        if target.is_human:
            accepted = self.io.confirm(
                f"{target.name}: accept loan of {principal:.1f} {sym} "
                f"at {rate_pct:.1f}% for {term_years} year(s) "
                f"(repay {repay:.1f} {sym})?"
            )
        else:
            accepted = rate <= 0.15
        if accepted:
            loan = self.loan_ledger.create_loan(
                borrower_id=target.player_id,
                lender_id=player.player_id,
                principal=principal,
                interest_rate=rate,
                issued_year=year,
                issued_season=season_index,
                term_years=term_years,
                own_committed=own_share,
                external_funded=external_share,
                posted_at_issue=funding_rate,
                reserve_ratio_at_issue=r,
            )
            self._fund_bank_external_portion(
                player, external_share, funding_rate, term_years, year, season_index
            )
            player.dollops -= principal
            target.dollops += principal
            self.io.print(
                f"  Loan #{loan.loan_id} issued. {target.name} received {principal:.1f} {sym}."
            )
            result.actions_taken.append(f"loan:offered:{principal:.1f}")
        else:
            self.io.print(f"  {target.name} declined the loan.")

    def _action_take_loan(self, player: Player, result: TurnResult,
                          year: int, season_index: int) -> None:
        sym = CURRENCY_SYMBOL
        banker = self._find_banker()
        if not banker:
            self.io.print("  No Banker island in the game.")
            return
        self_lending = banker.player_id == player.player_id
        principal = self.io.ask_dollop_amount(
            f"How much to borrow? (Bank cash {banker.dollops:.1f} {sym}; can fund externally)",
            1_000_000.0,
        )
        if principal <= 0:
            self.io.print("  Cancelled.")
            return
        term_years = self.io.choose_quantity("Loan term in years", 1, 3)
        funding_rate = posted_funding_rates(year, season_index)[term_years]
        rate = banker_quote_rate(
            player, self.loan_ledger, principal, term_years, year, season_index
        )
        rate_pct = rate * 100
        rate = rate_pct / 100.0
        # Phase D reserve check (skip when borrower IS the bank).
        if self_lending:
            r = 0.0
            own_share = 0.0
            external_share = 0.0
        else:
            r = self._banker_reserve_ratio(banker)
            can_issue, active, cap = self._banker_can_issue_loan(banker)
            if not can_issue:
                self._print_banker_cap_refusal(active, cap)
                return
            own_share = r * principal
            external_share = max(0.0, principal - own_share)
            if banker.dollops < own_share:
                mba = self._mba_banker_count(banker)
                self.io.print(
                    f"  Bank cannot back this loan at {r:.0%} reserve: needs "
                    f"{own_share:.1f} {sym} of own capital but has only "
                    f"{banker.dollops:.1f} {sym} (MBA-qualified Banker Managers: "
                    f"{mba}/{MBA_QUALIFIED_THRESHOLD}). Reduce principal or train MBAs."
                )
                return
        self.io.print(
            f"  Posted {term_years}-year funding rate: {funding_rate*100:.1f}%. "
            f"Banker quote: {rate_pct:.1f}% "
            f"(cost + minimum 2% spread plus borrower risk)."
        )
        if not self_lending:
            self.io.print(
                f"  Reserve {r:.0%}: bank locks {own_share:.1f} {sym} own capital "
                f"+ {external_share:.1f} {sym} sourced externally."
            )
        repay = round(principal * (1 + rate), 1)
        confirm = self.io.confirm(
            f"Borrow {principal:.1f} {sym} at {rate_pct:.1f}% for {term_years} year(s)? "
            f"(repay {repay:.1f} {sym})"
        )
        if not confirm:
            self.io.print("  Cancelled.")
            return
        loan = self.loan_ledger.create_loan(
            borrower_id=player.player_id,
            lender_id=banker.player_id,
            principal=principal,
            interest_rate=rate,
            issued_year=year,
            issued_season=season_index,
            term_years=term_years,
            own_committed=own_share,
            external_funded=external_share,
            posted_at_issue=funding_rate,
            reserve_ratio_at_issue=r,
        )
        if not self_lending:
            self._fund_bank_external_portion(
                banker, external_share, funding_rate, term_years, year, season_index
            )
            banker.dollops -= principal
        player.dollops += principal
        self.io.print(
            f"  Loan #{loan.loan_id}: borrowed {principal:.1f} {sym} from {banker.name} "
            f"at {rate_pct:.1f}% for {term_years} year(s) (repay {repay:.1f} {sym} by "
            f"Y{loan.maturity_year+1} S{loan.maturity_season+1})."
        )
        result.actions_taken.append(f"loan:taken:{principal:.1f}")

    def _action_rollover_loan(self, player: Player, result: TurnResult,
                              year: int, season_index: int) -> None:
        """Refinance an active loan where this player is the borrower (Issue #6).

        Refinancing: the old loan's repayment becomes the new loan's principal,
        rolled at a fresh banker_quote_rate for a new 1-3 year term.  No net
        cash changes hands at rollover — the new advance exactly covers the
        old repayment.
        """
        sym = CURRENCY_SYMBOL
        my_loans = [
            l for l in self.loan_ledger.active_loans_for(player.player_id)
            if l.borrower_id == player.player_id and l.lender_id >= 0
        ]
        if not my_loans:
            self.io.print("  No active loans to roll over.")
            return

        # Build a picker — let the player choose which loan to refinance.
        # We use ResourceType-style choose_resource via a labelled list, but
        # the simplest portable form is choose_quantity over the list index.
        self.io.print("\n  Your active loans:")
        for idx, loan in enumerate(my_loans, start=1):
            seasons_to_maturity = (
                (loan.maturity_year - year) * 4 + (loan.maturity_season - season_index)
            )
            self.io.print(
                f"    {idx}. Loan #{loan.loan_id}: {loan.principal:.1f} {sym} @ "
                f"{loan.interest_rate*100:.1f}% — repay {loan.repayment_amount:.1f} {sym} "
                f"in {seasons_to_maturity} season(s) "
                f"(matures Y{loan.maturity_year+1} S{loan.maturity_season+1})"
            )
        choice = self.io.choose_quantity(
            "Roll over which loan? (number above)", 1, len(my_loans)
        )
        old = my_loans[choice - 1]

        new_term_years = self.io.choose_quantity(
            "New term in years (1-3)", 1, 3
        )

        new_rate = banker_quote_rate(
            player, self.loan_ledger,
            old.repayment_amount, new_term_years, year, season_index,
        )
        rate_pct = new_rate * 100
        new_principal = old.repayment_amount
        new_repay = round(new_principal * (1 + new_rate), 1)

        funding_rate = posted_funding_rates(year, season_index)[new_term_years]
        self.io.print(
            f"\n  Banker quote for rollover of Loan #{old.loan_id}: "
            f"new principal {new_principal:.1f} {sym} (= old repayment), "
            f"rate {rate_pct:.1f}% (cost {funding_rate*100:.1f}%), "
            f"term {new_term_years} year(s), repay {new_repay:.1f} {sym}."
        )
        if not self.io.confirm(
            f"Confirm rollover: close Loan #{old.loan_id}, open new loan "
            f"{new_principal:.1f} {sym} at {rate_pct:.1f}% for "
            f"{new_term_years} year(s)?"
        ):
            self.io.print("  Rollover cancelled.")
            return

        try:
            new_loan = self.loan_ledger.rollover_loan(
                loan_id=old.loan_id,
                new_rate=new_rate,
                new_term_years=new_term_years,
                year=year,
                season=season_index,
            )
        except ValueError as exc:
            self.io.print(f"  Rollover failed: {exc}")
            return

        self.io.print(
            f"  Loan #{old.loan_id} rolled over → new Loan #{new_loan.loan_id} "
            f"({new_principal:.1f} {sym} @ {rate_pct:.1f}%, "
            f"matures Y{new_loan.maturity_year+1} S{new_loan.maturity_season+1})."
        )
        result.actions_taken.append(
            f"loan:rollover:{old.loan_id}->#{new_loan.loan_id}"
        )

    def _action_manage_insurance(self, player: Player, result: TurnResult,
                                 year: int, season_index: int) -> None:
        """Review active insurance policies and cancel for a pro-rata refund (Issue #5).

        The Banker pays the refund out of bank cash.  If no Banker player is
        available (auctioned away or AI-only), the refund is treated as
        external (cash is simply credited to the holder).
        """
        sym = CURRENCY_SYMBOL
        actives = player.active_policies(year, season_index)
        if not actives:
            self.io.print("  No active insurance policies to manage.")
            return

        self.io.print("\n  Your active insurance policies:")
        for idx, pol in enumerate(actives, start=1):
            refund = pol.cancel_refund(year, season_index)
            remaining = pol.seasons_remaining(year, season_index)
            self.io.print(
                f"    {idx}. {pol.describe()}  "
                f"— {remaining} season(s) left, cancel refund {refund:.1f} {sym}"
            )
        choice = self.io.choose_quantity(
            "Manage which policy? (number above)", 1, len(actives)
        )
        target = actives[choice - 1]

        if not self.io.confirm(
            f"Cancel {target.policy_type} insurance for a refund of "
            f"{target.cancel_refund(year, season_index):.1f} {sym}?"
        ):
            self.io.print("  Cancellation aborted.")
            return

        refund = player.cancel_insurance_policy(target.policy_id, year, season_index)
        # Debit the Banker (refund flows out of the Bank).  If no Banker, the
        # refund is credited to the holder anyway (external bank).
        banker = next(
            (p for p in self.players if p.player_id == target.banker_player_id),
            None,
        )
        if banker:
            banker.dollops -= refund
        player.receive_dollops(refund)
        self.io.print(
            f"  Cancelled {target.policy_type} policy. {player.name} received "
            f"{refund:.1f} {sym} refund."
        )
        result.actions_taken.append(
            f"insurance:cancelled:{target.policy_type}:{refund:.1f}"
        )

    def _action_apply_patent(self, player: Player, result: TurnResult) -> None:
        """Activate a Patent on one of the player's outputs.

        Each Patent reduces input cost by 20% on the chosen output. Cap of 3
        active patents per output.
        """
        if player.inventory.get(ResourceType.PATENTS) <= 0:
            self.io.print("  No Patents in inventory — buy one from the Educator.")
            return
        produced = player.all_produced_resources()
        produced = [r for r in produced if r != ResourceType.PATENTS]
        if not produced:
            self.io.print("  Your roles don't produce anything that benefits from a Patent.")
            return
        target = self.io.choose_resource(
            "Apply Patent to which output?", produced
        )
        if target is None:
            return
        already = player.active_patent_count(target.value)
        if already >= player.PATENT_MAX_PER_OUTPUT:
            self.io.print(
                f"  Cap reached: {target.value} already has {already}/"
                f"{player.PATENT_MAX_PER_OUTPUT} active patents."
            )
            return
        ok = player.apply_patent(target.value)
        if ok:
            mult = player.patent_input_multiplier(target.value)
            reduction = round((1 - mult) * 100)
            self.io.print(
                f"  Patent activated on {target.value} — input cost now "
                f"{round(mult * 100)}% (–{reduction}%)."
            )
            result.actions_taken.append(f"apply_patent:{target.value}")
        else:
            self.io.print("  Could not activate patent.")

    def _action_view_loans(self, player: Player) -> None:
        sym = CURRENCY_SYMBOL
        player_map = {p.player_id: p for p in self.players}
        loans = self.loan_ledger.active_loans_for(player.player_id)
        if not loans:
            self.io.print("  No outstanding loans.")
            return
        self.io.print("\n  Outstanding Loans:")
        for loan in loans:
            borrower = player_map.get(loan.borrower_id)
            lender = player_map.get(loan.lender_id)
            b_name = borrower.name if borrower else "?"
            l_name = lender.name if lender else "External Bank"
            role = "Borrower" if loan.borrower_id == player.player_id else "Lender"
            self.io.print(
                f"    #{loan.loan_id} [{role}] "
                f"{b_name} ← {loan.principal:.1f} {sym} from {l_name} "
                f"at {loan.interest_rate*100:.1f}% for {loan.term_years} year(s) "
                f"(repay {loan.repayment_amount:.1f} {sym} "
                f"Y{loan.maturity_year+1} S{loan.maturity_season+1})"
            )
