"""
Simulation runner for calibrating event chart weights.

Run N games with all-AI players, collect statistics, and export a CSV
so chart weights can be tuned until win rates and wealth are balanced
across all roles.

Usage:
    python -m island_traders.simulation.runner --games 200 --years 3 --seed 42
    python -m island_traders.simulation.runner --games 200 --years 3 --seeds 42,1,7,99
"""
from __future__ import annotations
import argparse
import csv
import random
import statistics
from dataclasses import dataclass, field
from pathlib import Path

from ..engine.game import Game, GameConfig, PlayerSpec
from ..engine.events import EventChartLoader, SeasonEventResolver
from ..models.resource import ResourceType
from ..models.role import ROLES
from ..constants import SEASONS, STARTING_DOLLOPS


class _SilentIO:
    """No-op IO adapter so simulations run without any terminal output.

    R2 (simulation-baselining review, 2026-07-04): every *decision* method
    counts its invocations in ``fallback_counts``.  A nonzero count means the
    sim answered a real game decision with a degenerate default (minimum /
    first option / yes / zero) instead of a modelled policy — i.e. the sim is
    defaulting through a mechanic, not exercising it.  The runner aggregates
    and surfaces these so new prompt flows can't silently skew baselines.
    """
    def __init__(self):
        self.fallback_counts: dict[str, int] = {}

    def _count(self, method: str) -> None:
        self.fallback_counts[method] = self.fallback_counts.get(method, 0) + 1

    def print(self, *_): pass
    def input(self, *_): return ""
    def choose_action(self, *_):
        from ..engine.turn import TurnAction
        self._count("choose_action")
        return TurnAction.END_TURN
    def choose_resource(self, _, available):
        self._count("choose_resource")
        return available[0] if available else None
    def choose_quantity(self, _, min_qty, max_qty, default=None):
        self._count("choose_quantity")
        return min_qty
    def choose_player(self, _, players):
        self._count("choose_player")
        return players[0]
    def confirm(self, _):
        self._count("confirm")
        return True
    def ask_dollop_amount(self, _, max_dollops):
        self._count("ask_dollop_amount")
        return 0.0


def gini_coefficient(values: list[float]) -> float:
    """Gini coefficient of a wealth distribution (0 = equal, →1 = concentrated).

    Negative wealth is clamped to 0 — Gini is undefined for negatives and a
    bankrupt island counts as "has nothing" for concentration purposes.
    """
    vals = sorted(max(0.0, v) for v in values)
    n = len(vals)
    total = sum(vals)
    if n == 0 or total <= 0:
        return 0.0
    # Standard rank formula: G = (2·Σ i·x_i)/(n·Σ x) − (n+1)/n, i is 1-based.
    weighted = sum(i * v for i, v in enumerate(vals, start=1))
    return round((2.0 * weighted) / (n * total) - (n + 1.0) / n, 4)


def hhi(shares: list[float]) -> float:
    """Herfindahl–Hirschman index over wealth shares (1/n = balanced, 1 = monopoly).

    Shares are normalised over their (0-clamped) sum, so callers may pass raw
    wealth values.
    """
    clamped = [max(0.0, s) for s in shares]
    total = sum(clamped)
    if total <= 0:
        return 0.0
    return round(sum((s / total) ** 2 for s in clamped), 4)


@dataclass
class RoleStats:
    role_name: str
    wins: int = 0
    total_games: int = 0
    total_wealth: float = 0.0
    event_counts: dict[str, int] = field(default_factory=dict)
    # R1: this role's share of each game's total (0-clamped) wealth, one entry
    # per game — the balance metric, with enough data for a variance bar.
    wealth_shares: list[float] = field(default_factory=list)

    @property
    def win_rate(self) -> float:
        return self.wins / self.total_games if self.total_games else 0.0

    @property
    def avg_wealth(self) -> float:
        return self.total_wealth / self.total_games if self.total_games else 0.0

    @property
    def share_mean(self) -> float:
        return (sum(self.wealth_shares) / len(self.wealth_shares)
                if self.wealth_shares else 0.0)

    @property
    def share_stddev(self) -> float:
        if len(self.wealth_shares) < 2:
            return 0.0
        return statistics.stdev(self.wealth_shares)


@dataclass
class SimulationStats:
    num_games: int
    num_years: int
    role_stats: dict[str, RoleStats]
    price_history_mean: dict[str, list[float]] = field(default_factory=dict)
    # Mean total Dollops in circulation per snapshot, averaged across games.
    # Index 0 is the opening balance; indices 1..N are end-of-season N.
    money_supply_mean: list[float] = field(default_factory=list)
    # Dynamic supply-chain liveness (B1/B2, #73): total volumes summed across
    # all games, keyed by resource name.  `flow_starvation` counts production
    # attempts that stalled on a missing input.
    flow_produced: dict[str, float] = field(default_factory=dict)
    flow_consumed: dict[str, float] = field(default_factory=dict)
    flow_traded: dict[str, float] = field(default_factory=dict)
    flow_starvation: dict[str, int] = field(default_factory=dict)
    # R2: decision prompts answered by _SilentIO defaults, summed across games.
    fallback_counts: dict[str, int] = field(default_factory=dict)
    # R7: mean per-game concentration of final wealth.
    gini_mean: float = 0.0
    hhi_mean: float = 0.0


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
        # Money supply has one opening snapshot + one per season.
        money_sums: list[float] = [0.0] * (num_seasons + 1)
        money_counts: list[int] = [0] * (num_seasons + 1)
        # Supply-chain liveness, summed across all games.
        flow_produced: dict[str, float] = {}
        flow_consumed: dict[str, float] = {}
        flow_traded: dict[str, float] = {}
        flow_starvation: dict[str, int] = {}
        fallback_counts: dict[str, int] = {}
        gini_sum = 0.0
        hhi_sum = 0.0

        for game_idx in range(self.num_games):
            game_seed = self._rng.randint(0, 2**31)
            specs = [
                PlayerSpec(
                    name=rname,
                    role_names=[rname],
                    is_human=False,
                    starting_dollops=STARTING_DOLLOPS,
                )
                for rname in role_names
            ]
            config = GameConfig(
                player_specs=specs,
                num_years=self.num_years,
                starting_dollops=STARTING_DOLLOPS,
                event_charts_path=self.event_charts_path,
            )
            # Override event resolver and turn-manager RNGs for reproducibility
            io = _SilentIO()
            game = Game(config, io)
            game.setup()
            game_rng = random.Random(game_seed)
            game.event_resolver = SeasonEventResolver(
                game.event_resolver.charts, rng=random.Random(game_seed)
            )
            if game.turn_manager:
                game.turn_manager._rng = random.Random(game_seed)
            summary = game.run()

            # Record stats
            final_wealths = [wealth for _, wealth in summary.final_rankings]
            game_total = sum(max(0.0, w) for w in final_wealths)
            for player, wealth in summary.final_rankings:
                rname = player.roles[0].name
                stats[rname].total_games += 1
                stats[rname].total_wealth += wealth
                # R1: per-game wealth share (0-clamped, matches Gini/HHI basis).
                stats[rname].wealth_shares.append(
                    max(0.0, wealth) / game_total if game_total > 0 else 0.0
                )

            winner_role = summary.winner.roles[0].name
            stats[winner_role].wins += 1

            # R7: per-game concentration of final wealth.
            gini_sum += gini_coefficient(final_wealths)
            hhi_sum += hhi(final_wealths)

            # R2: decision prompts that fell through to _SilentIO defaults.
            for method, count in io.fallback_counts.items():
                fallback_counts[method] = fallback_counts.get(method, 0) + count

            # Accumulate money supply (per-game series may be shorter if a game
            # ended early; only fold in the snapshots that exist).
            for idx, value in enumerate(summary.money_supply):
                if idx < len(money_sums):
                    money_sums[idx] += value
                    money_counts[idx] += 1

            # Accumulate supply-chain liveness counters.
            flow = summary.resource_flow
            if flow is not None:
                for dst, src in (
                    (flow_produced, flow.produced),
                    (flow_consumed, flow.consumed),
                    (flow_traded, flow.traded),
                    (flow_starvation, flow.starvation),
                ):
                    for name, value in src.items():
                        dst[name] = dst.get(name, 0) + value

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

        money_means = [
            round(s / c, 2) if c else 0.0
            for s, c in zip(money_sums, money_counts)
        ]

        return SimulationStats(
            num_games=self.num_games,
            num_years=self.num_years,
            role_stats=stats,
            price_history_mean=price_means,
            money_supply_mean=money_means,
            flow_produced=flow_produced,
            flow_consumed=flow_consumed,
            flow_traded=flow_traded,
            flow_starvation=flow_starvation,
            fallback_counts=fallback_counts,
            gini_mean=round(gini_sum / self.num_games, 4) if self.num_games else 0.0,
            hhi_mean=round(hhi_sum / self.num_games, 4) if self.num_games else 0.0,
        )

    def export_csv(self, stats: SimulationStats, path: str) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)

        # Role summary
        role_csv = p.parent / (p.stem + "_roles.csv")
        with open(role_csv, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "role", "games", "wins", "win_rate_%", "avg_wealth",
                "share_mean_%", "share_stddev_%",
            ])
            for rs in stats.role_stats.values():
                writer.writerow([
                    rs.role_name,
                    rs.total_games,
                    rs.wins,
                    f"{rs.win_rate * 100:.1f}",
                    f"{rs.avg_wealth:.1f}",
                    f"{rs.share_mean * 100:.2f}",
                    f"{rs.share_stddev * 100:.2f}",
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

        # Money supply per snapshot (index 0 = opening balance)
        money_csv = p.parent / (p.stem + "_money.csv")
        with open(money_csv, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["snapshot_index", "mean_money_supply"])
            for i, value in enumerate(stats.money_supply_mean):
                writer.writerow([i, f"{value:.2f}"])

        # Supply-chain liveness per resource (B1/B2, #73)
        flow_csv = p.parent / (p.stem + "_flows.csv")
        resources = sorted(
            set(stats.flow_produced)
            | set(stats.flow_consumed)
            | set(stats.flow_traded)
            | set(stats.flow_starvation)
        )
        with open(flow_csv, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["resource", "produced", "consumed", "traded", "starvation_events"])
            for r in resources:
                writer.writerow([
                    r,
                    f"{stats.flow_produced.get(r, 0):.0f}",
                    f"{stats.flow_consumed.get(r, 0):.0f}",
                    f"{stats.flow_traded.get(r, 0):.0f}",
                    stats.flow_starvation.get(r, 0),
                ])

        print(f"Role stats  → {role_csv}")
        print(f"Price history → {price_csv}")
        print(f"Money supply → {money_csv}")
        print(f"Resource flows → {flow_csv}")


def _parse_seeds(raw: str) -> list[int]:
    seeds: list[int] = []
    for part in raw.split(","):
        value = part.strip()
        if value:
            seeds.append(int(value))
    if not seeds:
        raise ValueError("--seeds must include at least one integer seed")
    return seeds


def _print_role_balance(stats: SimulationStats, title: str = "Role Balance") -> None:
    print(f"\n--- {title} ---")
    print(f"{'Role':<16} {'Wins':>6} {'Win%':>7} {'AvgWealth':>12} {'Share%':>8} {'±σ':>6}")
    print("-" * 60)
    for rs in stats.role_stats.values():
        print(
            f"{rs.role_name:<16} {rs.wins:>6} "
            f"{rs.win_rate*100:>6.1f}% {rs.avg_wealth:>12.1f} Dp"
            f"{rs.share_mean*100:>7.1f}% {rs.share_stddev*100:>5.1f}%"
        )
    print(
        f"  Concentration: mean Gini {stats.gini_mean:.3f}, "
        f"mean HHI {stats.hhi_mean:.3f} (balanced 7-player HHI ≈ 0.143)"
    )


def _print_fallback_telemetry(stats: SimulationStats) -> None:
    """R2: surface decision prompts the sim answered with degenerate defaults."""
    if not stats.fallback_counts:
        return
    print("\n--- Sim Fallback Telemetry (decisions answered by _SilentIO defaults) ---")
    top = sorted(stats.fallback_counts.items(), key=lambda kv: -kv[1])[:10]
    for method, count in top:
        per_game = count / stats.num_games if stats.num_games else 0.0
        print(f"  {method:<20} {count:>8,}  ({per_game:.1f}/game)")
    print("  ⚠ nonzero counts mean the sim defaulted through these mechanics"
          " (min/first/yes/zero) rather than modelling them.")


def _print_money_supply(stats: SimulationStats) -> None:
    series = stats.money_supply_mean
    if not series:
        return
    opening, closing = series[0], series[-1]
    growth = ((closing / opening - 1) * 100) if opening else 0.0
    print("\n--- Money Supply (mean Dollops in circulation) ---")
    print(f"  Opening: {opening:>12.1f} Dp")
    print(f"  Closing: {closing:>12.1f} Dp   ({growth:+.1f}% over the game)")
    per_season = (closing - opening) / (len(series) - 1) if len(series) > 1 else 0.0
    print(f"  Net mint/season: {per_season:>+9.1f} Dp")


def _print_resource_flows(stats: SimulationStats) -> None:
    if not (stats.flow_produced or stats.flow_consumed or stats.flow_traded):
        return
    print("\n--- Supply-Chain Liveness (totals across all games) ---")
    resources = sorted(
        set(stats.flow_produced) | set(stats.flow_consumed) | set(stats.flow_traded)
    )
    print(f"{'Resource':<18}{'Produced':>12}{'Consumed':>12}{'Traded':>12}")
    for r in resources:
        print(
            f"{r:<18}"
            f"{stats.flow_produced.get(r, 0):>12,.0f}"
            f"{stats.flow_consumed.get(r, 0):>12,.0f}"
            f"{stats.flow_traded.get(r, 0):>12,.0f}"
        )
    # Flag the things calibration cares about: resources that are consumed or
    # traded but never produced (a dead supply chain), and the worst input
    # starvations.
    never_produced = sorted(
        r for r in (set(stats.flow_consumed) | set(stats.flow_traded))
        if stats.flow_produced.get(r, 0) == 0
    )
    if never_produced:
        print(f"  ⚠ consumed/traded but NEVER produced: {', '.join(never_produced)}")
    if stats.flow_starvation:
        top = sorted(stats.flow_starvation.items(), key=lambda kv: -kv[1])[:5]
        print("  ⚠ top input starvations (producer stalled on missing input):")
        for name, count in top:
            print(f"      {name}: {count:,} events")


def _print_multi_seed_summary(seed_stats: list[tuple[int, SimulationStats]]) -> None:
    role_names = list(ROLES.keys())
    print("\n--- Multi-Seed Win Rate Summary ---")
    header = f"{'Role':<16}" + "".join(f"{seed:>10}" for seed, _ in seed_stats) + f"{'Mean':>10}"
    print(header)
    print("-" * len(header))
    for role_name in role_names:
        rates = [
            stats.role_stats[role_name].win_rate * 100
            for _, stats in seed_stats
        ]
        row = f"{role_name:<16}" + "".join(f"{rate:>9.1f}%" for rate in rates)
        row += f"{(sum(rates) / len(rates)):>9.1f}%"
        print(row)

    # R1: wealth share across seeds with a cross-seed variance bar.  The
    # regression rule of thumb: a share change is only a real move if it falls
    # outside mean ± 2σ of the baseline.
    print("\n--- Multi-Seed Wealth Share Summary (mean ± cross-seed σ) ---")
    print(f"{'Role':<16}" + "".join(f"{seed:>10}" for seed, _ in seed_stats)
          + f"{'Mean':>9}{'σ':>7}")
    for role_name in role_names:
        shares = [
            stats.role_stats[role_name].share_mean * 100
            for _, stats in seed_stats
        ]
        mean = sum(shares) / len(shares)
        sd = statistics.stdev(shares) if len(shares) > 1 else 0.0
        row = f"{role_name:<16}" + "".join(f"{s:>9.1f}%" for s in shares)
        row += f"{mean:>8.1f}%{sd:>6.1f}%"
        print(row)
    print("  Regression rule: flag a change only when it exceeds baseline mean ± 2σ.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Island Traders simulation runner")
    parser.add_argument("--games", type=int, default=100, help="Number of games to simulate")
    parser.add_argument("--years", type=int, default=3, help="Years per game")
    parser.add_argument("--seed", type=int, default=42, help="RNG seed for reproducibility")
    parser.add_argument(
        "--seeds",
        type=str,
        default=None,
        help="Comma-separated RNG seeds to run as separate batches, e.g. 42,1,7,99",
    )
    parser.add_argument("--charts", type=str, default=None, help="Path to event_charts.yaml")
    parser.add_argument("--output", type=str, default="simulation_results/run", help="Output CSV prefix")
    args = parser.parse_args()

    if args.seeds:
        seed_stats: list[tuple[int, SimulationStats]] = []
        for seed in _parse_seeds(args.seeds):
            print(f"Running {args.games} games × {args.years} years (seed={seed}) ...")
            runner = SimulationRunner(
                num_games=args.games,
                num_years=args.years,
                seed=seed,
                event_charts_path=args.charts,
            )
            stats = runner.run()
            seed_stats.append((seed, stats))
            _print_role_balance(stats, title=f"Role Balance — seed {seed}")
            _print_money_supply(stats)
            _print_resource_flows(stats)
            _print_fallback_telemetry(stats)
            runner.export_csv(stats, f"{args.output}_seed_{seed}")
        _print_multi_seed_summary(seed_stats)
        return

    print(f"Running {args.games} games × {args.years} years (seed={args.seed}) ...")
    runner = SimulationRunner(
        num_games=args.games,
        num_years=args.years,
        seed=args.seed,
        event_charts_path=args.charts,
    )
    stats = runner.run()
    _print_role_balance(stats)
    _print_money_supply(stats)
    _print_resource_flows(stats)
    _print_fallback_telemetry(stats)
    runner.export_csv(stats, args.output)


if __name__ == "__main__":
    main()
