from __future__ import annotations
from ..models.player import Player
from ..models.market import Market
from ..models.deal import DealProposal
from ..models.resource import ResourceType
from ..engine.game import GameSummary
from ..constants import BASE_PRICES, SEASONS, CURRENCY_SYMBOL


class Display:
    """Pure formatters — all methods return strings, never print directly."""

    @staticmethod
    def market_table(market: Market) -> str:
        sym = CURRENCY_SYMBOL
        lines = ["\n  ┌── MARKET PRICES ──────────────────────────────┐"]
        lines.append(f"  │  {'Resource':<18} {'Price':>8}  {'Supply':>7}  │")
        lines.append("  ├───────────────────────────────────────────────┤")
        for r in ResourceType:
            price = market.current_price(r)
            supply = market.supply.get(r, 0)
            base = BASE_PRICES.get(r.value, price)
            trend = "↑" if price > base else ("↓" if price < base else "=")
            lines.append(
                f"  │  {r.value:<18} {price:>6.2f}{sym} {trend}  {supply:>6}  │"
            )
        lines.append("  └───────────────────────────────────────────────┘")
        return "\n".join(lines)

    @staticmethod
    def player_summary(player: Player, market: Market) -> str:
        sym = CURRENCY_SYMBOL
        prices = market.current_prices()
        inv_lines = []
        for r in ResourceType:
            qty = player.inventory.get(r)
            if qty > 0:
                val = qty * prices.get(r, 0)
                inv_lines.append(f"    {r.value:<18} {qty:>4}  ({val:.1f} {sym})")
        inv_str = "\n".join(inv_lines) if inv_lines else "    (empty)"

        role_lines = []
        for role in player.roles:
            produces_str = ", ".join(r.value for r in role.produces) or "—"
            needs_str    = ", ".join(r.value for r in role.needs)    or "—"
            role_lines.append(
                f"    {role.name} [{role.island}]\n"
                f"      Produces: {produces_str}   Needs: {needs_str}"
            )

        ws = player.workforce.summary()
        return (
            f"\n  Player       : {player.name}\n"
            f"  Role(s)      :\n" + "\n".join(role_lines) + "\n"
            f"  Dollops      : {player.dollops:.2f} {sym}\n"
            f"  Wealth       : {player.total_wealth(prices):.2f} {sym}\n"
            f"  Capacity     : {player.production_capacity*100:.0f}%\n"
            f"  Workforce    : {ws['active']}/{ws['total']} workers  "
            f"(eff {ws['avg_efficiency_pct']}%)\n"
            f"  Inventory:\n{inv_str}"
        )

    @staticmethod
    def leaderboard(players: list[Player], market: Market) -> str:
        sym = CURRENCY_SYMBOL
        prices = market.current_prices()
        ranked = sorted(players, key=lambda p: p.total_wealth(prices), reverse=True)
        lines = ["\n  ┌── LEADERBOARD ────────────────────────────────┐"]
        for i, p in enumerate(ranked, 1):
            wealth = p.total_wealth(prices)
            lines.append(
                f"  │  {i}. {p.name:<14} {p.role_names():<18} {wealth:>7.1f}{sym}  │"
            )
        lines.append("  └───────────────────────────────────────────────┘")
        return "\n".join(lines)

    @staticmethod
    def season_header(year: int, season: str) -> str:
        return f"\n{'='*50}\n  YEAR {year + 1}  —  {season}\n{'='*50}"

    @staticmethod
    def turn_menu(player: Player, available_actions) -> str:
        lines = [f"\n  {player.name}'s turn — choose an action:"]
        for i, action in enumerate(available_actions, 1):
            lines.append(f"    {i}. {action.value.replace('_', ' ').title()}")
        return "\n".join(lines)

    @staticmethod
    def deal_proposal_summary(
        deal: DealProposal, proposer_name: str, target_name: str
    ) -> str:
        return deal.summary(proposer_name, target_name)

    @staticmethod
    def production_preview(preview: dict) -> str:
        if preview.get("outage"):
            return f"  [OUTAGE] {preview.get('reason')} — no production this season."
        if not preview.get("can_produce"):
            missing = ", ".join(
                f"{qty}x {r.value}" for r, qty in preview.get("missing_inputs", {}).items()
            )
            return f"  Cannot produce — missing inputs: {missing}"
        out = ", ".join(f"{qty}x {r.value}" for r, qty in preview.get("outputs", {}).items())
        yld = int(preview.get("yield_modifier", 1.0) * 100)
        eff = preview.get("effective_factor", preview.get("workforce_factor", 1.0))
        return (
            f"  Event: {preview.get('event')} (yield {yld}%)  "
            f"effective factor: {eff:.2f}  →  Will produce: {out}"
        )

    @staticmethod
    def game_summary(summary: GameSummary) -> str:
        sym = CURRENCY_SYMBOL
        lines = [
            "",
            "=" * 50,
            "  GAME OVER — FINAL RESULTS",
            "=" * 50,
            f"  Winner: {summary.winner.name} ({summary.winner.role_names()})",
            "",
            "  Final Rankings:",
        ]
        for i, (player, wealth) in enumerate(summary.final_rankings, 1):
            lines.append(
                f"    {i}. {player.name:<16} {player.role_names():<20} {wealth:>8.1f} {sym}"
            )
        lines.append(f"\n  Total deals made: {summary.deal_count}")
        lines.append("=" * 50)
        return "\n".join(lines)
