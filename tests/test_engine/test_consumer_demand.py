from island_traders.cli.prompts import FakeIOAdapter
from island_traders.engine.consumer import (
    buy_household_goods_from_offers,
    consumer_demand_plan,
    structural_consumer_demand_units,
)
from island_traders.engine.game import Game, GameConfig
from island_traders.engine.production import ProductionEngine
from island_traders.engine.trading import TradingEngine
from island_traders.engine.turn import TurnManager
from island_traders.models.market import Market
from island_traders.models.player import Player
from island_traders.models.resource import ResourceType
from island_traders.models.role import ROLES
from island_traders.models.deal import DealLedger


def test_household_cash_buys_end_products_from_producer_offers():
    buyer = Player(1, "Residents", [ROLES["Farmer"]], 100.0, is_human=False)
    seller = Player(2, "Forge", [ROLES["Manufacturer"]], 10.0, is_human=False)
    buyer.household_cash = 60.0
    seller.receive_resources(ResourceType.GOODS, 2)
    market = Market()
    market.post_offer(seller, ResourceType.GOODS, 30.0, 2)

    result = buy_household_goods_from_offers(
        buyer,
        market,
        {ResourceType.GOODS: 2},
    )

    assert result.bought == {ResourceType.GOODS: 2}
    assert result.spent == 60.0
    assert buyer.household_cash == 0.0
    assert seller.dollops == 70.0
    assert market.best_offer(ResourceType.GOODS) is None


def test_unfilled_household_demand_posts_price_signal():
    buyer = Player(1, "Residents", [ROLES["Farmer"]], 100.0, is_human=False)
    buyer.household_cash = 20.0
    market = Market()

    result = buy_household_goods_from_offers(
        buyer,
        market,
        {ResourceType.HEALTH_SERVICES: 1},
    )

    assert result.bought == {}
    assert result.unmet == {ResourceType.HEALTH_SERVICES: 1}
    assert buyer.household_cash == 20.0
    assert market.demand[ResourceType.HEALTH_SERVICES] == 1


def test_consumer_demand_plan_scales_goods_and_seasonal_health_vaccine():
    player = Player(1, "Island", [ROLES["Banker"]], 1300.0, is_human=False)
    player.population = 120

    summer = consumer_demand_plan(player, "Summer", casualties=2).units
    autumn = consumer_demand_plan(player, "Autumn").units

    assert summer[ResourceType.FOOD] == 2
    assert summer[ResourceType.GOODS] == 3
    assert summer[ResourceType.HEALTH_SERVICES] == 4
    assert autumn[ResourceType.VACCINE] == 2


def test_structural_consumer_demand_informs_goods_advisory():
    player = Player(1, "Island", [ROLES["Farmer"]], 1300.0, is_human=False)
    player.population = 120

    assert structural_consumer_demand_units(ResourceType.GOODS, [player], "Spring") == 3.0


def test_money_supply_counts_household_cash():
    game = Game(GameConfig([]), FakeIOAdapter())
    player = Player(1, "Island", [ROLES["Farmer"]], 10.0, is_human=False)
    player.personal_cash = 5.0
    player.household_cash = 7.0
    game.players = [player]

    assert game._total_money_supply() == 22.0


def test_total_wealth_counts_household_cash_as_island_wealth():
    player = Player(1, "Island", [ROLES["Farmer"]], 10.0, is_human=False)
    player.household_cash = 7.0

    breakdown = player.wealth_breakdown({})

    assert breakdown["components"]["treasury"] == 10.0
    assert breakdown["components"]["household_cash"] == 7.0
    assert breakdown["total"] == 17.0


def test_turn_manager_processes_household_demand_after_ai_listings():
    buyer = Player(1, "Residents", [ROLES["Farmer"]], 100.0, is_human=False)
    seller = Player(2, "Clinic", [ROLES["Doctor"]], 10.0, is_human=False)
    buyer.household_cash = 18.0
    seller.receive_resources(ResourceType.HEALTH_SERVICES, 1)
    market = Market()
    market.post_offer(seller, ResourceType.HEALTH_SERVICES, 18.0, 1)
    tm = TurnManager(
        [buyer, seller],
        ProductionEngine(),
        TradingEngine(market, DealLedger()),
        market,
        FakeIOAdapter(),
    )

    tm._process_consumer_demand("Summer", [])

    assert buyer.household_cash == 0.0
    assert seller.dollops == 28.0
