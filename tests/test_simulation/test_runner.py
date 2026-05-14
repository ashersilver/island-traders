import pytest

from island_traders.simulation.runner import SimulationRunner, _parse_seeds


def test_simulation_runs_to_completion():
    runner = SimulationRunner(num_games=5, num_years=1, seed=99)
    stats = runner.run()
    assert stats.num_games == 5
    assert len(stats.role_stats) == 7  # one entry per role


def test_simulation_all_games_counted():
    runner = SimulationRunner(num_games=10, num_years=1, seed=7)
    stats = runner.run()
    total_games = sum(rs.total_games for rs in stats.role_stats.values())
    # Each role appears once per game = 7 roles × 10 games
    assert total_games == 70


def test_simulation_win_counts_sum_to_num_games():
    runner = SimulationRunner(num_games=20, num_years=1, seed=1)
    stats = runner.run()
    total_wins = sum(rs.wins for rs in stats.role_stats.values())
    assert total_wins == 20


def test_simulation_price_history_populated():
    runner = SimulationRunner(num_games=3, num_years=1, seed=42)
    stats = runner.run()
    # 1 year × 4 seasons = 4 entries per resource
    for resource, prices in stats.price_history_mean.items():
        assert len(prices) == 4, f"{resource} has {len(prices)} entries, expected 4"


def test_simulation_deterministic_with_same_seed():
    r1 = SimulationRunner(num_games=5, num_years=1, seed=42).run()
    r2 = SimulationRunner(num_games=5, num_years=1, seed=42).run()
    for role in r1.role_stats:
        assert r1.role_stats[role].wins == r2.role_stats[role].wins


def test_parse_seeds_accepts_comma_separated_values():
    assert _parse_seeds("42, 1,7") == [42, 1, 7]


def test_parse_seeds_rejects_empty_values():
    with pytest.raises(ValueError):
        _parse_seeds(" , ")
