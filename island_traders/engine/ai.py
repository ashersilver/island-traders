from __future__ import annotations
from ..models.player import Player
from ..models.market import Market
from ..models.resource import ResourceType
from ..engine.events import EventResult
from ..engine.production import ProductionEngine
from ..engine.trading import TradingEngine
from ..constants import BASE_PRICES


class AIStrategy:
    """
    Greedy rule-based bot. Priority each turn:
    1. Buy missing production inputs from market if affordable.
    2. Produce if inputs satisfied.
    3. Sell produced resources if market price >= 80% of base price.
    Training is handled by TurnManager via _ai_educator_respond / _auto_arrange_transport.
    """

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

        # 1. Buy missing production inputs from market
        inputs_needed = player.all_required_inputs()
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
        can, missing = production_engine.can_produce(player, event_result)
        if can:
            produced = production_engine.produce(player, event_result, season_name)
            if produced:
                summary = ", ".join(f"{qty}x {r.value}" for r, qty in produced.items())
                actions.append(f"[AI] {player.name} produced: {summary}")
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
