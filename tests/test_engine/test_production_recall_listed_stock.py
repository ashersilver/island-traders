from __future__ import annotations

from island_traders.cli.prompts import FakeIOAdapter
from island_traders.engine.events import EventResult
from island_traders.engine.game import Game, GameConfig, PlayerSpec
from island_traders.engine.production import (
    InsufficientInputsError,
    ProductionEngine,
)


NORMAL = EventResult("Normal Operations", yield_modifier=1.0)


def _farmer_game() -> Game:
    game = Game(
        GameConfig(
            num_years=1,
            player_specs=[PlayerSpec(name="P", role_names=["Farmer"], is_human=False)],
        ),
        FakeIOAdapter(),
    )
    game.setup()
    return game


def _first_input(production, player):
    inputs = production._all_inputs(player, "Spring", None)
    for r, qty in inputs.items():
        if qty > 0:
            return r, qty
    raise AssertionError("Farmer has no positive-qty inputs in Spring")


def test_production_recalls_own_listed_stock_to_cover_shortfall():
    game = _farmer_game()
    farmer = game.players[0]
    production = game.turn_manager.production
    market = game.market
    r, needed = _first_input(production, farmer)

    # Hold exactly what's needed, then list all of it for sale.
    have = farmer.inventory.get(r)
    if have:
        farmer.give_resources(r, have)
    farmer.receive_resources(r, needed)
    market.post_offer(farmer, r, 99.0, needed)
    assert farmer.inventory.get(r) == 0
    assert market.listed_quantity(farmer.player_id, r) == needed

    # Feasibility now counts the unsold ask...
    ok, missing = production.can_produce(farmer, NORMAL, "Spring")
    assert ok, missing

    # ...and production recalls just the shortfall and succeeds.
    produced = production.produce(farmer, NORMAL, "Spring")
    assert produced  # some outputs were made
    assert market.listed_quantity(farmer.player_id, r) == 0


def test_recall_offers_pulls_back_only_requested_units():
    from island_traders.models.resource import ResourceType
    game = _farmer_game()
    farmer = game.players[0]
    market = game.market
    r = ResourceType.OIL

    have = farmer.inventory.get(r)
    if have:
        farmer.give_resources(r, have)
    farmer.receive_resources(r, 10)
    market.post_offer(farmer, r, 99.0, 10)
    assert farmer.inventory.get(r) == 0

    recalled = market.recall_offers(farmer, r, 4)
    assert recalled == 4
    assert farmer.inventory.get(r) == 4
    assert market.listed_quantity(farmer.player_id, r) == 6


def test_without_market_handle_shortfall_still_fails():
    # A bare engine (no market wired) keeps the original strict behaviour.
    game = _farmer_game()
    farmer = game.players[0]
    r, needed = _first_input(game.turn_manager.production, farmer)

    bare = ProductionEngine()  # market is None
    # Drain the input entirely.
    have = farmer.inventory.get(r)
    if have:
        farmer.give_resources(r, have)
    try:
        bare.produce(farmer, NORMAL, "Spring")
    except InsufficientInputsError as exc:
        assert r in exc.missing
    else:
        raise AssertionError("expected InsufficientInputsError without stock")
