from __future__ import annotations
from ..models.player import Player
from ..models.market import Market
from ..models.resource import ResourceType
from ..engine.events import EventResult
from ..engine.production import ProductionEngine
from ..engine.trading import TradingEngine
from ..constants import BASE_PRICES, MANUFACTURER_PRODUCT_LINES


class AIStrategy:
    """
    Greedy rule-based bot. Priority each turn:
    1. Buy missing production inputs from market if affordable.
    2. Produce if inputs satisfied.
    3. Sell produced resources if market price >= 80% of base price.
    Training is handled by TurnManager via _ai_educator_respond / _auto_arrange_transport.
    """

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

        # 1. Buy missing production inputs from market
        inputs_needed = player.all_required_inputs(season_name, chosen_line)
        for rtype, qty_needed in inputs_needed.items():
            have = player.inventory.get(rtype)
            if have < qty_needed:
                buy_qty = qty_needed - have
                supply = market.supply.get(rtype, 0)
                if supply >= buy_qty:
                    cost = trading_engine.get_quote(rtype, buy_qty)
                    if player.dollops >= cost:
                        try:
                            trading_engine.market_buy(player, rtype, buy_qty)
                            actions.append(
                                f"[AI] {player.name} bought {buy_qty}x {rtype.value} "
                                f"for {cost:.1f} Dp"
                            )
                        except Exception:
                            pass

        # 3. Produce if possible
        can, missing = production_engine.can_produce(player, event_result, season_name, chosen_line)
        if can:
            produced = production_engine.produce(player, event_result, season_name, chosen_line)
            if produced:
                line_tag = f" [{MANUFACTURER_PRODUCT_LINES[chosen_line]['desc']}]" if chosen_line else ""
                summary = ", ".join(f"{qty}x {r.value}" for r, qty in produced.items())
                actions.append(f"[AI] {player.name} produced{line_tag}: {summary}")
        elif missing:
            missing_str = ", ".join(f"{qty}x {r.value}" for r, qty in missing.items())
            actions.append(f"[AI] {player.name} cannot produce — missing: {missing_str}")

        # 4. Sell produced resources if market price >= 80% of base price
        for rtype in player.all_produced_resources():
            qty = player.inventory.get(rtype)
            if qty > 0:
                current = market.current_price(rtype)
                base = BASE_PRICES.get(rtype.value, current)
                if current >= base * 0.8:
                    try:
                        gold = trading_engine.market_sell(player, rtype, qty)
                        actions.append(
                            f"[AI] {player.name} sold {qty}x {rtype.value} for {gold:.1f} Dp"
                        )
                    except Exception:
                        pass

        return actions
