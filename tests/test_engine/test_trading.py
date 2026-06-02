import pytest
from island_traders.engine.trading import TradingEngine, InvalidDealError, StaleResourceError
from island_traders.models.market import Market, InsufficientSupplyError
from island_traders.models.deal import DealLedger, DealStatus
from island_traders.models.resource import ResourceType
from island_traders.models.role import ROLES
from island_traders.models.player import Player


def make_player(pid, role_name, gold=200.0):
    return Player(pid, f"P{pid}", [ROLES[role_name]], gold, is_human=False)


@pytest.fixture
def engine(base_market, ledger):
    return TradingEngine(base_market, ledger)


def test_market_buy_transfers_resources(engine, base_market, farmer, banker):
    base_market.post_supply(ResourceType.FOOD, 5)
    paid = engine.market_buy(banker, ResourceType.FOOD, 3)
    assert banker.inventory.get(ResourceType.FOOD) == 3
    assert banker.dollops == 100.0 - paid


def test_market_sell_adds_supply(engine, base_market, farmer):
    farmer.receive_resources(ResourceType.FOOD, 5)
    engine.market_sell(farmer, ResourceType.FOOD, 5)
    assert base_market.supply.get(ResourceType.FOOD, 0) == 5


def test_get_quote_no_state_change(engine, base_market):
    q1 = engine.get_quote(ResourceType.FOOD, 3)
    q2 = engine.get_quote(ResourceType.FOOD, 3)
    assert q1 == q2
    assert base_market.supply.get(ResourceType.FOOD, 0) == 0


def test_propose_deal_creates_pending(engine, farmer, banker):
    farmer.receive_resources(ResourceType.FOOD, 3)
    deal = engine.propose_deal(farmer, banker, ResourceType.FOOD, 2, ResourceType.REAGENTS, 1)
    assert deal.status == DealStatus.PENDING
    assert len(engine.ledger.deals) == 1


def test_propose_deal_insufficient_offer_raises(engine, farmer, banker):
    with pytest.raises(InvalidDealError):
        engine.propose_deal(farmer, banker, ResourceType.FOOD, 10, ResourceType.REAGENTS, 1)


def test_propose_empty_deal_raises(engine, farmer, banker):
    with pytest.raises(InvalidDealError):
        engine.propose_deal(farmer, banker, None, 0, None, 0)


def test_accept_deal_transfers_atomically(engine, farmer, banker):
    farmer.receive_resources(ResourceType.FOOD, 3)
    banker.receive_resources(ResourceType.REAGENTS, 2)
    deal = engine.propose_deal(farmer, banker, ResourceType.FOOD, 3, ResourceType.REAGENTS, 2)
    engine.accept_deal(deal, acceptor=banker, proposer=farmer)
    assert deal.status == DealStatus.ACCEPTED
    assert farmer.inventory.get(ResourceType.FOOD) == 0
    assert farmer.inventory.get(ResourceType.REAGENTS) == 2
    assert banker.inventory.get(ResourceType.REAGENTS) == 0
    assert banker.inventory.get(ResourceType.FOOD) == 3


def test_accept_deal_stale_resource_raises(engine, farmer, banker):
    farmer.receive_resources(ResourceType.FOOD, 3)
    banker.receive_resources(ResourceType.REAGENTS, 2)
    deal = engine.propose_deal(farmer, banker, ResourceType.FOOD, 3, ResourceType.REAGENTS, 2)
    # Farmer sells food in the meantime
    farmer.give_resources(ResourceType.FOOD, 3)
    with pytest.raises(StaleResourceError):
        engine.accept_deal(deal, acceptor=banker, proposer=farmer)


def test_reject_deal_no_transfer(engine, farmer, banker):
    farmer.receive_resources(ResourceType.FOOD, 3)
    deal = engine.propose_deal(farmer, banker, ResourceType.FOOD, 2, ResourceType.REAGENTS, 1)
    engine.reject_deal(deal)
    assert deal.status == DealStatus.REJECTED
    assert farmer.inventory.get(ResourceType.FOOD) == 3


def test_gold_sweetener_deal(engine, farmer, banker):
    farmer.receive_resources(ResourceType.FOOD, 2)
    deal = engine.propose_deal(
        farmer, banker,
        offer_resource=ResourceType.FOOD, offer_qty=2,
        request_resource=None, request_qty=0,
        gold_sweetener=0.0,
    )
    # Banker pays no gold; farmer offers food for nothing (gift/test)
    engine.accept_deal(deal, acceptor=banker, proposer=farmer)
    assert banker.inventory.get(ResourceType.FOOD) == 2
