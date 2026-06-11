import pytest
from island_traders.models.market import Market, InsufficientSupplyError
from island_traders.models.player import Player, InsufficientFundsError
from island_traders.models.resource import ResourceType
from island_traders.models.role import ROLES
from island_traders.constants import BASE_PRICES, MARKET_MAKER_DEPTH_PER_RESOURCE


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
    expected_paid = m.market_maker_ask(ResourceType.FOOD) * 3
    paid = m.execute_buy(buyer, ResourceType.FOOD, 3)
    assert paid == expected_paid
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
    m.post_supply(ResourceType.REAGENTS, 10)
    buyer = make_player(0, "Banker", dollops=1.0)
    with pytest.raises(InsufficientFundsError):
        m.execute_buy(buyer, ResourceType.REAGENTS, 5)


def test_execute_sell_increases_supply():
    m = Market()
    seller = make_player(0, "Farmer")
    seller.receive_resources(ResourceType.FOOD, 4)
    expected_received = m.market_maker_bid(ResourceType.FOOD) * 4
    starting_dollops = seller.dollops
    received = m.execute_sell(seller, ResourceType.FOOD, 4)
    assert received == expected_received
    assert seller.dollops == starting_dollops + received
    assert m.supply.get(ResourceType.FOOD, 0) == 4


def test_formula_market_buy_depth_is_finite_per_season():
    m = Market()
    m.post_supply(ResourceType.FOOD, MARKET_MAKER_DEPTH_PER_RESOURCE + 1)
    buyer = make_player(0, "Banker", dollops=5000.0)

    m.execute_buy(buyer, ResourceType.FOOD, MARKET_MAKER_DEPTH_PER_RESOURCE)

    assert m.market_maker_buy_depth(ResourceType.FOOD) == 0
    with pytest.raises(InsufficientSupplyError):
        m.execute_buy(buyer, ResourceType.FOOD, 1)


def test_formula_market_buy_does_not_consume_player_asks():
    m = Market()
    seller = make_player(1, "Farmer")
    buyer = make_player(2, "Banker")
    seller.receive_resources(ResourceType.FOOD, 5)
    offer = m.post_offer(seller, ResourceType.FOOD, 12.0, 5)

    with pytest.raises(InsufficientSupplyError):
        m.execute_buy(buyer, ResourceType.FOOD, 1)

    assert offer.remaining == 5
    assert buyer.inventory.get(ResourceType.FOOD) == 0
    assert seller.dollops == 200.0


def test_formula_market_sell_depth_is_finite_and_resets_with_season():
    m = Market()
    seller = make_player(0, "Farmer")
    seller.receive_resources(ResourceType.FOOD, MARKET_MAKER_DEPTH_PER_RESOURCE + 1)

    m.execute_sell(seller, ResourceType.FOOD, MARKET_MAKER_DEPTH_PER_RESOURCE)
    assert m.market_maker_sell_depth(ResourceType.FOOD) == 0

    with pytest.raises(InsufficientSupplyError):
        m.execute_sell(seller, ResourceType.FOOD, 1)
    assert seller.inventory.get(ResourceType.FOOD) == 1

    m.set_season(0, 1)
    m.execute_sell(seller, ResourceType.FOOD, 1)
    assert m.market_maker_sell_depth(ResourceType.FOOD) == (
        MARKET_MAKER_DEPTH_PER_RESOURCE - 1
    )


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
# New-order-overrides rule (a player can only have one standing order per
# resource — a new bid/ask cancels their prior bids AND asks on it).
# ---------------------------------------------------------------------------

def test_new_offer_cancels_prior_player_offer_on_same_resource():
    m = Market()
    seller = make_player(1, "Farmer")
    seller.receive_resources(ResourceType.FOOD, 10)

    a = m.post_offer(seller, ResourceType.FOOD, 10.0, 4)
    b = m.post_offer(seller, ResourceType.FOOD, 11.0, 3)

    # First ask is cancelled (refunded), only the new one is live.
    assert a.remaining == 0
    assert b.remaining == 3
    live = [o for o in m._offers if o.remaining > 0]
    assert live == [b]
    # Refund: seller had 10, gave 4 (qty in first offer), refunded 4 on
    # cancel, then gave 3 to the new offer → 10 − 4 + 4 − 3 = 7 left.
    assert seller.inventory.get(ResourceType.FOOD) == 7


def test_new_bid_cancels_prior_player_bid_on_same_resource():
    m = Market()
    buyer = make_player(1, "Banker", dollops=200.0)

    a = m.post_bid(buyer, ResourceType.FOOD, 10.0, 3)
    b = m.post_bid(buyer, ResourceType.FOOD, 12.0, 2)

    assert a.remaining == 0
    assert b.remaining == 2
    live = [x for x in m._bids if x.remaining > 0]
    assert live == [b]


def test_buy_from_offers_pays_the_resting_seller():
    m = Market()
    seller = make_player(1, "Farmer", dollops=50.0)
    buyer = make_player(2, "Banker", dollops=200.0)
    seller.receive_resources(ResourceType.FOOD, 4)
    m.post_offer(seller, ResourceType.FOOD, 10.0, 4)

    cost, bought = m.buy_from_offers(buyer, ResourceType.FOOD, 3)

    assert cost == 30.0
    assert bought == 3
    assert buyer.dollops == 170.0
    assert seller.dollops == 80.0


def test_new_bid_also_cancels_prior_player_offer_on_same_resource():
    """A player flipping sides on a resource has both their prior bid AND
    prior ask cancelled by a new order (asks refund resources)."""
    m = Market()
    player = make_player(1, "Farmer", dollops=200.0)
    player.receive_resources(ResourceType.FOOD, 5)

    # Player puts up an ask, then changes their mind and bids on the same
    # resource — the ask should be cancelled and 5 FOOD refunded.
    ask = m.post_offer(player, ResourceType.FOOD, 12.0, 5)
    bid = m.post_bid(player, ResourceType.FOOD, 8.0, 3)

    assert ask.remaining == 0
    assert bid.remaining == 3
    assert player.inventory.get(ResourceType.FOOD) == 5    # refunded


def test_new_offer_also_cancels_prior_player_bid_on_same_resource():
    m = Market()
    player = make_player(1, "Farmer", dollops=200.0)
    player.receive_resources(ResourceType.FOOD, 3)

    bid = m.post_bid(player, ResourceType.FOOD, 10.0, 4)
    ask = m.post_offer(player, ResourceType.FOOD, 14.0, 3)

    assert bid.remaining == 0
    assert ask.remaining == 3


def test_new_order_does_not_affect_other_players_or_other_resources():
    m = Market()
    a_seller = make_player(1, "Farmer")
    b_seller = make_player(2, "Farmer", dollops=100.0)
    a_seller.receive_resources(ResourceType.FOOD, 3)
    a_seller.receive_resources(ResourceType.FISH, 2)
    b_seller.receive_resources(ResourceType.FOOD, 3)

    a_food = m.post_offer(a_seller, ResourceType.FOOD, 12.0, 3)
    a_fish = m.post_offer(a_seller, ResourceType.FISH, 9.0, 2)
    b_food = m.post_offer(b_seller, ResourceType.FOOD, 12.0, 3)
    # A new ask from a_seller on FOOD should override only their FOOD ask
    # — not their FISH ask, and not b_seller's FOOD ask.
    a_seller.receive_resources(ResourceType.FOOD, 1)   # restock so we can re-post
    a_food2 = m.post_offer(a_seller, ResourceType.FOOD, 13.0, 1)

    assert a_food.remaining == 0
    assert a_fish.remaining == 2     # other resource, untouched
    assert b_food.remaining == 3     # other player, untouched
    assert a_food2.remaining == 1


def test_supply_and_demand_counters_decrement_on_cancelled_orders():
    m = Market()
    seller = make_player(1, "Farmer")
    buyer = make_player(2, "Banker", dollops=200.0)
    seller.receive_resources(ResourceType.FOOD, 5)

    m.post_offer(seller, ResourceType.FOOD, 15.0, 4)
    m.post_bid(buyer, ResourceType.FOOD, 8.0, 3)
    assert m.supply[ResourceType.FOOD] == 4
    assert m.demand[ResourceType.FOOD] == 3

    # New orders override their respective sides.
    m.post_offer(seller, ResourceType.FOOD, 15.0, 2)   # cancels first 4
    m.post_bid(buyer, ResourceType.FOOD, 8.0, 1)       # cancels first 3
    assert m.supply[ResourceType.FOOD] == 2
    assert m.demand[ResourceType.FOOD] == 1


def test_market_emits_and_drains_events():
    m = Market()
    seller = make_player(1, "Miner", dollops=200.0)
    buyer = make_player(2, "Manufacturer", dollops=500.0)
    seller.receive_resources(ResourceType.ORE, 10)

    m.post_offer(seller, ResourceType.ORE, price_per_unit=20.0, qty=5)
    m.post_bid(buyer, ResourceType.ORE, price_per_unit=18.0, qty=2)

    events = m.drain_events()
    kinds = [(e["resource"], e["side"], e["action"], e["actor"]) for e in events]
    assert ("Ore", "ask", "posted", seller.name) in kinds
    assert ("Ore", "bid", "posted", buyer.name) in kinds
    # draining clears the buffer
    assert m.drain_events() == []


def test_market_emits_fill_event_on_buy():
    m = Market()
    seller = make_player(1, "Miner", dollops=200.0)
    buyer = make_player(2, "Manufacturer", dollops=500.0)
    seller.receive_resources(ResourceType.ORE, 10)
    m.post_offer(seller, ResourceType.ORE, price_per_unit=20.0, qty=5)
    m.drain_events()  # clear the 'posted' event

    m.buy_from_offers(buyer, ResourceType.ORE, qty=3)
    fills = [e for e in m.drain_events() if e["action"] == "filled"]
    assert fills and fills[0]["resource"] == "Ore"
    assert fills[0]["side"] == "ask" and fills[0]["quantity"] == 3
    assert fills[0]["actor"] == buyer.name
