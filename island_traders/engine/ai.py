from __future__ import annotations
from ..models.player import Player
from ..models.market import Market
from ..models.resource import ResourceType
from ..engine.events import EventResult
from ..engine.production import ProductionEngine
from ..engine.trading import TradingEngine
from ..models.insurance import InsurancePolicy
from ..constants import (
    BASE_PRICES, MANUFACTURER_PRODUCT_LINES,
    WORKPLACE_RISK, INSURANCE_BASE_PREMIUM, INSURANCE_DURATION_SEASONS,
)

AI_TARGET_PRODUCTION_RUNS = 2


class AIStrategy:
    """
    Deterministic greedy rule-based bot for fast local play and simulations.

    This is intentionally a heuristic player, not an LLM-backed human-like
    player. Keep this path cheap, reproducible, and engine-local; see
    requirements/llm-player-adapter.md for the proposed LLM player adapter.

    Priority each turn:
    1. Buy missing production inputs from market if affordable.
    2. Produce if inputs satisfied.
    3. Sell produced resources if market price >= 80% of base price.
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
        """Pick the Manufacturer product line with the best expected profit margin.

        Score = (market price of output * qty) - cost of inputs.
        Prefer lines whose inputs the player already holds; fall back to best margin.
        """
        best_line = next(iter(MANUFACTURER_PRODUCT_LINES))
        best_score = float("-inf")
        for line_key, line in MANUFACTURER_PRODUCT_LINES.items():
            output_rt = ResourceType(line["output"])
            revenue = market.current_price(output_rt) * line["qty"]
            input_cost = sum(
                market.current_price(ResourceType(r)) * qty
                for r, qty in line["inputs"].items()
            )
            # Bonus for inputs already in inventory (avoid needing to buy)
            already_have = sum(
                min(player.inventory.get(ResourceType(r)), qty)
                for r, qty in line["inputs"].items()
            )
            score = revenue - input_cost + already_have * 2
            if score > best_score:
                best_score = score
                best_line = line_key
        return best_line

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

        # Manufacturer: pick the best product line the AI can afford / produce
        is_manufacturer = any(r.name == "Manufacturer" for r in player.roles)
        chosen_line: str | None = None
        if is_manufacturer:
            chosen_line = self._choose_product_line(player, market)

        # 1. Buy missing production inputs from market offers. AI players are
        # supply scaffolding for unclaimed islands, so they try to provision
        # multiple runs when the market can support it.
        inputs_needed = player.all_required_inputs(season_name, chosen_line)
        for rtype, qty_needed in inputs_needed.items():
            target_qty = qty_needed * self.target_production_runs
            have = player.inventory.get(rtype)
            if have < target_qty:
                buy_qty = target_qty - have
                offers = market.available_offers(rtype)
                avail = sum(o.remaining for o in offers)
                if avail > 0 and offers:
                    buy_qty = min(buy_qty, avail)
                    est_cost = sum(
                        offer.price_per_unit * take
                        for offer, take in self._planned_offer_fills(offers, buy_qty)
                    )
                    if player.dollops >= est_cost:
                        try:
                            cost, bought = market.buy_from_offers(player, rtype, buy_qty)
                            actions.append(
                                f"[AI] {player.name} bought {bought}x {rtype.value} "
                                f"for {cost:.1f} Dp"
                            )
                        except Exception:
                            pass

        # 3. Produce as many runs as inputs allow, up to the AI run target.
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

        # 4. Banker AI: offer insurance to high-risk players who don't already have it
        if any(r.name == "Banker" for r in player.roles):
            actions.extend(
                self._ai_offer_insurance(player, other_players, season_name, year, season_index)
            )

        # 5. Post sell offers at market price, but keep enough inventory to
        # run the chosen production plan again. Without this reserve the AI
        # sells its own critical inputs, then gets stuck in an input drought.
        reserve_inputs = player.all_required_inputs(season_name, chosen_line)
        for rtype in player.all_produced_resources():
            qty = max(0, player.inventory.get(rtype) - reserve_inputs.get(rtype, 0))
            if qty > 0:
                price = market.current_price(rtype)
                base = BASE_PRICES.get(rtype.value, price)
                if price >= base * 0.8:
                    try:
                        offer = market.post_offer(player, rtype, price, qty)
                        actions.append(
                            f"[AI] {player.name} listed {qty}x {rtype.value} "
                            f"at {price:.1f} Dp/unit"
                        )
                    except Exception:
                        pass

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
