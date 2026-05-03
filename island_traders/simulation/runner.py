"""
Simulation runner for calibrating event chart weights.

Run N games with all-AI players, collect statistics, and export a CSV
so chart weights can be tuned until win rates and wealth are balanced
across all roles.

Usage:
    python -m island_traders.simulation.runner --games 200 --years 3 --seed 42
"""
from __future__ import annotations
import argparse
import csv
import random
from dataclasses import dataclass, field
from pathlib import Path

from ..engine.game import Game, GameConfig, PlayerSpec
from ..engine.events import EventChartLoader, SeasonEventResolver
from ..models.resource import ResourceType
from ..models.role import ROLES
from ..constants import SEASONS


class _SilentIO:
    """No-op IO adapter so simulations run without any terminal output."""
    def print(self, *_): pass
    def input(self, *_): return ""
    def choose_action(self, *_):
        from ..engine.turn import TurnAction
        return TurnAction.END_TURN
    def choose_resource(self, _, available):
        return available[0] if available else None
    def choose_quantity(self, _, min_qty, max_qty): return min_qty
    def choose_player(self, _, players): return players[0]
    def confirm(self, _): return True
    def ask_dollop_amount(self, _, max_dollops): return 0.0


@dataclass
class RoleStats:
    role_name: str
    wins: int = 0
    total_games: int = 0
    total_wealth: float = 0.0
    event_counts: dict[str, int] = field(default_factory=dict)

    @property
    def win_rate(self) -> float:
        return self.wins / self.total_games if self.total_games else 0.0

    @property
    def avg_wealth(self) -> float:
        return self.total_wealth / self.total_games if self.total_games else 0.0


@dataclass
class SimulationStats:
    num_games: int
    num_years: int
    role_stats: dict[str, RoleStats]
    price_history_mean: dict[str, list[float]] = field(default_factory=dict)


class SimulationRunner:
    def __init__(
        self,
        num_games: int = 100,
        num_years: int = 3,
        seed: int = 42,
        event_charts_path: str | None = None,
    ):
        self.num_games = num_games
        self.num_years = num_years
        self.seed = seed
        self.event_charts_path = event_charts_path
        self._rng = random.Random(seed)

    def run(self) -> SimulationStats:
        role_names = list(ROLES.keys())
        stats: dict[str, RoleStats] = {r: RoleStats(r) for r in role_names}
        # Accumulate per-season price sums for averaging
        num_seasons = self.num_years * len(SEASONS)
        price_sums: dict[str, list[float]] = {r.value: [0.0] * num_seasons for r in ResourceType}

        for game_idx in range(self.num_games):
            game_seed = self._rng.randint(0, 2**31)
            specs = [
                PlayerSpec(name=rname, role_names=[rname], is_human=False)
                for rname in role_names
            ]
            config = GameConfig(
                player_specs=specs,
                num_years=self.num_years,
                starting_dollops=100.0,
                event_charts_path=self.event_charts_path,
            )
            # Override event resolver RNG for reproducibility
            io = _SilentIO()
            game = Game(config, io)
            game.setup()
            game.event_resolver = SeasonEventResolver(
                game.event_resolver.charts, rng=random.Random(game_seed)
            )
            summary = game.run()

            # Record stats
            for player, wealth in summary.final_rankings:
                rname = player.roles[0].name
                stats[rname].total_games += 1
                stats[rname].total_wealth += wealth

            winner_role = summary.winner.roles[0].name
            stats[winner_role].wins += 1

            # Accumulate prices
            for snap in summary.price_history:
                season_idx = snap.year * len(SEASONS) + snap.season
                if season_idx < num_seasons:
                    for r, price in snap.prices.items():
                        price_sums[r.value][season_idx] += price

        # Compute means
        price_means: dict[str, list[float]] = {}
        for r_val, sums in price_sums.items():
            price_means[r_val] = [round(s / self.num_games, 2) for s in sums]

        return SimulationStats(
            num_games=self.num_games,
            num_years=self.num_years,
            role_stats=stats,
            price_history_mean=price_means,
        )

    def export_csv(self, stats: SimulationStats, path: str) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)

        # Role summary
        role_csv = p.parent / (p.stem + "_roles.csv")
        with open(role_csv, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["role", "games", "wins", "win_rate_%", "avg_wealth"])
            for rs in stats.role_stats.values():
                writer.writerow([
                    rs.role_name,
                    rs.total_games,
                    rs.wins,
                    f"{rs.win_rate * 100:.1f}",
                    f"{rs.avg_wealth:.1f}",
                ])

        # Price history
        price_csv = p.parent / (p.stem + "_prices.csv")
        resources = list(stats.price_history_mean.keys())
        with open(price_csv, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["season_index"] + resources)
            num_seasons = stats.num_years * len(SEASONS)
            for i in range(num_seasons):
                row = [i] + [stats.price_history_mean[r][i] for r in resources]
                writer.writerow(row)

        print(f"Role stats  → {role_csv}")
        print(f"Price history → {price_csv}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Island Traders simulation runner")
    parser.add_argument("--games", type=int, default=100, help="Number of games to simulate")
    parser.add_argument("--years", type=int, default=3, help="Years per game")
    parser.add_argument("--seed", type=int, default=42, help="RNG seed for reproducibility")
    parser.add_argument("--charts", type=str, default=None, help="Path to event_charts.yaml")
    parser.add_argument("--output", type=str, default="simulation_results/run", help="Output CSV prefix")
    args = parser.parse_args()

    print(f"Running {args.games} games × {args.years} years (seed={args.seed}) ...")
    runner = SimulationRunner(
        num_games=args.games,
        num_years=args.years,
        seed=args.seed,
        event_charts_path=args.charts,
    )
    stats = runner.run()

    print("\n--- Role Balance ---")
    print(f"{'Role':<16} {'Wins':>6} {'Win%':>7} {'AvgWealth':>12}")
    print("-" * 45)
    for rs in stats.role_stats.values():
        print(f"{rs.role_name:<16} {rs.wins:>6} {rs.win_rate*100:>6.1f}% {rs.avg_wealth:>12.1f} Dp")

    runner.export_csv(stats, args.output)


if __name__ == "__main__":
    main()
