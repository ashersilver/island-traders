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


def test_simulation_money_supply_has_opening_plus_one_per_season():
    runner = SimulationRunner(num_games=4, num_years=2, seed=42)
    stats = runner.run()
    # Opening snapshot + one per season (2 years × 4 seasons).
    assert len(stats.money_supply_mean) == 2 * 4 + 1


def test_simulation_money_supply_opens_at_total_starting_dollops():
    from island_traders.constants import STARTING_DOLLOPS

    runner = SimulationRunner(num_games=3, num_years=1, seed=7)
    stats = runner.run()
    # All-AI game seats one player per role; opening circulation is the sum of
    # every island's starting treasury.
    expected = STARTING_DOLLOPS * len(stats.role_stats)
    assert stats.money_supply_mean[0] == pytest.approx(expected)


def test_simulation_records_resource_flows():
    runner = SimulationRunner(num_games=3, num_years=1, seed=42)
    stats = runner.run()
    # Some production happens every game, so produced totals are non-empty and
    # positive; traded volume is recorded separately.
    assert stats.flow_produced, "expected some produced resources"
    assert all(v > 0 for v in stats.flow_produced.values())
    # Every traded/consumed resource name is a real resource string (sanity:
    # keys come straight from ResourceType.value).
    from island_traders.models.resource import ResourceType

    valid = {r.value for r in ResourceType}
    for bucket in (stats.flow_produced, stats.flow_consumed, stats.flow_traded):
        assert set(bucket).issubset(valid)


def test_production_telemetry_records_produced_and_starvation():
    from island_traders.engine.production import ProductionEngine, InsufficientInputsError
    from island_traders.engine.telemetry import ResourceFlowTelemetry
    from island_traders.engine.events import EventResult
    from island_traders.models.player import Player
    from island_traders.models.role import ROLES
    from island_traders.models.resource import ResourceType

    telem = ResourceFlowTelemetry()
    engine = ProductionEngine()
    engine.telemetry = telem

    # A Miner with no inputs at all should stall and log starvation, not crash
    # the telemetry path.
    player = Player(player_id=1, name="M", roles=[ROLES["Miner"]], dollops=0.0)
    for r in list(ResourceType):
        have = player.inventory.get(r)
        if have:
            player.give_resources(r, have)
    event = EventResult(event_name="none")
    try:
        engine.produce(player, event, season_name="Spring")
    except InsufficientInputsError:
        pass
    assert telem.starvation, "starvation should be recorded on missing inputs"


def test_parse_seeds_accepts_comma_separated_values():
    assert _parse_seeds("42, 1,7") == [42, 1, 7]


def test_parse_seeds_rejects_empty_values():
    with pytest.raises(ValueError):
        _parse_seeds(" , ")
