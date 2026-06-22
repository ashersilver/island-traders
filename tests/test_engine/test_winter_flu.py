from __future__ import annotations

import random

from island_traders.cli.prompts import FakeIOAdapter
from island_traders.engine.ai import AIStrategy
from island_traders.engine.events import EventResult
from island_traders.engine.flu import vaccine_doses_needed
from island_traders.engine.production import ProductionEngine
from island_traders.engine.trading import TradingEngine
from island_traders.engine.turn import TurnManager
from island_traders.models.deal import DealLedger
from island_traders.models.market import Market
from island_traders.models.player import Player
from island_traders.models.resource import ResourceType
from island_traders.models.role import ROLES


def _player(pid: int, role: str = "Farmer", *, is_human: bool = True) -> Player:
    return Player(pid, f"Player{pid}", [ROLES[role]], 500.0, is_human=is_human)


def _turn_manager(players, *, rng=None, market=None) -> TurnManager:
    market = market or Market()
    return TurnManager(
        players=players,
        production_engine=ProductionEngine(),
        trading_engine=TradingEngine(market, DealLedger(), players),
        market=market,
        io_adapter=FakeIOAdapter(),
        rng=rng,
    )


def test_vaccine_doses_needed_uses_population_not_workforce():
    assert vaccine_doses_needed(0) == 0
    assert vaccine_doses_needed(1) == 1
    assert vaccine_doses_needed(100) == 5
    assert vaccine_doses_needed(101) == 6


def test_non_winter_does_not_apply_or_consume_vaccines():
    player = _player(1)
    player.receive_resources(ResourceType.VACCINE, 5)
    tm = _turn_manager([player])
    event_results = {player.player_id: EventResult("Normal Operations")}

    returned = tm._apply_winter_flu("Autumn", event_results, strain_loss=0.20)

    assert returned is event_results
    assert player.inventory.get(ResourceType.VACCINE) == 5
    assert event_results[player.player_id].yield_modifier == 1.0
    assert event_results[player.player_id].flu_effective_loss == 0.0


def test_winter_flu_consumes_vaccines_and_mitigates_loss_proportionally():
    zero = _player(1)
    partial = _player(2)
    full = _player(3)
    partial.receive_resources(ResourceType.VACCINE, 2)
    full.receive_resources(ResourceType.VACCINE, 5)
    tm = _turn_manager([zero, partial, full])

    results = tm._apply_winter_flu(
        "Winter",
        {
            zero.player_id: EventResult("Normal Operations"),
            partial.player_id: EventResult("Normal Operations"),
            full.player_id: EventResult("Normal Operations"),
        },
        strain_loss=0.20,
    )

    assert zero.inventory.get(ResourceType.VACCINE) == 0
    assert partial.inventory.get(ResourceType.VACCINE) == 0
    assert full.inventory.get(ResourceType.VACCINE) == 0
    assert results[zero.player_id].flu_doses_needed == 5
    assert results[zero.player_id].flu_doses_administered == 0
    assert results[zero.player_id].flu_effective_loss == 0.20
    assert results[zero.player_id].yield_modifier == 0.80
    assert results[partial.player_id].flu_doses_administered == 2
    assert results[partial.player_id].flu_effective_loss == 0.136
    assert results[partial.player_id].yield_modifier == 0.864
    assert results[full.player_id].flu_doses_administered == 5
    assert results[full.player_id].flu_effective_loss == 0.04
    assert results[full.player_id].yield_modifier == 0.96


def test_winter_flu_does_not_overconsume_and_stacks_with_existing_event():
    player = _player(1)
    player.receive_resources(ResourceType.VACCINE, 9)
    original = EventResult("Poor Weather", yield_modifier=0.50)
    tm = _turn_manager([player])

    results = tm._apply_winter_flu(
        "Winter",
        {player.player_id: original},
        strain_loss=0.20,
    )
    event = results[player.player_id]

    assert player.inventory.get(ResourceType.VACCINE) == 4
    assert event is not original
    assert original.yield_modifier == 0.50
    assert event.yield_modifier == 0.48
    assert event.event_name == "Poor Weather + Winter Flu"


def test_flu_strain_roll_is_deterministic_under_fixed_seed():
    first = _turn_manager([], rng=random.Random(42))
    second = _turn_manager([], rng=random.Random(42))

    assert [first._roll_flu_strain_loss() for _ in range(8)] == [
        second._roll_flu_strain_loss() for _ in range(8)
    ]


def test_ai_buys_vaccines_in_autumn_and_keeps_coverage_reserve():
    buyer = _player(1, is_human=False)
    doctor = _player(2, "Doctor", is_human=False)
    market = Market()
    trading = TradingEngine(market, DealLedger(), [buyer, doctor])
    doctor.receive_resources(ResourceType.VACCINE, 8)
    market.post_offer(doctor, ResourceType.VACCINE, 10.0, 8)

    actions = AIStrategy().take_turn(
        buyer,
        market,
        [doctor],
        ProductionEngine(),
        trading,
        EventResult("Normal Operations"),
        season_name="Autumn",
        year=0,
        season_index=2,
    )

    assert buyer.inventory.get(ResourceType.VACCINE) == 5
    assert market.best_offer(ResourceType.VACCINE).remaining == 3
    assert any("stocked 5x Vaccine" in action for action in actions)


def test_ai_doctor_lists_only_vaccine_surplus_above_own_winter_cover():
    doctor = _player(1, "Doctor", is_human=False)
    doctor.receive_resources(ResourceType.VACCINE, 8)
    market = Market()
    trading = TradingEngine(market, DealLedger(), [doctor])

    AIStrategy().take_turn(
        doctor,
        market,
        [],
        ProductionEngine(),
        trading,
        EventResult("Normal Operations"),
        season_name="Autumn",
        year=0,
        season_index=2,
    )

    offer = market.best_offer(ResourceType.VACCINE)
    assert offer is not None
    assert doctor.inventory.get(ResourceType.VACCINE) >= vaccine_doses_needed(
        doctor.population
    )
