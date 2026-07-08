"""Trade Blotter (#210): order layering vs supersede, and the fills ledger.

These lock in the two engine-level behaviours the blotter relies on:
  1. ``post_offer`` / ``post_bid`` layer alongside prior orders when
     ``replace=False`` and still supersede them (the historical default)
     when ``replace=True``.
  2. Every executed fill lands in the ledger and ``player_fills`` shapes it
     from each viewer's perspective (buy vs sell, counterparty name).
"""
from island_traders.models.market import Market
from island_traders.models.player import Player
from island_traders.models.resource import ResourceType
from island_traders.models.role import ROLES


def make_player(pid, role_name, dollops=200.0):
    return Player(pid, f"P{pid}", [ROLES[role_name]], dollops, is_human=False)


# ---------------------------------------------------------------- layering ---

def test_layer_offer_keeps_prior_offer():
    m = Market()
    seller = make_player(1, "Farmer")
    seller.receive_resources(ResourceType.FOOD, 10)

    a = m.post_offer(seller, ResourceType.FOOD, 10.0, 4)
    b = m.post_offer(seller, ResourceType.FOOD, 11.0, 3, replace=False)

    live = [o for o in m._offers if o.remaining > 0]
    assert a.remaining == 4
    assert b.remaining == 3
    assert live == [a, b]
    # Both asks escrowed their units: 10 − 4 − 3 = 3 left in inventory.
    assert seller.inventory.get(ResourceType.FOOD) == 3


def test_layer_bid_keeps_prior_bid():
    m = Market()
    buyer = make_player(1, "Banker", dollops=200.0)

    a = m.post_bid(buyer, ResourceType.FOOD, 10.0, 3)
    b = m.post_bid(buyer, ResourceType.FOOD, 12.0, 2, replace=False)

    live = [x for x in m._bids if x.remaining > 0]
    assert a.remaining == 3
    assert b.remaining == 2
    assert live == [a, b]


def test_layer_bid_does_not_cancel_prior_ask():
    """Layering lets an island hold a resting bid AND ask on one resource."""
    m = Market()
    player = make_player(1, "Farmer", dollops=200.0)
    player.receive_resources(ResourceType.FOOD, 5)

    ask = m.post_offer(player, ResourceType.FOOD, 14.0, 5)
    bid = m.post_bid(player, ResourceType.FOOD, 8.0, 3, replace=False)

    assert ask.remaining == 5   # not superseded
    assert bid.remaining == 3
    # No self-trade: the island's own bid must not cross its own ask.
    assert m.player_fills(1) == []


def test_replace_true_still_supersedes():
    m = Market()
    seller = make_player(1, "Farmer")
    seller.receive_resources(ResourceType.FOOD, 10)

    a = m.post_offer(seller, ResourceType.FOOD, 10.0, 4)
    b = m.post_offer(seller, ResourceType.FOOD, 11.0, 3, replace=True)

    assert a.remaining == 0
    assert [o for o in m._offers if o.remaining > 0] == [b]


# --------------------------------------------------------------- fills tape ---

def test_market_maker_buy_records_fill():
    m = Market()
    m.post_supply(ResourceType.FOOD, 10)
    buyer = make_player(1, "Banker")
    m.execute_buy(buyer, ResourceType.FOOD, 3)

    fills = m.player_fills(1)
    assert len(fills) == 1
    f = fills[0]
    assert f["side"] == "buy"
    assert f["resource"] == "Food"
    assert f["quantity"] == 3
    assert f["counterparty"] == "Market"


def test_market_maker_sell_records_fill():
    m = Market()
    seller = make_player(1, "Farmer")
    seller.receive_resources(ResourceType.FOOD, 5)
    m.execute_sell(seller, ResourceType.FOOD, 2)

    fills = m.player_fills(1)
    assert len(fills) == 1
    assert fills[0]["side"] == "sell"
    assert fills[0]["counterparty"] == "Market"
    assert fills[0]["quantity"] == 2


def test_crossing_orders_record_fill_for_both_sides():
    m = Market()
    seller = make_player(1, "Farmer")
    buyer = make_player(2, "Banker", dollops=200.0)
    seller.receive_resources(ResourceType.FOOD, 5)

    m.post_offer(seller, ResourceType.FOOD, 8.0, 5)
    m.post_bid(buyer, ResourceType.FOOD, 12.0, 3)  # crosses at ask price 8

    seller_fills = m.player_fills(1)
    buyer_fills = m.player_fills(2)
    assert len(seller_fills) == 1 and len(buyer_fills) == 1

    sf, bf = seller_fills[0], buyer_fills[0]
    assert sf["side"] == "sell" and sf["counterparty"] == "P2"
    assert bf["side"] == "buy" and bf["counterparty"] == "P1"
    assert sf["price_per_unit"] == 8.0 and bf["price_per_unit"] == 8.0
    assert sf["quantity"] == 3 and bf["quantity"] == 3


def test_buy_from_offers_records_fill():
    m = Market()
    seller = make_player(1, "Farmer", dollops=50.0)
    buyer = make_player(2, "Banker", dollops=200.0)
    seller.receive_resources(ResourceType.FOOD, 4)
    m.post_offer(seller, ResourceType.FOOD, 10.0, 4)

    m.buy_from_offers(buyer, ResourceType.FOOD, 3)

    assert m.player_fills(2)[0]["side"] == "buy"
    assert m.player_fills(1)[0]["side"] == "sell"
    assert m.player_fills(2)[0]["counterparty"] == "P1"


def test_sell_to_bids_records_fill():
    m = Market()
    seller = make_player(1, "Farmer")
    buyer = make_player(2, "Banker", dollops=200.0)
    seller.receive_resources(ResourceType.FOOD, 5)
    m.post_bid(buyer, ResourceType.FOOD, 11.0, 2)

    m.sell_to_bids(seller, ResourceType.FOOD, 2, [seller, buyer])

    assert m.player_fills(1)[0]["side"] == "sell"
    assert m.player_fills(2)[0]["side"] == "buy"
    assert m.player_fills(1)[0]["price_per_unit"] == 11.0


def test_buying_own_offer_records_no_self_fill():
    """A self-trade is not a real trade and must not enter the ledger."""
    m = Market()
    player = make_player(1, "Farmer", dollops=200.0)
    player.receive_resources(ResourceType.FOOD, 4)
    m.post_offer(player, ResourceType.FOOD, 10.0, 4)

    # buy_from_offers skips paying a self-offer; no fill should be recorded.
    m.buy_from_offers(player, ResourceType.FOOD, 3)
    assert m.player_fills(1) == []


def test_player_fills_recent_first_and_limit():
    m = Market()
    m.post_supply(ResourceType.FOOD, 100)
    buyer = make_player(1, "Banker", dollops=10_000.0)
    for _ in range(4):
        m.execute_buy(buyer, ResourceType.FOOD, 1)

    fills = m.player_fills(1, limit=2)
    assert len(fills) == 2
    # Most-recent first → descending fill_id.
    assert fills[0]["fill_id"] > fills[1]["fill_id"]


def test_other_players_fills_excluded():
    m = Market()
    m.post_supply(ResourceType.FOOD, 10)
    buyer = make_player(1, "Banker")
    m.execute_buy(buyer, ResourceType.FOOD, 2)

    assert m.player_fills(99) == []
