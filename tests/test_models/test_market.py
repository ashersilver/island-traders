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
    m.post_supply(ResourceType.LABORATORY_EQUIPMENT, 10)
    buyer = make_player(0, "Banker", dollops=1.0)
    with pytest.raises(InsufficientFundsError):
        m.execute_buy(buyer, ResourceType.LABORATORY_EQUIPMENT, 5)


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


def test_exact_bid_auto_resolves_against_existing_offer():
    m = Market()
    seller = make_player(1, "Farmer")
    buyer = make_player(2, "Banker", dollops=200.0)
    seller.receive_resources(ResourceType.FOOD, 5)

    offer = m.post_offer(seller, ResourceType.FOOD, 12.5, 5)
    bid = m.post_bid(buyer, ResourceType.FOOD, 12.5, 3)

    assert bid.remaining == 0
    assert offer.remaining == 2
    assert buyer.inventory.get(ResourceType.FOOD) == 3
    assert buyer.dollops == 162.5
    assert seller.dollops == 237.5


def test_exact_offer_auto_resolves_against_existing_bid():
    m = Market()
    seller = make_player(1, "Farmer")
    buyer = make_player(2, "Banker", dollops=200.0)
    seller.receive_resources(ResourceType.FOOD, 5)

    bid = m.post_bid(buyer, ResourceType.FOOD, 12.5, 3)
    offer = m.post_offer(seller, ResourceType.FOOD, 12.5, 5)

    assert bid.remaining == 0
    assert offer.remaining == 2
    assert buyer.inventory.get(ResourceType.FOOD) == 3
    assert buyer.dollops == 162.5
    assert seller.dollops == 237.5


def test_bid_partially_fills_when_quantity_exceeds_offer():
    """Partial fill: bid for 3 against offer of 2 → fills 2, leaves 1 resting."""
    m = Market()
    seller = make_player(1, "Farmer")
    buyer = make_player(2, "Banker", dollops=200.0)
    seller.receive_resources(ResourceType.FOOD, 2)

    offer = m.post_offer(seller, ResourceType.FOOD, 12.5, 2)
    bid = m.post_bid(buyer, ResourceType.FOOD, 12.5, 3)

    assert bid.remaining == 1
    assert offer.remaining == 0
    assert buyer.inventory.get(ResourceType.FOOD) == 2
    assert buyer.dollops == 175.0           # 200 − 2 × 12.5
    assert seller.dollops == 225.0          # 200 + 2 × 12.5


def test_new_bid_crosses_lower_resting_ask_and_trades_at_ask_price():
    """Resting (older) order sets price → buyer bidding 12 against ask 8 pays 8."""
    m = Market()
    seller = make_player(1, "Farmer")
    buyer = make_player(2, "Banker", dollops=200.0)
    seller.receive_resources(ResourceType.FOOD, 5)

    offer = m.post_offer(seller, ResourceType.FOOD, 8.0, 5)
    bid = m.post_bid(buyer, ResourceType.FOOD, 12.0, 3)

    assert bid.remaining == 0
    assert offer.remaining == 2
    assert buyer.inventory.get(ResourceType.FOOD) == 3
    assert buyer.dollops == 176.0           # 200 − 3 × 8 (paid ask price)
    assert seller.dollops == 224.0


def test_new_ask_crosses_higher_resting_bid_and_trades_at_bid_price():
    """Resting bid sets price → seller asking 8 against resting bid 12 receives 12."""
    m = Market()
    seller = make_player(1, "Farmer")
    buyer = make_player(2, "Banker", dollops=200.0)
    seller.receive_resources(ResourceType.FOOD, 5)

    bid = m.post_bid(buyer, ResourceType.FOOD, 12.0, 3)
    offer = m.post_offer(seller, ResourceType.FOOD, 8.0, 5)

    assert bid.remaining == 0
    assert offer.remaining == 2
    assert buyer.inventory.get(ResourceType.FOOD) == 3
    assert buyer.dollops == 164.0           # 200 − 3 × 12 (paid resting bid)
    assert seller.dollops == 236.0


def test_bid_does_not_cross_more_expensive_resting_asks():
    """Bid below all asks: no trades, both books retain their orders."""
    m = Market()
    seller = make_player(1, "Farmer")
    buyer = make_player(2, "Banker", dollops=200.0)
    seller.receive_resources(ResourceType.FOOD, 5)

    offer = m.post_offer(seller, ResourceType.FOOD, 15.0, 5)
    bid = m.post_bid(buyer, ResourceType.FOOD, 10.0, 3)

    assert bid.remaining == 3
    assert offer.remaining == 5
    assert buyer.inventory.get(ResourceType.FOOD) == 0
    assert buyer.dollops == 200.0
    assert seller.dollops == 200.0


def test_bid_walks_multiple_resting_asks_for_partial_fills():
    """Bid 5 @ 10 sweeps asks at 8 (qty 2) + 9 (qty 2) + 10 (qty 2) = 5 filled
    across three trades at the respective ask prices."""
    m = Market()
    s_a = make_player(1, "Farmer", dollops=100.0)
    s_b = make_player(2, "Farmer", dollops=100.0)
    s_c = make_player(3, "Farmer", dollops=100.0)
    buyer = make_player(4, "Banker", dollops=200.0)
    s_a.receive_resources(ResourceType.FOOD, 2)
    s_b.receive_resources(ResourceType.FOOD, 2)
    s_c.receive_resources(ResourceType.FOOD, 2)

    o1 = m.post_offer(s_a, ResourceType.FOOD, 8.0, 2)
    o2 = m.post_offer(s_b, ResourceType.FOOD, 9.0, 2)
    o3 = m.post_offer(s_c, ResourceType.FOOD, 10.0, 2)
    bid = m.post_bid(buyer, ResourceType.FOOD, 10.0, 5)

    assert bid.remaining == 0
    assert o1.remaining == 0
    assert o2.remaining == 0
    assert o3.remaining == 1                # one unit left on the costliest
    # Buyer paid 2*8 + 2*9 + 1*10 = 16 + 18 + 10 = 44.
    assert buyer.inventory.get(ResourceType.FOOD) == 5
    assert buyer.dollops == 156.0           # 200 − 44
    assert s_a.dollops == 116.0             # 100 + 16
    assert s_b.dollops == 118.0             # 100 + 18
    assert s_c.dollops == 110.0             # 100 + 10


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


# ---------------------------------------------------------------------------
# Cumulative orders — same (player, resource, price, season) merges
# ---------------------------------------------------------------------------

def test_same_seller_same_price_offers_accumulate_into_one_book_entry():
    m = Market()
    seller = make_player(1, "Farmer")
    seller.receive_resources(ResourceType.FOOD, 7)

    a = m.post_offer(seller, ResourceType.FOOD, 12.5, 3)
    b = m.post_offer(seller, ResourceType.FOOD, 12.5, 4)

    # Same logical resting offer — single entry, cumulative quantity.
    assert a is b
    assert a.remaining == 7
    assert a.quantity == 7
    assert len([o for o in m._offers if o.remaining > 0]) == 1


def test_same_buyer_same_price_bids_accumulate_into_one_book_entry():
    m = Market()
    buyer = make_player(1, "Banker", dollops=200.0)

    a = m.post_bid(buyer, ResourceType.FOOD, 10.0, 3)
    b = m.post_bid(buyer, ResourceType.FOOD, 10.0, 2)

    assert a is b
    assert a.remaining == 5
    assert a.quantity == 5
    assert len([x for x in m._bids if x.remaining > 0]) == 1


def test_different_prices_do_not_accumulate():
    m = Market()
    seller = make_player(1, "Farmer")
    seller.receive_resources(ResourceType.FOOD, 6)
    a = m.post_offer(seller, ResourceType.FOOD, 10.0, 3)
    b = m.post_offer(seller, ResourceType.FOOD, 11.0, 3)
    assert a is not b
    assert len([o for o in m._offers if o.remaining > 0]) == 2


def test_different_sellers_do_not_accumulate():
    m = Market()
    s1 = make_player(1, "Farmer")
    s2 = make_player(2, "Farmer", dollops=100.0)
    s1.receive_resources(ResourceType.FOOD, 3)
    s2.receive_resources(ResourceType.FOOD, 3)
    a = m.post_offer(s1, ResourceType.FOOD, 12.5, 3)
    b = m.post_offer(s2, ResourceType.FOOD, 12.5, 3)
    assert a is not b
    assert len([o for o in m._offers if o.remaining > 0]) == 2


def test_topping_up_a_resting_bid_immediately_settles_against_existing_ask():
    """First bid at 8 doesn't cross a resting 10 ask. Topping up the same
    bid to 10 (per the new cumulative rule, by posting a second 10-price
    bid) should still leave them as distinct entries (different prices).
    But topping up the SAME-PRICE bid past a price-update isn't supported
    here — separate orders by design. This test guards against accidental
    cross-price merging."""
    m = Market()
    seller = make_player(1, "Farmer")
    buyer = make_player(2, "Banker", dollops=200.0)
    seller.receive_resources(ResourceType.FOOD, 5)
    m.post_offer(seller, ResourceType.FOOD, 10.0, 5)
    b1 = m.post_bid(buyer, ResourceType.FOOD, 8.0, 2)    # doesn't cross
    b2 = m.post_bid(buyer, ResourceType.FOOD, 10.0, 2)   # crosses immediately
    assert b1 is not b2
    assert b1.remaining == 2
    assert b2.remaining == 0   # filled against resting ask at ask price
