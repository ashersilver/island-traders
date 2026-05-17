from __future__ import annotations
from ..models.player import Player
from ..models.market import Market
from ..models.resource import ResourceType
from ..models.deal import DealProposal, DealStatus
from ..engine.events import EventResult
from ..engine.production import ProductionEngine
from ..engine.trading import TradingEngine
from ..models.insurance import InsurancePolicy
from ..constants import (
    BASE_PRICES, MANUFACTURER_PRODUCT_LINES,
    WORKPLACE_RISK, INSURANCE_BASE_PREMIUM, INSURANCE_DURATION_SEASONS,
)

AI_TARGET_PRODUCTION_RUNS = 2
AI_OFFER_MARKUP = 1.0
AI_ARBITRAGE_MIN_MARGIN = 0.05


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
        for line_key, line in MANUFACTURER_PRODUCT_LINES.items():
            output_rt = ResourceType(line["output"])
            revenue = market.current_price(output_rt) * line["qty"]
            input_cost = sum(
                market.current_price(ResourceType(r)) * qty
                for r, qty in line["inputs"].items()
            )
            already_have = sum(
                min(player.inventory.get(ResourceType(r)), qty)
                for r, qty in line["inputs"].items()
            )
            score = revenue - input_cost + already_have * 2
            if score > best_score:
                best_score = score
                best_line = line_key
        return best_line

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

        inputs_needed = player.all_required_inputs(season_name, chosen_line)
        for rtype, qty_needed in inputs_needed.items():
            target_qty = qty_needed * self.target_production_runs
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

        reserve_inputs = player.all_required_inputs(season_name, chosen_line)
        listable_resources = set(player.all_produced_resources()) | set(produced_totals)
        for rtype in listable_resources:
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
