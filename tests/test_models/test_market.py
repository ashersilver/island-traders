import pytest
from island_traders.models.market import Market, InsufficientSupplyError
from island_traders.models.player import Player, InsufficientFundsError
from island_traders.models.resource import ResourceType
from island_traders.models.role import ROLES
from island_traders.constants import BASE_PRICES


def make_player(pid, role_name, dollops=200.0):
    return Player(pid, f"P{pid}", [ROLES[role_name]], dollops, is_human=False)


def test_price_at_equilibrium():
    m = Market()
    m.post_supply(ResourceType.FOOD, 5)
    m.post_demand(ResourceType.FOOD, 5)
    price = m.current_price(ResourceType.FOOD)
    base = BASE_PRICES["Food"]
    assert abs(price - base) < 0.01


def test_price_rises_on_scarcity():
    m = Market()
    m.post_supply(ResourceType.FOOD, 0)
    m.post_demand(ResourceType.FOOD, 10)
    price = m.current_price(ResourceType.FOOD)
    assert price > BASE_PRICES["Food"]


def test_price_drops_on_glut():
    m = Market()
    m.post_supply(ResourceType.FOOD, 100)
    m.post_demand(ResourceType.FOOD, 1)
    price = m.current_price(ResourceType.FOOD)
    assert price < BASE_PRICES["Food"]


def test_execute_buy_transfers_resources_and_gold():
    m = Market()
    m.post_supply(ResourceType.FOOD, 10)
    buyer = make_player(0, "Banker")
    paid = m.execute_buy(buyer, ResourceType.FOOD, 3)
    assert buyer.inventory.get(ResourceType.FOOD) == 3
    assert buyer.dollops == 200.0 - paid


def test_execute_buy_reduces_supply():
    m = Market()
    m.post_supply(ResourceType.ORE, 8)
    buyer = make_player(0, "Banker")
    m.execute_buy(buyer, ResourceType.ORE, 3)
    assert m.supply.get(ResourceType.ORE, 0) == 5


def test_execute_buy_insufficient_supply_raises():
    m = Market()
    m.post_supply(ResourceType.FOOD, 2)
    buyer = make_player(0, "Banker")
    with pytest.raises(InsufficientSupplyError):
        m.execute_buy(buyer, ResourceType.FOOD, 5)


def test_execute_buy_insufficient_funds_raises():
    m = Market()
    m.post_supply(ResourceType.CAPITAL_EQUIPMENT, 10)
    buyer = make_player(0, "Banker", dollops=1.0)
    with pytest.raises(InsufficientFundsError):
        m.execute_buy(buyer, ResourceType.CAPITAL_EQUIPMENT, 5)


def test_execute_sell_increases_supply():
    m = Market()
    seller = make_player(0, "Farmer")
    seller.receive_resources(ResourceType.FOOD, 4)
    m.execute_sell(seller, ResourceType.FOOD, 4)
    assert m.supply.get(ResourceType.FOOD, 0) == 4


def test_snapshot_appends_entry():
    m = Market()
    assert len(m.price_history) == 0
    m.snapshot_prices(0, 0)
    assert len(m.price_history) == 1


def test_reset_period_signals_zeros_demand():
    m = Market()
    m.post_demand(ResourceType.FOOD, 5)
    m.reset_period_signals()
    assert m.demand.get(ResourceType.FOOD, 0) == 0


def test_price_shock_raises_price():
    m = Market()
    base_price = m.current_price(ResourceType.OIL)
    m.apply_price_shock(ResourceType.OIL, 2.0, 1)
    shocked_price = m.current_price(ResourceType.OIL)
    assert shocked_price > base_price


def test_market_summary_reports_bid_and_ask_books():
    m = Market()
    seller = make_player(1, "Farmer")
    buyer = make_player(2, "Banker")
    seller.receive_resources(ResourceType.FOOD, 4)

    m.post_offer(seller, ResourceType.FOOD, 12.5, 4)
    m.post_bid(buyer, ResourceType.FOOD, 10.0, 3)

    summary = m.market_summary()[ResourceType.FOOD.value]
    assert summary["ask_price"] == 12.5
    assert summary["ask_quantity"] == 4
    assert summary["bid_price"] == 10.0
    assert summary["bid_quantity"] == 3
    assert summary["best_price"] == 12.5
    assert summary["quantity"] == 4


def test_sell_to_bids_transfers_to_highest_bidder():
    m = Market()
    seller = make_player(1, "Farmer")
    low = make_player(2, "Banker", dollops=200.0)
    high = make_player(3, "Banker", dollops=200.0)
    seller.receive_resources(ResourceType.FOOD, 5)

    m.post_bid(low, ResourceType.FOOD, 8.0, 5)
    m.post_bid(high, ResourceType.FOOD, 11.0, 2)
    paid, sold = m.sell_to_bids(seller, ResourceType.FOOD, 3, [seller, low, high])

    assert sold == 3
    assert paid == 30.0
    assert high.inventory.get(ResourceType.FOOD) == 2
    assert low.inventory.get(ResourceType.FOOD) == 1
    assert seller.inventory.get(ResourceType.FOOD) == 2
    assert seller.dollops == 230.0
