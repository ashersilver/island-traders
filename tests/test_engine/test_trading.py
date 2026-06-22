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


def test_formula_buy_consumes_buyer_freight_when_available(base_market, ledger):
    buyer = make_player(10, "Banker", gold=100.0)
    transporter = make_player(11, "Transporter", gold=20.0)
    buyer.receive_resources(ResourceType.FREIGHT, 1)
    base_market.post_supply(ResourceType.FOOD, 5)
    engine = TradingEngine(base_market, ledger, [buyer, transporter])

    paid = engine.market_buy(buyer, ResourceType.FOOD, 3, [buyer, transporter])

    assert buyer.inventory.get(ResourceType.FOOD) == 3
    assert buyer.inventory.get(ResourceType.FREIGHT) == 0
    assert buyer.dollops == pytest.approx(100.0 - paid)
    assert transporter.dollops == 20.0


def test_formula_buy_without_freight_pays_transporter_fee(base_market, ledger):
    buyer = make_player(10, "Banker", gold=100.0)
    transporter = make_player(11, "Transporter", gold=20.0)
    base_market.post_supply(ResourceType.FOOD, 5)
    engine = TradingEngine(base_market, ledger, [buyer, transporter])

    paid = engine.market_buy(buyer, ResourceType.FOOD, 3, [buyer, transporter])

    assert buyer.inventory.get(ResourceType.FOOD) == 3
    assert buyer.dollops == pytest.approx(100.0 - paid - 3.0)
    assert transporter.dollops == 23.0


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


def test_order_book_buy_pays_transporter_fee():
    market = Market()
    buyer = make_player(10, "Banker", gold=100.0)
    seller = make_player(11, "Farmer", gold=10.0)
    transporter = make_player(12, "Transporter", gold=5.0)
    seller.receive_resources(ResourceType.FOOD, 2)
    market.post_offer(seller, ResourceType.FOOD, 10.0, 2)
    engine = TradingEngine(market, DealLedger(), [buyer, seller, transporter])

    result = engine.execute_order_list(
        buyer,
        [{"side": "buy", "resource": "Food", "quantity": 2}],
        [buyer, seller, transporter],
    )[0]

    assert result["freight"] == {
        "mode": "fee",
        "units": 1,
        "fee": 2.0,
        "recipient_id": transporter.player_id,
    }
    assert buyer.dollops == pytest.approx(78.0)
    assert seller.dollops == pytest.approx(30.0)
    assert transporter.dollops == pytest.approx(7.0)


def test_freight_resource_trade_is_exempt(base_market, ledger):
    buyer = make_player(10, "Banker", gold=100.0)
    transporter = make_player(11, "Transporter", gold=20.0)
    base_market.post_supply(ResourceType.FREIGHT, 5)
    engine = TradingEngine(base_market, ledger, [buyer, transporter])

    paid = engine.market_buy(buyer, ResourceType.FREIGHT, 2, [buyer, transporter])

    assert buyer.inventory.get(ResourceType.FREIGHT) == 2
    assert buyer.dollops == pytest.approx(100.0 - paid)
    assert transporter.dollops == 20.0


def test_accept_deal_charges_inbound_freight_to_receiver(base_market, ledger):
    proposer = make_player(10, "Farmer", gold=100.0)
    acceptor = make_player(11, "Banker", gold=100.0)
    transporter = make_player(12, "Transporter", gold=5.0)
    proposer.receive_resources(ResourceType.FOOD, 3)
    engine = TradingEngine(base_market, ledger, [proposer, acceptor, transporter])

    deal = engine.propose_deal(proposer, acceptor, ResourceType.FOOD, 3, None, 0)
    engine.accept_deal(
        deal,
        acceptor=acceptor,
        proposer=proposer,
        players=[proposer, acceptor, transporter],
    )

    assert acceptor.inventory.get(ResourceType.FOOD) == 3
    assert acceptor.dollops == pytest.approx(97.0)
    assert transporter.dollops == pytest.approx(8.0)


def test_same_island_deal_and_no_transporter_do_not_charge_freight(base_market, ledger):
    proposer = make_player(10, "Farmer", gold=100.0)
    acceptor = make_player(11, "Farmer", gold=100.0)
    proposer.receive_resources(ResourceType.FOOD, 3)
    engine = TradingEngine(base_market, ledger, [proposer, acceptor])

    deal = engine.propose_deal(proposer, acceptor, ResourceType.FOOD, 3, None, 0)
    engine.accept_deal(deal, acceptor=acceptor, proposer=proposer, players=[proposer, acceptor])

    assert acceptor.inventory.get(ResourceType.FOOD) == 3
    assert acceptor.dollops == 100.0


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


def test_returned_deal_can_be_accepted_by_original_proposer(engine, farmer, banker):
    farmer.receive_resources(ResourceType.FOOD, 3)
    banker.receive_resources(ResourceType.REAGENTS, 2)
    deal = engine.propose_deal(
        farmer, banker, ResourceType.FOOD, 3, ResourceType.REAGENTS, 1
    )

    engine.return_deal(
        deal,
        responder_id=banker.player_id,
        offer_resource=ResourceType.FOOD,
        offer_qty=1,
        request_resource=ResourceType.REAGENTS,
        request_qty=2,
        gold_sweetener=5.0,
        message="One food for both Reagents.",
    )
    engine.accept_deal(deal, acceptor=banker, proposer=farmer)

    assert deal.status == DealStatus.ACCEPTED
    assert farmer.inventory.get(ResourceType.FOOD) == 2
    assert farmer.inventory.get(ResourceType.REAGENTS) == 2
    assert farmer.dollops == 95.0
    assert banker.inventory.get(ResourceType.FOOD) == 1
    assert banker.inventory.get(ResourceType.REAGENTS) == 0
    assert banker.dollops == 105.0


def test_accept_stale_returned_deal_raises_and_moves_nothing(engine, farmer, banker):
    farmer.receive_resources(ResourceType.FOOD, 2)
    banker.receive_resources(ResourceType.REAGENTS, 1)
    deal = engine.propose_deal(
        farmer, banker, ResourceType.FOOD, 1, ResourceType.REAGENTS, 1
    )
    engine.return_deal(
        deal,
        responder_id=banker.player_id,
        offer_resource=ResourceType.FOOD,
        offer_qty=1,
        request_resource=ResourceType.REAGENTS,
        request_qty=2,
    )

    with pytest.raises(StaleResourceError):
        engine.accept_deal(deal, acceptor=banker, proposer=farmer)

    assert deal.status == DealStatus.RETURNED
    assert farmer.inventory.get(ResourceType.FOOD) == 2
    assert farmer.inventory.get(ResourceType.REAGENTS) == 0
    assert banker.inventory.get(ResourceType.REAGENTS) == 1


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


def test_accept_deal_installs_equipment_for_producer(engine):
    manufacturer = Player(3, "Forge", [ROLES["Manufacturer"]], 100.0, is_human=False)
    farmer = Player(4, "Farm", [ROLES["Farmer"]], 200.0, is_human=False)
    manufacturer.receive_resources(ResourceType.FARM_MACHINERY, 1)

    deal = engine.propose_deal(
        manufacturer,
        farmer,
        ResourceType.FARM_MACHINERY,
        1,
        None,
        0,
        0.0,
    )
    engine.accept_deal(
        deal,
        acceptor=farmer,
        proposer=manufacturer,
        acquired_tick=7,
    )

    assert farmer.inventory.get(ResourceType.FARM_MACHINERY) == 0
    assert farmer.capital_count("farmer.tractor") == 1
    assert farmer.capital_acquired_ticks["farmer.tractor"] == [7]
