from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from ..models.player import Player
from ..models.market import Market
from ..models.resource import ResourceType
from ..models.training import TrainingRegistry, TrainingStatus, TrainingCapacityError
from ..engine.events import EventResult
from ..engine.production import ProductionEngine
from ..engine.trading import TradingEngine
from ..engine.ai import AIStrategy
from ..models.insurance import InsurancePolicy
from ..models.loan import LoanLedger, LoanStatus, banker_quote_rate, posted_funding_rates
from ..models.profession import Profession, PROFESSION_LABEL
from ..engine.workforce_events import apply_workplace_risks
from ..constants import (
    SEASONS, CURRENCY_SYMBOL, UNIVERSITY_CAPACITY,
    MANUFACTURER_PRODUCT_LINES, MAX_CLASS_SIZE_PER_COURSE,
    INSURANCE_BASE_PREMIUM, INSURANCE_DURATION_SEASONS, LIFE_INSURANCE_DEATH_BENEFIT,
    MEDICAL_INSURANCE_INJURY_REDUCTION, WORKPLACE_RISK,
)
from ..constants_capacity import CAPITAL_CATALOGUE
from ..models.capacity import items_for_role
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
    OFFER_LOAN         = "offer_loan"          # Banker: offer a loan to another player
    TAKE_LOAN          = "take_loan"           # any player: borrow from the Banker
    ROLLOVER_LOAN      = "rollover_loan"       # borrower: refinance an active loan (#6)
    VIEW_LOANS         = "view_loans"          # view outstanding loans
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
        self._post_population_food_demand()

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
            actions = self._ai.take_turn(
                player, self.market, self.players, self.production, self.trading,
                event_result, season_name, year, season_index,
            )
            result.actions_taken = actions
            for a in actions:
                self.io.print(a)
        else:
            self._human_turn(player, event_result, result, season_name, year, season_index)

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
        self.io.print(f"\n--- {player.name}'s turn ({player.role_names()}) ---")
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
                elif action == TurnAction.OFFER_LOAN:
                    self._action_offer_loan(player, result, year, season_index)
                elif action == TurnAction.TAKE_LOAN:
                    self._action_take_loan(player, result, year, season_index)
                elif action == TurnAction.ROLLOVER_LOAN:
                    self._action_rollover_loan(player, result, year, season_index)
                elif action == TurnAction.VIEW_LOANS:
                    self._action_view_loans(player)
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

    def _post_population_food_demand(self) -> None:
        """Post seasonal market demand from island populations without consuming stock yet."""
        for player in self.players:
            for resource, qty in player.population_food_fish_needs().items():
                if qty > 0:
                    self.market.post_demand(resource, qty)

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

        manufacturers = [
            p for p in self.players
            if any(r.name == "Manufacturer" for r in p.roles)
        ]
        if not manufacturers:
            self.io.print("  No Manufacturing island is available to build capital equipment.")
            return

        sym = CURRENCY_SYMBOL
        self.io.print("\n  Capital equipment available from Manufacturing:")
        for idx, item in enumerate(available_items, 1):
            manufactured_resource = self._manufactured_resource_for_capital_item(item)
            arrival = (
                "arrives now"
                if item.delivery_seasons == 0
                else f"arrives in {item.delivery_seasons} season(s)"
            )
            self.io.print(
                f"    {idx}. {item.name} ({item.role}) — {item.cost:.0f} {sym}; "
                f"requires 1x {manufactured_resource.value}; {arrival}"
            )

        choice = self.io.choose_quantity("Choose capital item", 1, len(available_items))
        item = available_items[choice - 1]
        manufacturer = self.io.choose_player("Buy from which Manufacturer?", manufacturers)
        manufactured_resource = self._manufactured_resource_for_capital_item(item)
        if manufacturer.inventory.get(manufactured_resource) <= 0:
            self.io.print(
                f"  {manufacturer.name} has no {manufactured_resource.value} available "
                f"to build {item.name}."
            )
            return
        if manufacturer.player_id != player.player_id and player.dollops < item.cost:
            self.io.print(f"  You need {item.cost:.0f} {sym} to buy {item.name}.")
            return
        if not self.io.confirm(
            f"Buy {item.name} from {manufacturer.name} for {item.cost:.0f} {sym}?"
        ):
            return

        manufacturer.give_resources(manufactured_resource, 1)
        if manufacturer.player_id != player.player_id:
            player.spend_dollops(item.cost)
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
        self.io.print(
            f"  Purchased {item.name}; consumed 1x {manufactured_resource.value}; {arrival}."
        )
        result.actions_taken.append(f"purchase_capital:{item.item_id}:{manufacturer.name}")

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

        target_profession = self.io.choose_profession(
            "Train workers into which profession?", available_professions
        )

        # For the chosen profession, decide which workers are eligible
        # Unskilled workers → enter profession at Basic; professionals → advance level
        unskilled_ids = player.workforce.get_unskilled_ids(player.workforce.active_count)
        other_trainable = [
            wid for wid in player.workforce.get_trainable_ids(player.workforce.active_count)
            if wid not in unskilled_ids
        ]
        # Prefer unskilled (entering profession) for new professions, or existing workers to advance
        trainable_ids = unskilled_ids + other_trainable
        if not trainable_ids:
            self.io.print("  No eligible workers to send (all expert or already at college).")
            return

        remaining_capacity = capacity_map[target_profession]["remaining"]
        max_send = min(len(trainable_ids), remaining_capacity)
        count = self.io.choose_quantity(
            f"How many workers to train as {target_profession}? (max {max_send})", 1, max_send
        )
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
            ticket_price = self.market.current_price(ResourceType.PASSENGER_SEATS)
            suggested_total = (20.0 * count) + (ticket_price * count)
            dollops_educator = self.io.ask_dollop_amount(
                f"Offer total training fee to Educator ({educator.name}) in {sym}? "
                f"(suggested includes tickets: {suggested_total:.0f} {sym})",
                player.dollops,
            )
            transport_mode = "air_ticket"
        dollops_transport = 0.0

        try:
            req = self.training.propose(
                requester_id=player.player_id,
                worker_ids=worker_ids,
                educator_id=educator.player_id,
                dollops_to_educator=dollops_educator,
                dollops_to_transporter=dollops_transport,
                target_profession=target_profession,
                year=year,
                season=season_index,
                transport_mode=transport_mode,
            )
        except TrainingCapacityError as e:
            self.io.print(f"  {e}")
            return

        player_names = {p.player_id: p.name for p in self.players}
        self.io.print(f"  Training request #{req.batch_id} submitted:")
        self.io.print(f"    {req.describe(player_names)}")
        result.actions_taken.append(f"request_training:batch#{req.batch_id}")

        if is_self_training:
            # Self-training still consumes Course slots (1 per class of
            # MAX_CLASS_SIZE_PER_COURSE).  No Courses → request stays
            # pending until next season's Course production refills.
            need_courses = self.courses_needed(count)
            if not self._ensure_training_courses(player, req):
                have = player.inventory.get(ResourceType.COURSES)
                self.io.print(
                    f"  Self-training request #{req.batch_id} submitted but on hold: "
                    f"needs {need_courses} Course(s), Education Island has {have}. "
                    f"It will start once Courses are produced."
                )
                return
            # Auto-approve and dispatch immediately — there's no other party
            # in the loop.  Workers head off to the on-island programme this
            # season; return next season.
            self.training.educator_approve(req.batch_id)
            self.training.dispatch(req.batch_id, year, season_index)
            self.io.print(
                f"  {count} worker(s) entered on-island training as {target_profession} "
                f"({need_courses} Course slot(s) used); "
                f"return in {SEASONS[(season_index + 1) % len(SEASONS)]}."
            )
            return

        self.io.print(
            f"  Awaiting {educator.name}'s approval. "
            f"{educator.name} must supply {count} PassengerSeats air ticket(s)."
        )

        # AI Educator auto-responds immediately
        if not educator.is_human:
            self._ai_educator_respond(educator, player, req, season_name, year)

    def _ai_educator_respond(
        self, educator, requester, req, season_name: str, year: int
    ) -> None:
        """Educator AI: accept if the Dollops offered cover a fair rate per worker."""
        fair_rate = 20.0 * len(req.worker_ids)
        ticket_cost = self.market.current_price(ResourceType.PASSENGER_SEATS) * len(req.worker_ids)
        if req.dollops_to_educator >= fair_rate + ticket_cost:
            # Peek Courses before burning air tickets.
            need_c = self.courses_needed(len(req.worker_ids))
            if educator.inventory.get(ResourceType.COURSES) < need_c:
                self.io.print(
                    f"  [AI] {educator.name} cannot approve training request #{req.batch_id} yet: "
                    f"needs {need_c} Course(s) "
                    f"(has {educator.inventory.get(ResourceType.COURSES)}). Pending."
                )
                return
            if not self._ensure_training_air_tickets(educator, req):
                self.io.print(
                    f"  [AI] {educator.name} cannot approve training request #{req.batch_id}: "
                    f"needs {len(req.worker_ids)} PassengerSeats air ticket(s)."
                )
                return
            self._ensure_training_courses(educator, req)
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
                f"Offer at least {fair_rate + ticket_cost:.0f} Dp to cover training and tickets."
            )

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

    def _dispatch_training(self, requester, req, season_name: str, year: int) -> None:
        """Workers physically depart; mark them absent for the season."""
        season_index = SEASONS.index(season_name)
        self.training.dispatch(req.batch_id, year=year, season=season_index, num_seasons=len(SEASONS))
        departed = requester.workforce.dispatch_for_training(req.worker_ids)
        self.io.print(
            f"  {len(departed)} worker(s) from {requester.name}'s island departed for "
            f"Education Island. They will return next season with upgraded training."
        )

    def _ensure_training_air_tickets(self, educator: Player, req) -> bool:
        """Consume 1 PassengerSeats ticket per trainee from the Educator."""
        needed = len(req.worker_ids)
        if educator.inventory.get(ResourceType.PASSENGER_SEATS) < needed:
            return False
        educator.give_resources(ResourceType.PASSENGER_SEATS, needed)
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

    def _ensure_training_courses(self, educator: Player, req) -> bool:
        """Consume ceil(trainees / class size) Courses from the Educator.

        Returns False (without consuming) if the Education Island doesn't
        have enough Courses in inventory yet — the request stays pending
        until next season's Course production refills the stock.
        """
        needed = self.courses_needed(len(req.worker_ids))
        if needed <= 0:
            return True
        if educator.inventory.get(ResourceType.COURSES) < needed:
            return False
        educator.give_resources(ResourceType.COURSES, needed)
        return True

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
        ticket_need = len(req.worker_ids) if req.transport_mode == "air_ticket" else 0
        funds = f" | requester cash: {requester.dollops:.1f} {sym}" if requester else ""
        msg = f" | message: {req.counter_message}" if req.counter_message else ""
        return (
            f"{req.describe(player_names)}\n"
            f"    Workers: {len(req.worker_ids)}  | Profession: {self._profession_label(req.target_profession)}\n"
            f"    Offered educator fee: {req.dollops_to_educator:.1f} {sym}{funds}\n"
            f"    Travel: {ticket_need} PassengerSeats supplied by Education Island{msg}"
        )

    def _approve_training_request(
        self,
        educator: Player,
        requester: Player,
        req,
        result: TurnResult,
        season_name: str,
        year: int,
    ) -> bool:
        # Peek Course sufficiency BEFORE consuming any air tickets so a
        # Course shortfall doesn't burn the Educator's PassengerSeats.
        need_courses = self.courses_needed(len(req.worker_ids))
        have_courses = educator.inventory.get(ResourceType.COURSES)
        if need_courses > have_courses:
            self.io.print(
                f"  Cannot approve yet — Education Island needs {need_courses} Course slot(s) "
                f"for this batch but only has {have_courses}. Produce more Courses first; "
                f"the request stays pending."
            )
            return False
        if req.transport_mode == "air_ticket" and not self._ensure_training_air_tickets(educator, req):
            short = len(req.worker_ids) - educator.inventory.get(ResourceType.PASSENGER_SEATS)
            self.io.print(
                f"  Cannot approve yet — Education Island needs {short} more "
                f"PassengerSeats air ticket(s). Buy tickets from the market first."
            )
            return False
        # Tickets secured; now consume the Course slots.
        self._ensure_training_courses(educator, req)
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
                f"  Used {len(req.worker_ids)} PassengerSeats air ticket(s) for trainee travel."
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
            if self.io.confirm("Accept this training counter-offer?"):
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
        pending = self.training.pending_for_educator(player.player_id)
        if not pending:
            self.io.print("  No training requests awaiting your approval.")
            return
        player_names = {p.player_id: p.name for p in self.players}
        player_map = {p.player_id: p for p in self.players}
        for req in pending:
            requester = player_map[req.requester_id]
            self.io.print(f"\n  Request: {self._training_request_details(req, player_names, requester)}")
            if self.io.confirm("Approve this training request?"):
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
                requester.spend_dollops(dollops_offered)
                player.receive_dollops(dollops_offered)
                self.training.arrange_transport(req.batch_id, player.player_id, dollops_offered)
                self._dispatch_training(requester, req, season_name, year)
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
            if borrower.dollops >= amount:
                borrower.dollops -= amount
                if lender.player_id != borrower.player_id:
                    lender.dollops += amount
                loan.status = LoanStatus.REPAID
                self.io.print(
                    f"\n[LOAN] {borrower.name} repaid {amount:.1f} {sym} to {lender.name} "
                    f"(principal {loan.principal:.1f} + interest {loan.interest_amount:.1f})"
                )
            else:
                paid = borrower.dollops
                borrower.dollops = 0
                if lender.player_id != borrower.player_id:
                    lender.dollops += paid
                loan.status = LoanStatus.DEFAULTED
                shortfall = amount - paid
                self.io.print(
                    f"\n[LOAN DEFAULT] {borrower.name} could not repay {amount:.1f} {sym} "
                    f"to {lender.name}. Paid {paid:.1f} {sym}, shortfall {shortfall:.1f} {sym}."
                )

    def _find_banker(self) -> Player | None:
        for p in self.players:
            if any(r.name == "Banker" for r in p.roles):
                return p
        return None

    def _fund_bank_shortfall(
        self,
        banker: Player,
        principal: float,
        cost_rate: float,
        term_years: int,
        year: int,
        season_index: int,
    ) -> float:
        """Borrow externally at the posted funding rate if the bank is short."""
        shortfall = max(0.0, principal - banker.dollops)
        if shortfall <= 0:
            return 0.0
        funding = self.loan_ledger.create_loan(
            borrower_id=banker.player_id,
            lender_id=-1,
            principal=shortfall,
            interest_rate=cost_rate,
            issued_year=year,
            issued_season=season_index,
            term_years=term_years,
        )
        banker.receive_dollops(shortfall)
        self.io.print(
            f"  Bank borrowed {shortfall:.1f} {CURRENCY_SYMBOL} externally "
            f"at {cost_rate*100:.1f}% (funding loan #{funding.loan_id})."
        )
        return shortfall

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
        self.io.print(
            f"  Offering {principal:.1f} {sym} to {target.name} "
            f"at {rate_pct:.1f}% — bank cost {funding_rate*100:.1f}%, "
            f"repayment {repay:.1f} {sym} after {term_years} year(s)."
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
            )
            self._fund_bank_shortfall(
                player, principal, funding_rate, term_years, year, season_index
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
        self.io.print(
            f"  Posted {term_years}-year funding rate: {funding_rate*100:.1f}%. "
            f"Banker quote: {rate_pct:.1f}% "
            f"(cost + minimum 2% spread plus borrower risk)."
        )
        rate = rate_pct / 100.0
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
        )
        if not self_lending:
            self._fund_bank_shortfall(
                banker, principal, funding_rate, term_years, year, season_index
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
