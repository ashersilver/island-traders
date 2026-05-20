"""TurnAction.INVEST — take up an opening-catalogue item not yet owned."""
from __future__ import annotations

from island_traders.cli.prompts import FakeIOAdapter
from island_traders.constants_capacity import CAPITAL_CATALOGUE
from island_traders.engine.production import ProductionEngine
from island_traders.engine.trading import TradingEngine
from island_traders.engine.turn import TurnManager, TurnResult
from island_traders.models.capacity import items_for_role
from island_traders.models.deal import DealLedger
from island_traders.models.market import Market
from island_traders.models.player import Player
from island_traders.models.role import ROLES


class InvestIO(FakeIOAdapter):
    """Pick a specific item_id from the available investments list."""
    def __init__(self, chosen_item_id: str | None = "skip"):
        super().__init__()
        self.chosen_item_id = chosen_item_id

    def choose_option(self, prompt, options):
        if self.chosen_item_id == "skip":
            return options[0]["value"] if options else None
        for opt in options:
            if opt["value"] == self.chosen_item_id:
                return opt["value"]
        return None


def _farmer_tm(player, io=None):
    market = Market()
    return TurnManager(
        players=[player],
        production_engine=ProductionEngine(),
        trading_engine=TradingEngine(market, DealLedger()),
        market=market,
        io_adapter=io or InvestIO(chosen_item_id="farmer.storage_building"),
    )


def _farmer_player(dollops: float = 1500.0) -> Player:
    return Player(
        player_id=0, name="Farmer", roles=[ROLES["Farmer"]],
        dollops=dollops, is_human=True,
    )


def test_invest_adds_chosen_item_immediately_and_debits_cost():
    p = _farmer_player(dollops=200.0)
    assert p.capital_inventory.get("farmer.storage_building", 0) == 0
    tm = _farmer_tm(p, InvestIO(chosen_item_id="farmer.storage_building"))
    tm._action_invest(
        p, TurnResult(player_id=p.player_id, season=0, year=0),
        year=0, season_index=0,
    )
    # storage_building cost 40 (see constants_capacity catalogue).
    assert p.capital_inventory.get("farmer.storage_building", 0) == 1
    assert p.dollops == 160.0
    # Acquired tick set to the current tick (0).
    assert p.capital_acquired_ticks["farmer.storage_building"] == [0]


def test_invest_skips_items_already_owned():
    p = _farmer_player()
    p.add_capital("farmer.storage_building", 1, acquired_tick=0)
    tm = _farmer_tm(p, InvestIO(chosen_item_id="farmer.storage_building"))
    tm._action_invest(
        p, TurnResult(player_id=p.player_id, season=0, year=0),
        year=0, season_index=0,
    )
    # The owned item must NOT appear in the choices presented; IO falls
    # back to None → "Unknown selection." Stock unchanged.
    assert p.capital_inventory.get("farmer.storage_building", 0) == 1


def test_invest_refuses_when_player_cannot_afford():
    p = _farmer_player(dollops=10.0)   # too poor for storage_building (40 Dp)
    tm = _farmer_tm(p, InvestIO(chosen_item_id="farmer.storage_building"))
    tm._action_invest(
        p, TurnResult(player_id=p.player_id, season=0, year=0),
        year=0, season_index=0,
    )
    assert p.capital_inventory.get("farmer.storage_building", 0) == 0
    assert p.dollops == 10.0


def test_invest_reports_no_remaining_when_role_catalogue_fully_taken():
    p = _farmer_player(dollops=99999.0)
    # Pre-own every Farmer-catalogue item.
    for item in items_for_role(CAPITAL_CATALOGUE, "Farmer"):
        if p.capital_inventory.get(item.item_id, 0) == 0:
            p.add_capital(item.item_id, 1, acquired_tick=0)
    io = InvestIO(chosen_item_id="farmer.storage_building")
    tm = _farmer_tm(p, io)
    tm._action_invest(
        p, TurnResult(player_id=p.player_id, season=0, year=0),
        year=0, season_index=0,
    )
    log = "\n".join(io.printed)
    assert "No remaining opening investments" in log
