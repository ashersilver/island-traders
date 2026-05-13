"""
Generates printable reference materials for physical board game play.

Outputs plain-text files suitable for printing on paper or card stock.

Usage:
    python -m island_traders.export.printables --output ./printables/
"""
from __future__ import annotations
import argparse
from pathlib import Path

from ..models.role import ROLES, Role
from ..models.resource import ResourceType
from ..engine.events import EventChart, EventChartLoader
from ..constants import BASE_PRICES, BASE_PRODUCTION, PRODUCTION_INPUTS


def _box(title: str, lines: list[str], width: int = 52) -> str:
    border = "+" + "-" * (width - 2) + "+"
    def pad(s: str) -> str:
        return "| " + s.ljust(width - 4) + " |"
    result = [border, pad(f"  {title}"), border]
    for line in lines:
        result.append(pad(line))
    result.append(border)
    return "\n".join(result)


def role_card(role: Role) -> str:
    produces = ", ".join(r.value for r in role.produces)
    inputs_raw = PRODUCTION_INPUTS.get(role.name, {})
    needs = ", ".join(f"{qty}x {r}" for r, qty in inputs_raw.items()) or "None"
    base_out = BASE_PRODUCTION.get(role.name, {})
    output_str = ", ".join(f"{qty}x {r}" for r, qty in base_out.items())

    lines = [
        f"Island : {role.island}",
        "",
        f"Produces (base) : {output_str}",
        f"Inputs needed   : {needs}",
        "",
        role.description,
        "",
        "-- Physical play notes --",
        "Roll 1d10 on your island's Event Chart each season.",
        "Apply the result before producing.",
        "Trades: negotiate freely with other players.",
        "Market board: update prices after each season.",
    ]
    return _box(f"ROLE: {role.name.upper()}", lines)


def event_chart_table(chart: EventChart, role_name: str) -> str:
    lines: list[str] = []
    lines.append(f"ISLAND EVENT CHART — {role_name.upper()}")
    lines.append("=" * 64)
    lines.append(f"{'Event':<28} {'Weight%':>8}  {'Yield%':>6}  {'Outage':>6}  Notes")
    lines.append("-" * 64)
    prev = 0.0
    for threshold, ev in chart._buckets:
        w = (threshold - prev) * 100
        prev = threshold
        yield_pct = int(ev.yield_modifier * 100)
        outage_str = "YES" if ev.outage else "-"
        notes = []
        if ev.damage_seasons:
            notes.append(f"dmg:{ev.damage_seasons}s")
        if ev.natural_disaster:
            notes.append("DISASTER")
        if ev.price_shock_resource and ev.price_shock_multiplier != 1.0:
            notes.append(f"price {ev.price_shock_resource.value}×{ev.price_shock_multiplier}")
        note_str = "  ".join(notes)
        lines.append(f"{ev.event_name:<28} {w:>7.1f}%  {yield_pct:>5}%  {outage_str:>6}  {note_str}")
    lines.append("-" * 64)
    lines.append("")
    lines.append("HOW TO USE (physical play):")
    lines.append("  Roll 2d6 or draw from shuffled event cards.")
    lines.append("  Convert weight% to a card count out of 20 cards")
    lines.append("  (e.g. 50% = 10 cards, 15% = 3 cards).")
    lines.append("  Reshuffle deck at the start of each year.")
    return "\n".join(lines)


def market_price_board(base_prices: dict[str, float] | None = None) -> str:
    prices = base_prices or BASE_PRICES
    lines: list[str] = []
    lines.append("ISLAND TRADERS — MARKET PRICE BOARD")
    lines.append("=" * 44)
    lines.append("Use tokens or a whiteboard to track current prices.")
    lines.append("Adjust up/down after each season based on events.")
    lines.append("")
    lines.append(f"{'Resource':<20} {'Base Price':>12}  {'Current':<10}")
    lines.append("-" * 44)
    for name, price in prices.items():
        lines.append(f"{name:<20} {price:>10.1f}g  ______")
    lines.append("-" * 44)
    lines.append("")
    lines.append("PRICE ADJUSTMENT GUIDE (rough guide for physical play):")
    lines.append("  Scarcity (few units on market): price × 1.3–2.0")
    lines.append("  Glut (many units on market):    price × 0.5–0.8")
    lines.append("  Disaster event:                 price × 1.5–2.5")
    lines.append("  Bumper/Bull event:              price × 0.8–0.9")
    return "\n".join(lines)


def season_scorecard() -> str:
    lines = [
        "SEASON SCORECARD",
        "=" * 52,
        "Player name: ___________________________",
        "Role(s):     ___________________________",
        "",
        f"{'Season':<10} {'Event':<22} {'Produced':<12} {'Gold'}",
        "-" * 52,
    ]
    from ..constants import SEASONS
    for s in SEASONS:
        lines.append(f"{s:<10} {'':22} {'':12} ____")
    lines += [
        "-" * 52,
        "Year-end net wealth (Dollops + resources + receivables - loans): ___________",
        "",
        "Side deals made this year:",
        "  1. ____________________________________________",
        "  2. ____________________________________________",
        "  3. ____________________________________________",
    ]
    return "\n".join(lines)


def export_all(output_dir: str, event_charts_path: str | None = None) -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    charts = (
        EventChartLoader.from_yaml(event_charts_path)
        if event_charts_path
        else EventChartLoader.default_charts()
    )

    # Role cards
    for role in ROLES.values():
        text = role_card(role)
        path = out / f"role_card_{role.name.lower()}.txt"
        path.write_text(text)
        print(f"  Written: {path}")

    # Event chart tables
    for role_name, chart in charts.items():
        text = event_chart_table(chart, role_name)
        path = out / f"event_chart_{role_name.lower()}.txt"
        path.write_text(text)
        print(f"  Written: {path}")

    # Market price board
    path = out / "market_price_board.txt"
    path.write_text(market_price_board())
    print(f"  Written: {path}")

    # Scorecard template
    path = out / "season_scorecard.txt"
    path.write_text(season_scorecard())
    print(f"  Written: {path}")

    print(f"\nAll printables saved to: {out.resolve()}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Island Traders printable assets")
    parser.add_argument("--output", type=str, default="./printables", help="Output directory")
    parser.add_argument("--charts", type=str, default=None, help="Path to event_charts.yaml")
    args = parser.parse_args()
    print(f"Generating printables in {args.output} ...")
    export_all(args.output, args.charts)


if __name__ == "__main__":
    main()
