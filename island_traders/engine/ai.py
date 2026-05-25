from __future__ import annotations
from ..models.player import Player
from ..models.market import Market
from ..models.resource import ResourceType
from ..models.deal import DealProposal, DealStatus
from ..engine.events import EventResult
from ..engine.production import ProductionEngine
from ..engine.trading import TradingEngine
from ..models.insurance import InsurancePolicy
from ..models.loan import LoanLedger, banker_quote_rate, posted_funding_rates
from ..models.profession import Profession
from ..constants import (
    BASE_PRICES, MANUFACTURER_PRODUCT_LINES, PRODUCER_PRODUCTIVITY_MULTIPLIER,
    WORKPLACE_RISK, INSURANCE_BASE_PREMIUM, INSURANCE_DURATION_SEASONS,
    MBA_RESERVE_RATIO_BASE, MBA_RESERVE_RATIO_QUALIFIED,
    MBA_QUALIFIED_THRESHOLD,
)
from ..constants_capacity import CAPITAL_CATALOGUE
from ..models.capacity import items_for_role

AI_TARGET_PRODUCTION_RUNS = 2
AI_OFFER_MARKUP = 1.0
AI_ARBITRAGE_MIN_MARGIN = 0.05
AI_MIN_LOAN_PRINCIPAL = 50.0
AI_DEBT_CEILING_MULTIPLIER = 2.0
AI_EQUIPMENT_INPUT_RUNS = 5
AI_EQUIPMENT_INPUTS = {
    ResourceType.FARM_MACHINERY,
    ResourceType.MINING_EQUIPMENT,
    ResourceType.LABORATORY_EQUIPMENT,
    ResourceType.MEDICAL_DEVICES,
    ResourceType.TRANSPORT_EQUIPMENT,
}
AI_LIST_ONLY_WITH_BID = {
    ResourceType.HEALTH_SERVICES,
    ResourceType.VACCINE,
    ResourceType.PATENTS,
    ResourceType.PASSENGER_SEATS,
}


class AIStrategy:
    """
    Deterministic greedy rule-based bot for fast local play and simulations.

    This is intentionally a heuristic player, not an LLM-backed human-like
    player. Keep this path cheap, reproducible, and engine-local; see
    requirements/llm-player-adapter.md for the proposed LLM player adapter.

    Priority each turn:
    1. Review peer deals using observable market value.
    2. Buy or bid for missing production inputs.
    3. Produce if inputs are satisfied.
    4. Sell surplus production and opportunistically capture visible arbitrage.
    Training is handled by TurnManager via _ai_educator_respond / _auto_arrange_transport.
    """

    def __init__(self, target_production_runs: int = AI_TARGET_PRODUCTION_RUNS):
        self.target_production_runs = max(1, target_production_runs)

    def _mba_banker_count(self, banker: Player) -> int:
        return sum(
            1 for worker in banker.workforce.active_workers
            if worker.profession == Profession.BANKER.value
            and getattr(worker, "has_mba", False)
        )

    def _banker_reserve_ratio(self, banker: Player) -> float:
        if self._mba_banker_count(banker) >= MBA_QUALIFIED_THRESHOLD:
            return MBA_RESERVE_RATIO_QUALIFIED
        return MBA_RESERVE_RATIO_BASE

    def _one_season_input_cost(
        self,
        player: Player,
        market: Market,
        season_name: str,
        product_line: str | None = None,
    ) -> float:
        inputs = player.all_required_inputs(season_name, product_line)
        cost = sum(market.current_price(rtype) * qty for rtype, qty in inputs.items())
        return round(max(AI_MIN_LOAN_PRINCIPAL, cost), 1)

    def _capital_short_threshold(
        self,
        player: Player,
        market: Market,
        season_name: str,
        product_line: str | None = None,
    ) -> float:
        return self._one_season_input_cost(player, market, season_name, product_line)

    def _find_ai_banker(
        self,
        players: list[Player],
        exclude_player_id: int | None = None,
    ) -> Player | None:
        for candidate in players:
            if candidate.is_human or candidate.player_id == exclude_player_id:
                continue
            if any(role.name == "Banker" for role in candidate.roles):
                return candidate
        return None

    def _ai_issue_loan(
        self,
        banker: Player,
        borrower: Player,
        principal: float,
        loan_ledger: LoanLedger,
        year: int,
        season_index: int,
    ) -> str | None:
        if borrower.is_human or banker.player_id == borrower.player_id:
            return None
        if principal <= 0:
            return None
        term_years = 1
        funding_rate = posted_funding_rates(year, season_index)[term_years]
        rate = banker_quote_rate(
            borrower, loan_ledger, principal, term_years, year, season_index
        )
        reserve_ratio = self._banker_reserve_ratio(banker)
        own_share = round(reserve_ratio * principal, 2)
        if banker.dollops < own_share:
            return None
        external_share = max(0.0, round(principal - own_share, 2))

        loan = loan_ledger.create_loan(
            borrower_id=borrower.player_id,
            lender_id=banker.player_id,
            principal=principal,
            interest_rate=rate,
            issued_year=year,
            issued_season=season_index,
            term_years=term_years,
            own_committed=own_share,
            external_funded=external_share,
            posted_at_issue=funding_rate,
            reserve_ratio_at_issue=reserve_ratio,
        )
        if external_share > 0:
            loan_ledger.create_loan(
                borrower_id=banker.player_id,
                lender_id=-1,
                principal=external_share,
                interest_rate=funding_rate,
                issued_year=year,
                issued_season=season_index,
                term_years=term_years,
            )
            banker.receive_dollops(external_share)
        banker.dollops -= principal
        borrower.receive_dollops(principal)
        return (
            f"[AI] {banker.name} issued Loan #{loan.loan_id} to {borrower.name} "
            f"for {principal:.1f} Dp at {rate*100:.1f}%"
        )

    def _ai_offer_loans(
        self,
        banker: Player,
        other_players: list[Player],
        market: Market,
        loan_ledger: LoanLedger | None,
        season_name: str,
        year: int,
        season_index: int,
    ) -> list[str]:
        if loan_ledger is None:
            return []
        actions: list[str] = []
        for borrower in other_players:
            if borrower.player_id == banker.player_id or borrower.is_human:
                continue
            if any(
                loan.borrower_id == borrower.player_id
                for loan in loan_ledger.active_loans_for(borrower.player_id)
            ):
                continue
            threshold = self._capital_short_threshold(borrower, market, season_name)
            if borrower.dollops >= threshold:
                continue
            if loan_ledger.outstanding_debt(borrower.player_id) > (
                threshold * AI_DEBT_CEILING_MULTIPLIER
            ):
                continue
            principal = round(threshold - borrower.dollops, 1)
            action = self._ai_issue_loan(
                banker, borrower, principal, loan_ledger, year, season_index
            )
            if action:
                actions.append(action)
        return actions

    def _ai_take_loan_if_short(
        self,
        player: Player,
        market: Market,
        other_players: list[Player],
        loan_ledger: LoanLedger | None,
        season_name: str,
        year: int,
        season_index: int,
        product_line: str | None = None,
    ) -> list[str]:
        if loan_ledger is None:
            return []
        if any(role.name == "Banker" for role in player.roles):
            return []
        if any(
            loan.borrower_id == player.player_id
            for loan in loan_ledger.active_loans_for(player.player_id)
        ):
            return []
        threshold = self._capital_short_threshold(
            player, market, season_name, product_line
        )
        if player.dollops >= threshold:
            return []
        banker = self._find_ai_banker(other_players, exclude_player_id=player.player_id)
        if banker is None:
            return []
        principal = round(threshold - player.dollops, 1)
        action = self._ai_issue_loan(
            banker, player, principal, loan_ledger, year, season_index
        )
        return [action] if action else []

    def _ai_rollover_due_loans(
        self,
        player: Player,
        loan_ledger: LoanLedger | None,
        year: int,
        season_index: int,
    ) -> list[str]:
        if loan_ledger is None:
            return []
        actions: list[str] = []
        for loan in loan_ledger.active_loans_for(player.player_id):
            if loan.borrower_id != player.player_id or loan.lender_id < 0:
                continue
            seasons_to_maturity = (
                (loan.maturity_year - year) * 4
                + (loan.maturity_season - season_index)
            )
            if seasons_to_maturity > 1 or player.dollops >= loan.repayment_amount:
                continue
            new_rate = banker_quote_rate(
                player, loan_ledger, loan.repayment_amount, 1, year, season_index
            )
            try:
                new_loan = loan_ledger.rollover_loan(
                    loan.loan_id, new_rate, 1, year, season_index
                )
            except ValueError:
                continue
            actions.append(
                f"[AI] {player.name} rolled over Loan #{loan.loan_id} "
                f"into Loan #{new_loan.loan_id}"
            )
            break
        return actions

    def _ai_invest_unclaimed_catalogue_item(
        self,
        player: Player,
        year: int,
        season_index: int,
    ) -> list[str]:
        seen: set[str] = set()
        unclaimed = []
        for role in player.roles:
            for item in items_for_role(CAPITAL_CATALOGUE, role.name):
                if item.item_id in seen:
                    continue
                seen.add(item.item_id)
                if player.capital_inventory.get(item.item_id, 0) <= 0:
                    unclaimed.append(item)
        if not unclaimed:
            return []
        item = min(unclaimed, key=lambda catalogue_item: catalogue_item.cost)
        if player.dollops <= item.cost * 2:
            return []
        player.dollops -= item.cost
        current_tick = year * 4 + season_index
        player.add_capital(item.item_id, 1, acquired_tick=current_tick)
        return [
            f"[AI] {player.name} invested {item.cost:.0f} Dp in {item.name}"
        ]

    def _ai_offer_insurance(
        self,
        banker: Player,
        other_players: list[Player],
        season_name: str,
        year: int,
        season_index: int,
    ) -> list[str]:
        """Banker AI proactively sells base-premium policies to uninsured AI players."""
        actions: list[str] = []
        purchased_tick = year * 4 + season_index
        expires_at = purchased_tick + INSURANCE_DURATION_SEASONS
        for target in other_players:
            if target.player_id == banker.player_id or target.is_human:
                continue
            for role in target.roles:
                risk = WORKPLACE_RISK.get(role.name, {})
                if not risk.get("injury_rate") and not risk.get("fatality_rate"):
                    continue
                for policy_type in ("life", "medical"):
                    if target.has_active_insurance(policy_type, year, season_index):
                        continue
                    premium = INSURANCE_BASE_PREMIUM[policy_type]
                    if target.dollops < premium or banker.dollops < 0:
                        continue
                    target.spend_dollops(premium)
                    banker.receive_dollops(premium)
                    policy = InsurancePolicy(
                        policy_id=len(target.insurance_policies) + 1,
                        policy_type=policy_type,
                        holder_player_id=target.player_id,
                        banker_player_id=banker.player_id,
                        premium_paid=premium,
                        purchased_tick=purchased_tick,
                        expires_at_tick=expires_at,
                    )
                    target.add_insurance_policy(policy)
                    actions.append(
                        f"[AI] {banker.name} issued {policy_type} insurance to "
                        f"{target.name} for {premium:.0f} Dp"
                    )
        return actions

    def _choose_product_line(self, player: Player, market: Market) -> str:
        """Pick the Manufacturer product line with the best expected profit margin."""
        best_line = next(iter(MANUFACTURER_PRODUCT_LINES))
        best_score = float("-inf")
        bid_lines = [
            line_key for line_key, line in MANUFACTURER_PRODUCT_LINES.items()
            if market.best_bid(ResourceType(line["output"])) is not None
        ]
        candidates = bid_lines or list(MANUFACTURER_PRODUCT_LINES)
        for line_key, line in MANUFACTURER_PRODUCT_LINES.items():
            if line_key not in candidates:
                continue
            output_rt = ResourceType(line["output"])
            bid = market.best_bid(output_rt)
            unit_price = bid.price_per_unit if bid is not None else market.current_price(output_rt)
            bid_pull = min(bid.remaining, line["qty"]) if bid is not None else 0
            revenue = unit_price * line["qty"]
            input_cost = sum(
                market.current_price(ResourceType(r)) * qty
                for r, qty in line["inputs"].items()
            )
            freight = self._manufacturer_freight_surcharge(line_key, line["qty"])
            input_cost += market.current_price(ResourceType.FREIGHT) * freight
            already_have = sum(
                min(player.inventory.get(ResourceType(r)), qty)
                for r, qty in line["inputs"].items()
            )
            score = revenue - input_cost + already_have * 2 + bid_pull * unit_price
            if score > best_score:
                best_score = score
                best_line = line_key
        return best_line

    def _manufacturer_freight_surcharge(self, product_line: str | None, qty: int) -> int:
        if not product_line or product_line not in MANUFACTURER_PRODUCT_LINES:
            return 0
        freight_per_unit = MANUFACTURER_PRODUCT_LINES[product_line]["freight_per_unit"]
        if freight_per_unit <= 0 or qty <= 0:
            return 0
        board_scale_qty = max(1, round(qty / PRODUCER_PRODUCTIVITY_MULTIPLIER))
        return freight_per_unit * board_scale_qty

    def _inputs_for_ai_purchase(
        self,
        player: Player,
        season_name: str,
        product_line: str | None,
    ) -> dict[ResourceType, int]:
        inputs = dict(player.all_required_inputs(season_name, product_line))
        if any(role.name == "Manufacturer" for role in player.roles):
            line = MANUFACTURER_PRODUCT_LINES.get(
                product_line or next(iter(MANUFACTURER_PRODUCT_LINES))
            )
            if line:
                freight = self._manufacturer_freight_surcharge(product_line, line["qty"])
                if freight:
                    inputs[ResourceType.FREIGHT] = inputs.get(ResourceType.FREIGHT, 0) + freight
        return inputs

    def _last_deal_price(self, trading_engine: TradingEngine, rtype: ResourceType) -> float | None:
        """Infer the latest cash/unit price from accepted one-resource deals."""
        for deal in reversed(trading_engine.ledger.deals):
            if deal.status != DealStatus.ACCEPTED:
                continue
            if deal.offer_resource == rtype and deal.offer_qty > 0 and deal.gold_sweetener < 0:
                return round(abs(deal.gold_sweetener) / deal.offer_qty, 2)
            if deal.request_resource == rtype and deal.request_qty > 0 and deal.gold_sweetener > 0:
                return round(deal.gold_sweetener / deal.request_qty, 2)
        return None

    def _valuation_price(
        self, market: Market, trading_engine: TradingEngine, rtype: ResourceType
    ) -> float:
        """Value goods from recent deals, then live asks, then formula price."""
        last_deal = self._last_deal_price(trading_engine, rtype)
        if last_deal is not None:
            return last_deal
        best_offer = market.best_offer(rtype)
        if best_offer is not None:
            return best_offer.price_per_unit
        return market.current_price(rtype)

    def _deal_value_for_acceptor(
        self, deal: DealProposal, market: Market, trading_engine: TradingEngine
    ) -> tuple[float, float]:
        received = max(deal.gold_sweetener, 0)
        given = max(-deal.gold_sweetener, 0)
        if deal.offer_resource and deal.offer_qty > 0:
            received += deal.offer_qty * self._valuation_price(
                market, trading_engine, deal.offer_resource
            )
        if deal.request_resource and deal.request_qty > 0:
            given += deal.request_qty * self._valuation_price(
                market, trading_engine, deal.request_resource
            )
        return received, given

    def _review_pending_deals(
        self,
        player: Player,
        market: Market,
        other_players: list[Player],
        trading_engine: TradingEngine,
    ) -> list[str]:
        """Accept profitable AI-targeted deals; reject deals that destroy value."""
        actions: list[str] = []
        players = {p.player_id: p for p in other_players}
        for deal in trading_engine.ledger.pending_for_player(player.player_id):
            proposer = players.get(deal.proposer_id)
            if proposer is None:
                trading_engine.ledger.expire(deal.deal_id)
                actions.append(f"[AI] {player.name} let stale deal #{deal.deal_id} expire")
                continue
            received, given = self._deal_value_for_acceptor(deal, market, trading_engine)
            profitable = received >= given * (1 + AI_ARBITRAGE_MIN_MARGIN) or (
                given == 0 and received > 0
            )
            if profitable:
                try:
                    trading_engine.accept_deal(deal, acceptor=player, proposer=proposer)
                    actions.append(f"[AI] {player.name} accepted profitable deal #{deal.deal_id}")
                except Exception:
                    trading_engine.ledger.expire(deal.deal_id)
                    actions.append(f"[AI] {player.name} let stale deal #{deal.deal_id} expire")
            else:
                trading_engine.reject_deal(deal)
                actions.append(f"[AI] {player.name} rejected deal #{deal.deal_id}")
        return actions

    def _capture_visible_arbitrage(
        self, player: Player, market: Market, other_players: list[Player]
    ) -> list[str]:
        """Buy the cheapest ask and immediately fill richer bids when the spread is visible."""
        actions: list[str] = []
        for rtype in ResourceType:
            if rtype == ResourceType.FINANCE:
                continue
            offer = market.best_offer(rtype)
            bid = market.best_bid(rtype)
            if offer is None or bid is None:
                continue
            if offer.seller_id == player.player_id or bid.buyer_id == player.player_id:
                continue
            if bid.price_per_unit < offer.price_per_unit * (1 + AI_ARBITRAGE_MIN_MARGIN):
                continue
            qty = min(offer.remaining, bid.remaining)
            if qty <= 0 or player.dollops < offer.price_per_unit * qty:
                continue
            try:
                cost, bought = market.buy_from_offers(player, rtype, qty)
                paid, sold = market.sell_to_bids(player, rtype, bought, other_players)
            except Exception:
                continue
            if sold:
                actions.append(
                    f"[AI] {player.name} arbitraged {sold}x {rtype.value} "
                    f"for {paid - cost:.1f} Dp profit"
                )
        return actions

    def take_turn(
        self,
        player: Player,
        market: Market,
        other_players: list[Player],
        production_engine: ProductionEngine,
        trading_engine: TradingEngine,
        event_result: EventResult,
        season_name: str = "Spring",
        year: int = 0,
        season_index: int = 0,
        loan_ledger: LoanLedger | None = None,
    ) -> list[str]:
        actions: list[str] = []

        if event_result.outage:
            actions.append(f"[AI] {player.name} — outage: {event_result.event_name}, skipping")
            return actions

        actions.extend(self._review_pending_deals(player, market, other_players, trading_engine))

        is_manufacturer = any(r.name == "Manufacturer" for r in player.roles)
        chosen_line: str | None = None
        if is_manufacturer:
            chosen_line = self._choose_product_line(player, market)

        actions.extend(
            self._ai_rollover_due_loans(player, loan_ledger, year, season_index)
        )
        actions.extend(
            self._ai_take_loan_if_short(
                player, market, other_players, loan_ledger, season_name,
                year, season_index, chosen_line,
            )
        )
        actions.extend(
            self._ai_invest_unclaimed_catalogue_item(player, year, season_index)
        )

        inputs_needed = self._inputs_for_ai_purchase(player, season_name, chosen_line)
        for rtype, qty_needed in inputs_needed.items():
            if rtype == ResourceType.FINANCE:
                continue
            target_runs = (
                AI_EQUIPMENT_INPUT_RUNS
                if rtype in AI_EQUIPMENT_INPUTS else self.target_production_runs
            )
            target_qty = qty_needed * target_runs
            have = player.inventory.get(rtype)
            if have >= target_qty:
                continue
            buy_qty = target_qty - have
            offers = market.available_offers(rtype)
            avail = sum(o.remaining for o in offers)
            if avail > 0 and offers:
                fill_qty = min(buy_qty, avail)
                est_cost = sum(
                    offer.price_per_unit * take
                    for offer, take in self._planned_offer_fills(offers, fill_qty)
                )
                if player.dollops >= est_cost:
                    try:
                        cost, bought = market.buy_from_offers(player, rtype, fill_qty)
                        actions.append(
                            f"[AI] {player.name} bought {bought}x {rtype.value} "
                            f"for {cost:.1f} Dp"
                        )
                        buy_qty -= bought
                    except Exception:
                        pass
            if buy_qty > 0:
                bid_price = self._valuation_price(market, trading_engine, rtype)
                affordable_qty = min(buy_qty, int(player.dollops // bid_price))
                if affordable_qty > 0:
                    try:
                        market.post_bid(player, rtype, bid_price, affordable_qty)
                        actions.append(
                            f"[AI] {player.name} bid for {affordable_qty}x {rtype.value} "
                            f"at {bid_price:.1f} Dp/unit"
                        )
                    except Exception:
                        pass

        produced_totals: dict[ResourceType, int] = {}
        missing: dict[ResourceType, int] = {}
        for _ in range(self.target_production_runs):
            can, missing = production_engine.can_produce(
                player, event_result, season_name, chosen_line
            )
            if not can:
                break
            produced = production_engine.produce(player, event_result, season_name, chosen_line)
            if produced:
                for rtype, qty in produced.items():
                    produced_totals[rtype] = produced_totals.get(rtype, 0) + qty
        if produced_totals:
            line_tag = f" [{MANUFACTURER_PRODUCT_LINES[chosen_line]['desc']}]" if chosen_line else ""
            summary = ", ".join(f"{qty}x {r.value}" for r, qty in produced_totals.items())
            actions.append(f"[AI] {player.name} produced{line_tag}: {summary}")
        elif missing:
            missing_str = ", ".join(f"{qty}x {r.value}" for r, qty in missing.items())
            actions.append(f"[AI] {player.name} cannot produce — missing: {missing_str}")

        if any(r.name == "Banker" for r in player.roles):
            actions.extend(
                self._ai_offer_insurance(player, other_players, season_name, year, season_index)
            )
            actions.extend(
                self._ai_offer_loans(
                    player, other_players, market, loan_ledger,
                    season_name, year, season_index,
                )
            )

        reserve_inputs = player.all_required_inputs(season_name, chosen_line)
        listable_resources = set(player.all_produced_resources()) | set(produced_totals)
        for rtype in listable_resources:
            if rtype == ResourceType.FINANCE:
                continue
            if rtype in AI_LIST_ONLY_WITH_BID and market.best_bid(rtype) is None:
                continue
            qty = max(0, player.inventory.get(rtype) - reserve_inputs.get(rtype, 0))
            if qty <= 0:
                continue
            price = round(market.current_price(rtype) * AI_OFFER_MARKUP, 2)
            base = BASE_PRICES.get(rtype.value, price)
            if price >= base * 0.8:
                try:
                    market.post_offer(player, rtype, price, qty)
                    actions.append(
                        f"[AI] {player.name} listed {qty}x {rtype.value} "
                        f"at {price:.1f} Dp/unit"
                    )
                except Exception:
                    pass

        actions.extend(self._capture_visible_arbitrage(player, market, other_players))
        return actions

    def _planned_offer_fills(self, offers, qty: int):
        remaining = qty
        for offer in offers:
            if remaining <= 0:
                break
            take = min(remaining, offer.remaining)
            if take > 0:
                yield offer, take
                remaining -= take
