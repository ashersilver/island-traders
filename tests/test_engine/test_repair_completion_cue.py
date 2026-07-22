from __future__ import annotations

from island_traders.cli.prompts import FakeIOAdapter
from island_traders.constants_capacity import CAPITAL_CATALOGUE
from island_traders.engine.game import Game, GameConfig, PlayerSpec
from island_traders.models.player import CapitalUnit

_CATALOGUE = {it.item_id: it for it in CAPITAL_CATALOGUE}


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


def _seed_failed_with_repair(player, item_id, tick):
    unit = CapitalUnit(item_id=item_id, unit_id=999, status="failed",
                       repair_completes_at_tick=tick)
    player.capital_units.setdefault(item_id, []).append(unit)
    player.capital_repair_in_progress.append(
        {"item_id": item_id, "count": 1, "completes_at_tick": tick})
    return unit


def test_completed_repair_records_recently_repaired_cue():
    game = _farmer_game()
    player = game.players[0]
    item_id = "farmer.tractor"
    unit = _seed_failed_with_repair(player, item_id, tick=5)

    game._complete_capital_repairs(player, current_tick=5, catalogue=_CATALOGUE)

    assert unit.status == "in_service"
    assert len(player.recently_repaired) == 1
    entry = player.recently_repaired[0]
    assert entry["item_id"] == item_id
    assert entry["count"] == 1
    assert entry["name"]  # the catalogue display name


def test_recently_repaired_is_fresh_each_season():
    game = _farmer_game()
    player = game.players[0]
    _seed_failed_with_repair(player, "farmer.tractor", tick=5)
    game._complete_capital_repairs(player, current_tick=5, catalogue=_CATALOGUE)
    assert player.recently_repaired

    # A later season with no completions clears the cue.
    game._complete_capital_repairs(player, current_tick=6, catalogue=_CATALOGUE)
    assert player.recently_repaired == []


def test_pending_repair_not_yet_due_is_not_cued():
    game = _farmer_game()
    player = game.players[0]
    _seed_failed_with_repair(player, "farmer.tractor", tick=9)

    game._complete_capital_repairs(player, current_tick=5, catalogue=_CATALOGUE)

    assert player.recently_repaired == []
    assert player.capital_repair_in_progress  # still queued
