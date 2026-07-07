import pytest

from island_traders.engine.trading import TradingEngine
from island_traders.models.deal import DealLedger
from island_traders.models.market import Market
from island_traders.models.player import Player
from island_traders.models.resource import ResourceType
from island_traders.models.role import ROLES


def _player(pid: int, role: str, dollops: float = 200.0) -> Player:
    return Player(pid, role, [ROLES[role]], dollops, is_human=False)


def _snapshot(players: list[Player], market: Market):
    return {
        "players": {
            p.player_id: {
                "cash": round(p.dollops, 2),
                "inventory": {
                    r.value: p.inventory.get(r)
                    for r in ResourceType
                    if p.inventory.get(r)
                },
            }
            for p in players
        },
        "offers": [
            (o.seller_id, o.resource.value, o.price_per_unit, o.remaining)
            for o in market.available_offers(ResourceType.OIL)
            + market.available_offers(ResourceType.FOOD)
        ],
        "bids": [
            (b.buyer_id, b.resource.value, b.price_per_unit, b.remaining)
            for b in market.available_bids(ResourceType.OIL)
            + market.available_bids(ResourceType.FOOD)
        ],
    }


def test_execute_order_list_mixed_rows_continue_after_rejection():
    market = Market()
    engine = TradingEngine(market, DealLedger())
    trader = _player(1, "Farmer", dollops=100.0)
    seller = _player(2, "Miner", dollops=0.0)
    buyer = _player(3, "Banker", dollops=200.0)
    seller.receive_resources(ResourceType.OIL, 3)
    trader.receive_resources(ResourceType.FOOD, 2)
    market.post_offer(seller, ResourceType.OIL, 10.0, 3)
    market.post_bid(buyer, ResourceType.FOOD, 15.0, 2)

    results = engine.execute_order_list(
        trader,
        [
            {"side": "buy", "resource": "Oil", "quantity": 2},
            {"side": "sell", "resource": "Food", "quantity": 1},
            {"side": "sell", "resource": "Oil", "quantity": 99},
        ],
        [trader, seller, buyer],
    )

    assert results[0] == {
        "index": 0,
        "side": "buy",
        "resource": "Oil",
        "status": "filled",
        "quantity": 2,
        "unit_price": 10.0,
        "total": -20.0,
    }
    assert results[1]["status"] == "filled"
    assert results[1]["total"] == 15.0
    assert results[2]["status"] == "rejected"
    assert trader.inventory.get(ResourceType.OIL) == 2
    assert trader.inventory.get(ResourceType.FOOD) == 1
    assert trader.dollops == pytest.approx(95.0)


def test_execute_order_list_limit_buy_partially_fills_and_rests():
    market = Market()
    engine = TradingEngine(market, DealLedger())
    buyer = _player(1, "Farmer", dollops=100.0)
    seller = _player(2, "Miner", dollops=0.0)
    seller.receive_resources(ResourceType.OIL, 2)
    market.post_offer(seller, ResourceType.OIL, 10.0, 2)

    results = engine.execute_order_list(
        buyer,
        [{"side": "buy", "resource": "Oil", "quantity": 5, "limit_price": 12.0}],
        [buyer, seller],
    )

    assert results[0]["status"] == "partial"
    assert results[0]["quantity"] == 2
    assert results[0]["total"] == -20.0
    assert results[0]["reason"] == "resting bid for 3"
    assert market.best_bid(ResourceType.OIL).remaining == 3


def test_execute_order_list_matches_sequential_market_primitives():
    def setup():
        market = Market()
        trader = _player(1, "Farmer", dollops=100.0)
        seller = _player(2, "Miner", dollops=0.0)
        buyer = _player(3, "Banker", dollops=200.0)
        seller.receive_resources(ResourceType.OIL, 3)
        trader.receive_resources(ResourceType.FOOD, 2)
        market.post_offer(seller, ResourceType.OIL, 10.0, 3)
        market.post_bid(buyer, ResourceType.FOOD, 15.0, 2)
        return market, trader, seller, buyer

    batch_market, batch_trader, batch_seller, batch_buyer = setup()
    TradingEngine(batch_market, DealLedger()).execute_order_list(
        batch_trader,
        [
            {"side": "buy", "resource": "Oil", "quantity": 2},
            {"side": "sell", "resource": "Food", "quantity": 1},
            {"side": "buy", "resource": "Oil", "quantity": 2, "limit_price": 12.0},
            {"side": "sell", "resource": "Food", "quantity": 1, "limit_price": 20.0},
        ],
        [batch_trader, batch_seller, batch_buyer],
    )

    seq_market, seq_trader, seq_seller, seq_buyer = setup()
    seq_market.buy_from_offers(seq_trader, ResourceType.OIL, 2)
    seq_market.sell_to_bids(seq_trader, ResourceType.FOOD, 1, [seq_trader, seq_seller, seq_buyer])
    seq_market.post_bid(seq_trader, ResourceType.OIL, 12.0, 2)
    seq_market.post_offer(seq_trader, ResourceType.FOOD, 20.0, 1)

    assert _snapshot([batch_trader, batch_seller, batch_buyer], batch_market) == _snapshot(
        [seq_trader, seq_seller, seq_buyer], seq_market
    )


def test_execute_order_list_layers_resting_orders_when_replace_false():
    """Blotter capture (#211): replace:false stacks orders instead of
    superseding — the layered-strategy the Trade Blotter exposes."""
    market = Market()
    engine = TradingEngine(market, DealLedger())
    buyer = _player(1, "Banker", dollops=500.0)

    engine.execute_order_list(
        buyer,
        [
            {"side": "buy", "resource": "Oil", "quantity": 2,
             "limit_price": 10.0, "replace": False},
            {"side": "buy", "resource": "Oil", "quantity": 3,
             "limit_price": 9.0, "replace": False},
        ],
        [buyer],
    )

    live = market.available_bids(ResourceType.OIL)
    assert sorted(b.remaining for b in live) == [2, 3]


def test_execute_order_list_supersedes_resting_orders_by_default():
    """Omitting replace keeps the historical supersede behaviour so existing
    callers (AI turn handlers, older clients) are unchanged."""
    market = Market()
    engine = TradingEngine(market, DealLedger())
    buyer = _player(1, "Banker", dollops=500.0)

    engine.execute_order_list(
        buyer,
        [
            {"side": "buy", "resource": "Oil", "quantity": 2, "limit_price": 10.0},
            {"side": "buy", "resource": "Oil", "quantity": 3, "limit_price": 9.0},
        ],
        [buyer],
    )

    live = market.available_bids(ResourceType.OIL)
    assert [b.remaining for b in live] == [3]
