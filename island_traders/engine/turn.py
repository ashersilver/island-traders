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
from ..models.loan import LoanLedger, LoanStatus
from ..engine.workforce_events import apply_workplace_risks
from ..constants import (
    SEASONS, CURRENCY_SYMBOL, UNIVERSITY_CAPACITY,
    FLIGHT_COST_FRACTION, CARGO_FREE_PASSENGERS, MANUFACTURER_PRODUCT_LINES,
    INSURANCE_BASE_PREMIUM, INSURANCE_DURATION_SEASONS, LIFE_INSURANCE_DEATH_BENEFIT,
    MEDICAL_INSURANCE_INJURY_REDUCTION, WORKPLACE_RISK,
)


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
    OFFER_LOAN         = "offer_loan"          # Banker: offer a loan to another player
    TAKE_LOAN          = "take_loan"           # any player: borrow from the Banker
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
        self.io.print(
            f"    Dollops: {player.dollops:.1f} {sym}  |  "
            f"Wealth: {player.total_wealth(prices):.1f} {sym}  |  "
            f"Workers: {player.workforce.count} "
            f"({player.workforce.average_efficiency*100:.0f}% eff  |  "
            f"capacity: {player.production_capacity*100:.0f}%)"
        )
        while True:
            action = self.io.choose_action(player, list(TurnAction))
            if action == TurnAction.END_TURN:
                break
            elif action == TurnAction.INVENTORY:
                self.io.print(player.inventory_report(self.market.current_prices()))
            elif action == TurnAction.VIEW_MARKET:
                self.io.print(self._format_market())
            elif action == TurnAction.VIEW_PLAYERS:
                self.io.print(self._format_players(player))
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
            elif action == TurnAction.OFFER_LOAN:
                self._action_offer_loan(player, result, year, season_index)
            elif action == TurnAction.TAKE_LOAN:
                self._action_take_loan(player, result, year, season_index)
            elif action == TurnAction.VIEW_LOANS:
                self._action_view_loans(player)
            elif action == TurnAction.APPLY_PATENT:
                self._action_apply_patent(player, result)

    def _choose_product_line_human(self) -> str:
        """Prompt the human Manufacturer player to choose a product line."""
        lines = list(MANUFACTURER_PRODUCT_LINES.items())
        self.io.print("\n  ForgeHaven Product Lines:")
        for i, (key, line) in enumerate(lines, 1):
            freight_note = (
                f"  (no freight surcharge)"
                if line["freight_per_unit"] == 0
                else f"  (+{line['freight_per_unit']} Freight/unit shipped)"
            )
            self.io.print(
                f"    {i}. {line['desc']:<30}"
                f"  Inputs: {line['inputs']}"
                f"  → {line['qty']}x {line['output']}"
                f"  | Skilled: {line['skilled']}  Unskilled: {line['unskilled']}"
                f"{freight_note}"
            )
        choice = self.io.choose_quantity("Choose product line [1–4]:", 1, len(lines))
        return lines[choice - 1][0]

    def _action_produce(
        self, player: Player, event_result: EventResult, result: TurnResult, season_name: str
    ) -> None:
        is_manufacturer = any(r.name == "Manufacturer" for r in player.roles)
        product_line: str | None = None

        if is_manufacturer:
            product_line = self._choose_product_line_human()

        preview = self.production.production_preview(player, event_result, season_name, product_line)
        self.io.print(f"  Event: {preview['event']}")
        if preview["outage"]:
            self.io.print("  Production halted this season.")
            return
        if not preview["can_produce"]:
            missing = ", ".join(
                f"{qty}x {r.value}" for r, qty in preview["missing_inputs"].items()
            )
            self.io.print(f"  Cannot produce — missing: {missing}")
            return
        self.io.print(
            f"  Workforce: {preview['workforce_count']} workers  "
            f"(need {preview['workforce_required']}, fill {preview['fill_rate_pct']}%, "
            f"eff {preview['avg_efficiency_pct']}%)  "
            f"capacity floor: {preview['base_capacity_pct']}%  →  "
            f"effective factor: {preview['effective_factor']:.2f}"
        )
        if product_line:
            line_info = MANUFACTURER_PRODUCT_LINES[product_line]
            freight_note = (
                "" if line_info["freight_per_unit"] == 0
                else f"  (freight surcharge: {preview.get('freight_surcharge', 0)} Freight)"
            )
            self.io.print(f"  Product line: {line_info['desc']}{freight_note}")
        self.io.print(f"  Will produce: {preview['outputs']}")
        if self.io.confirm("Produce?"):
            produced = self.production.produce(player, event_result, season_name, product_line)
            summary = ", ".join(f"{qty}x {r.value}" for r, qty in produced.items())
            self.io.print(f"  Produced: {summary}")
            result.actions_taken.append(f"produce:{summary}")

    def _action_request_training(
        self, player: Player, result: TurnResult, season_name: str, year: int
    ) -> None:
        """Player proposes to send workers to the Education Island for one season."""
        season_index = SEASONS.index(season_name)

        # Build list of professions with remaining capacity
        capacity_map = self.training.capacity_summary(year, season_index)
        available_professions = [
            prof for prof, info in capacity_map.items() if info["remaining"] > 0
        ]
        if not available_professions:
            self.io.print("  University is fully booked for this year across all professions.")
            return

        # Show capacity and let player choose target profession
        self.io.print("  University capacity remaining this year:")
        for prof in available_professions:
            info = capacity_map[prof]
            seasonal_note = (
                f"  (max {info['seasonal_cap']}/season)" if info["seasonal_cap"] else ""
            )
            self.io.print(
                f"    {prof:<24}  {info['remaining']:>2} slot(s) left "
                f"(of {info['annual_cap']} annual){seasonal_note}"
            )

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

        # Find Educator players
        educators = [
            p for p in self.players
            if p.player_id != player.player_id
            and any(r.name == "Educator" for r in p.roles)
        ]
        if not educators:
            self.io.print("  No Educator player in this game.")
            return

        educator = self.io.choose_player("Which Educator?", educators)
        sym = CURRENCY_SYMBOL
        dollops_educator = self.io.ask_dollop_amount(
            f"Offer to Educator ({educator.name}) in {sym}?", player.dollops
        )

        # Choose transport mode
        flight_cost = round(dollops_educator * FLIGHT_COST_FRACTION, 2)
        self.io.print(
            f"\n  Transport options for {count} worker(s):\n"
            f"    1. Charter flight  — {flight_cost:.0f} {sym} (20% of training fee), departs this season\n"
            f"    2. Cargo vessel    — free for up to {CARGO_FREE_PASSENGERS}, arrives next season (+1 turn)\n"
            f"    3. Hire Transporter — negotiate fee with Transporter player"
        )
        transport_choice = self.io.choose_quantity("Transport option [1/2/3]?", 1, 3)

        if transport_choice == 1:
            transport_mode = "flight"
            dollops_transport = flight_cost
            if player.dollops < dollops_educator + dollops_transport:
                self.io.print("  Insufficient Dollops to cover educator + flight.")
                return
        elif transport_choice == 2:
            transport_mode = "cargo"
            if count > CARGO_FREE_PASSENGERS:
                self.io.print(
                    f"  Cargo vessels carry only {CARGO_FREE_PASSENGERS} passengers free. "
                    f"You are sending {count} workers — consider a flight or Transporter instead."
                )
                return
            dollops_transport = 0.0
        else:
            transport_mode = "transporter"
            dollops_transport = self.io.ask_dollop_amount(
                "Offer to Transporter for moving workers? (0 to arrange later)",
                player.dollops - dollops_educator,
            )
            if player.dollops < dollops_educator + dollops_transport:
                self.io.print("  Insufficient Dollops to cover both payments.")
                return

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

        if transport_mode in ("flight", "cargo"):
            self.io.print(
                f"  Transport arranged ({transport_mode}). "
                f"Awaiting {educator.name}'s approval."
            )
        else:
            self.io.print(
                f"  Awaiting {educator.name}'s approval. "
                f"Workers depart once Educator and Transporter both agree."
            )
        result.actions_taken.append(f"request_training:batch#{req.batch_id}")

        # AI Educator auto-responds immediately
        if not educator.is_human:
            self._ai_educator_respond(educator, player, req, season_name, year)

    def _ai_educator_respond(
        self, educator, requester, req, season_name: str, year: int
    ) -> None:
        """Educator AI: accept if the Dollops offered cover a fair rate per worker."""
        fair_rate = 20.0 * len(req.worker_ids)
        if req.dollops_to_educator >= fair_rate:
            self.training.educator_approve(req.batch_id)
            requester.spend_dollops(req.dollops_to_educator)
            educator.receive_dollops(req.dollops_to_educator)
            self.io.print(
                f"  [AI] {educator.name} approved training request #{req.batch_id} "
                f"(received {req.dollops_to_educator:.0f} Dp)."
            )
            if req.transport_mode in ("flight", "cargo"):
                # Transport already arranged — deduct flight cost and dispatch
                if req.transport_mode == "flight" and req.dollops_to_transporter > 0:
                    requester.spend_dollops(req.dollops_to_transporter)
                self._dispatch_training(requester, req, season_name, year)
            else:
                self._auto_arrange_transport(requester, req, season_name, year)
        else:
            self.training.educator_reject(req.batch_id)
            self.io.print(
                f"  [AI] {educator.name} rejected training request #{req.batch_id}. "
                f"Offer at least {fair_rate:.0f} Dp to get approval."
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

    def _action_review_training(
        self, player: Player, result: TurnResult, season_name: str, year: int
    ) -> None:
        """Educator reviews pending training requests and approves or rejects them."""
        if not any(r.name == "Educator" for r in player.roles):
            self.io.print("  Only the Educator can review training requests.")
            return
        pending = self.training.pending_for_educator(player.player_id)
        if not pending:
            self.io.print("  No training requests awaiting your approval.")
            return
        player_names = {p.player_id: p.name for p in self.players}
        player_map = {p.player_id: p for p in self.players}
        for req in pending:
            self.io.print(f"\n  Request: {req.describe(player_names)}")
            if self.io.confirm("Approve this training request?"):
                requester = player_map[req.requester_id]
                requester.spend_dollops(req.dollops_to_educator)
                player.receive_dollops(req.dollops_to_educator)
                self.training.educator_approve(req.batch_id)
                self.io.print(
                    f"  Approved. Received {req.dollops_to_educator:.0f} Dp from {requester.name}."
                )
                if req.transport_mode in ("flight", "cargo"):
                    if req.transport_mode == "flight" and req.dollops_to_transporter > 0:
                        requester.spend_dollops(req.dollops_to_transporter)
                        self.io.print(
                            f"  Flight booked — {req.dollops_to_transporter:.0f} Dp deducted from {requester.name}."
                        )
                    self._dispatch_training(requester, req, season_name, year)
                else:
                    self._auto_arrange_transport(requester, req, season_name, year)
                result.actions_taken.append(f"approved_training:batch#{req.batch_id}")
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
        count = self.io.choose_quantity("How many workers to recruit?", 1, available)
        recruited = player.recruit_workers(count)
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
        self.io.print(f"  Reference price: {ref_price:.2f} {sym}/unit")
        price = self.io.ask_dollop_amount(
            f"Your asking price per unit (ref: {ref_price:.2f})?", ref_price * 5
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

    def _format_market(self) -> str:
        sym = CURRENCY_SYMBOL
        lines = ["\n  Market Prices:"]
        for r in ResourceType:
            price = self.market.current_price(r)
            supply = self.market.supply.get(r, 0)
            lines.append(f"    {r.value:<18} {price:>7.2f} {sym}  supply:{supply}")
        return "\n".join(lines)

    def _format_players(self, current: Player) -> str:
        """Show all players: roles, island, produces, capacity, Dollops, wealth, workers."""
        from ..models.role import ROLES
        sym = CURRENCY_SYMBOL
        prices = self.market.current_prices()
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
                f"Wealth: {p.total_wealth(prices):.1f} {sym}  |  "
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
            if not borrower or not lender:
                loan.status = LoanStatus.DEFAULTED
                continue
            amount = loan.repayment_amount
            if borrower.dollops >= amount:
                borrower.dollops -= amount
                lender.dollops += amount
                loan.status = LoanStatus.REPAID
                self.io.print(
                    f"\n[LOAN] {borrower.name} repaid {amount:.1f} {sym} to {lender.name} "
                    f"(principal {loan.principal:.1f} + interest {loan.interest_amount:.1f})"
                )
            else:
                paid = borrower.dollops
                borrower.dollops = 0
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
            f"Loan principal (max {player.dollops:.1f} {sym})?", player.dollops
        )
        if principal <= 0:
            self.io.print("  Cancelled — principal must be positive.")
            return
        if principal > player.dollops:
            self.io.print(f"  You only have {player.dollops:.1f} {sym} available.")
            return
        rate_pct = self.io.ask_dollop_amount("Interest rate %? (e.g. 10 for 10%)", 100)
        if rate_pct < 0:
            self.io.print("  Cancelled — rate must be non-negative.")
            return
        rate = rate_pct / 100.0
        repay = round(principal * (1 + rate), 1)
        self.io.print(
            f"  Offering {principal:.1f} {sym} to {target.name} "
            f"at {rate_pct:.0f}% — repayment {repay:.1f} {sym} after 1 year."
        )
        if target.is_human:
            accepted = self.io.confirm(
                f"{target.name}: accept loan of {principal:.1f} {sym} "
                f"at {rate_pct:.0f}% (repay {repay:.1f} {sym})?"
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
        if banker.player_id == player.player_id:
            self.io.print("  You are the Banker — use 'Offer Loan' instead.")
            return
        principal = self.io.ask_dollop_amount(
            f"How much to borrow (Banker has {banker.dollops:.1f} {sym})?",
            banker.dollops,
        )
        if principal <= 0:
            self.io.print("  Cancelled.")
            return
        if principal > banker.dollops:
            self.io.print(f"  Banker only has {banker.dollops:.1f} {sym} available.")
            return
        if banker.is_human:
            rate_pct = self.io.ask_dollop_amount(
                f"Banker: set interest rate % for {player.name}'s loan of {principal:.1f} {sym}?",
                100
            )
            if rate_pct < 0:
                self.io.print("  Banker declined.")
                return
            accepted = True
        else:
            rate_pct = 10.0
            accepted = True
            self.io.print(f"  Banker AI offers {rate_pct:.0f}% interest.")
        rate = rate_pct / 100.0
        repay = round(principal * (1 + rate), 1)
        confirm = self.io.confirm(
            f"Borrow {principal:.1f} {sym} at {rate_pct:.0f}%? "
            f"(repay {repay:.1f} {sym} in 1 year)"
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
        )
        banker.dollops -= principal
        player.dollops += principal
        self.io.print(
            f"  Loan #{loan.loan_id}: borrowed {principal:.1f} {sym} from {banker.name} "
            f"at {rate_pct:.0f}% (repay {repay:.1f} {sym} by "
            f"Y{loan.maturity_year+1} S{loan.maturity_season+1})."
        )
        result.actions_taken.append(f"loan:taken:{principal:.1f}")

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
            l_name = lender.name if lender else "?"
            role = "Borrower" if loan.borrower_id == player.player_id else "Lender"
            self.io.print(
                f"    #{loan.loan_id} [{role}] "
                f"{b_name} ← {loan.principal:.1f} {sym} from {l_name} "
                f"at {loan.interest_rate*100:.0f}% "
                f"(repay {loan.repayment_amount:.1f} {sym} "
                f"Y{loan.maturity_year+1} S{loan.maturity_season+1})"
            )
