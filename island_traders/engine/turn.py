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
from ..constants import (
    SEASONS, CURRENCY_SYMBOL, UNIVERSITY_CAPACITY,
    FLIGHT_COST_FRACTION, CARGO_FREE_PASSENGERS, MANUFACTURER_PRODUCT_LINES,
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
    ):
        self.players = players
        self.production = production_engine
        self.trading = trading_engine
        self.market = market
        self.io = io_adapter
        self.training = training or TrainingRegistry()
        self._ai = AIStrategy()
        self._damage_counters: dict[int, int] = {}

    def run_season(
        self,
        year: int,
        season_index: int,
        event_results: dict[int, EventResult],
    ) -> list[TurnResult]:
        season_name = SEASONS[season_index]
        sym = CURRENCY_SYMBOL
        self.io.print(f"\n{'='*50}")
        self.io.print(f"  Year {year + 1}  —  {season_name}")
        self.io.print(f"{'='*50}")

        results = []
        for player in self.players:
            event = event_results.get(player.player_id, EventResult("Normal Operations"))
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
            result = self.execute_turn(player, event, year, season_index)
            results.append(result)

        self.market.snapshot_prices(year, season_index)
        self.market.reset_period_signals()
        self.market.tick_shocks()
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
                event_result, season_name,
            )
            result.actions_taken = actions
            for a in actions:
                self.io.print(a)
        else:
            self._human_turn(player, event_result, result, season_name, year)

        result.dollops_delta = player.dollops - dollops_before
        return result

    def _human_turn(
        self,
        player: Player,
        event_result: EventResult,
        result: TurnResult,
        season_name: str,
        year: int,
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

    def _action_market_buy(self, player: Player, result: TurnResult) -> None:
        sym = CURRENCY_SYMBOL
        available = [r for r in ResourceType if self.market.supply.get(r, 0) > 0]
        if not available:
            self.io.print("  Market has no supply available.")
            return
        rtype = self.io.choose_resource("Buy which resource?", available)
        max_qty = self.market.supply.get(rtype, 0)
        qty = self.io.choose_quantity(f"How many {rtype.value}?", 1, max_qty)
        quote = self.trading.get_quote(rtype, qty)
        self.io.print(f"  Cost: {quote:.2f} {sym}")
        if self.io.confirm("Confirm buy?"):
            try:
                paid = self.trading.market_buy(player, rtype, qty)
                self.io.print(f"  Bought {qty}x {rtype.value} for {paid:.2f} {sym}")
                result.actions_taken.append(f"buy:{qty}x{rtype.value}")
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
        quote = self.trading.get_quote(rtype, qty)
        self.io.print(f"  You'll receive: {quote:.2f} {sym}")
        if self.io.confirm("Confirm sell?"):
            try:
                earned = self.trading.market_sell(player, rtype, qty)
                self.io.print(f"  Sold {qty}x {rtype.value} for {earned:.2f} {sym}")
                result.actions_taken.append(f"sell:{qty}x{rtype.value}")
            except Exception as e:
                self.io.print(f"  Failed: {e}")

    def _action_propose_deal(self, player: Player, result: TurnResult) -> None:
        sym = CURRENCY_SYMBOL
        others = [p for p in self.players if p.player_id != player.player_id]
        if not others:
            self.io.print("  No other players to deal with.")
            return
        target = self.io.choose_player("Deal with which player?", others)
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
