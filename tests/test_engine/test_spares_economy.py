from __future__ import annotations

from island_traders.constants import BASE_PRICES, MANUFACTURER_PRODUCT_LINES
from island_traders.engine.ai import AIStrategy
from island_traders.engine.events import EventResult
from island_traders.engine.production import ProductionEngine
from island_traders.engine.trading import TradingEngine
from island_traders.models.deal import DealLedger, DealStatus
from island_traders.models.market import Market
from island_traders.models.player import Player
from island_traders.models.resource import NON_TRADABLE_RESOURCES, ResourceType
from island_traders.models.role import ROLES


def _player(player_id: int, role_name: str, dollops: float = 500.0) -> Player:
    return Player(
        player_id,
        role_name,
        [ROLES[role_name]],
        dollops,
        is_human=False,
    )


def test_spares_is_priced_and_tradable():
    market = Market()

    assert ResourceType.SPARES not in NON_TRADABLE_RESOURCES
    assert BASE_PRICES[ResourceType.SPARES.value] == 12.0
    assert market.current_prices()[ResourceType.SPARES] == 12.0


def test_manufacturer_produces_spares_from_metal_and_oil():
    manufacturer = _player(1, "Manufacturer")
    manufacturer.receive_resources(ResourceType.METAL, 2)
    manufacturer.receive_resources(ResourceType.OIL, 1)

    produced = ProductionEngine().produce(
        manufacturer, EventResult("Normal"), "Spring", "Spares"
    )

    assert MANUFACTURER_PRODUCT_LINES["Spares"]["inputs"] == {"Metal": 2, "Oil": 1}
    assert produced == {ResourceType.SPARES: 4}
    assert manufacturer.inventory.get(ResourceType.METAL) == 0
    assert manufacturer.inventory.get(ResourceType.OIL) == 0
    assert manufacturer.inventory.get(ResourceType.SPARES) == 4


def test_market_offer_buy_round_trip_moves_spares():
    market = Market()
    seller = _player(1, "Manufacturer", dollops=100.0)
    buyer = _player(2, "Farmer", dollops=100.0)
    seller.receive_resources(ResourceType.SPARES, 2)

    offer = market.post_offer(seller, ResourceType.SPARES, 12.0, 2)
    paid, bought = market.buy_from_offers(buyer, ResourceType.SPARES, 1)

    assert offer.remaining == 1
    assert paid == 12.0
    assert bought == 1
    assert buyer.inventory.get(ResourceType.SPARES) == 1
    assert seller.dollops == 112.0


def test_deal_can_offer_and_request_spares():
    market = Market()
    ledger = DealLedger()
    engine = TradingEngine(market, ledger)
    proposer = _player(1, "Manufacturer")
    acceptor = _player(2, "Farmer")
    proposer.receive_resources(ResourceType.SPARES, 2)
    acceptor.receive_resources(ResourceType.FOOD, 3)

    deal = engine.propose_deal(
        proposer, acceptor, ResourceType.SPARES, 2, ResourceType.FOOD, 3
    )
    engine.accept_deal(deal, acceptor=acceptor, proposer=proposer, players=[proposer, acceptor])

    assert deal.status == DealStatus.ACCEPTED
    assert acceptor.inventory.get(ResourceType.SPARES) == 2
    assert proposer.inventory.get(ResourceType.FOOD) == 3


def test_ai_manufacturer_makes_spares_in_repair_emergency():
    # The override fires ONLY when own capital sits failed with zero kits on
    # hand — otherwise Spares competes in the normal product-line scoring
    # (the always-on version of this override tanked the Manufacturer's sim
    # win rate from 10.4% to 3.3% by chronically displacing better lines).
    market = Market()
    manufacturer = _player(1, "Manufacturer")
    manufacturer.add_capital("manufacturer.small_warehouse")  # spares storage
    manufacturer.add_capital("manufacturer.assembly_line")
    manufacturer.capital_units["manufacturer.assembly_line"][0].status = "failed"
    manufacturer.receive_resources(ResourceType.METAL, 2)
    manufacturer.receive_resources(ResourceType.OIL, 1)
    strategy = AIStrategy()

    chosen = strategy._choose_product_line(manufacturer, market, [])

    assert chosen == "Spares"


def test_ai_manufacturer_low_stock_alone_does_not_hijack_the_line_choice():
    market = Market()
    manufacturer = _player(1, "Manufacturer")
    manufacturer.add_capital("manufacturer.small_warehouse")
    # Inputs for several lines; nothing failed, no Spares bid on the market.
    manufacturer.receive_resources(ResourceType.METAL, 6)
    manufacturer.receive_resources(ResourceType.OIL, 4)
    strategy = AIStrategy()

    chosen = strategy._choose_product_line(manufacturer, market, [])

    assert chosen != "Spares"


def test_ai_with_capital_and_no_spares_buys_small_buffer():
    market = Market()
    manufacturer = _player(1, "Manufacturer")
    farmer = _player(2, "Farmer", dollops=100.0)
    farmer.add_capital("farmer.tractor")
    manufacturer.receive_resources(ResourceType.SPARES, 2)
    market.post_offer(manufacturer, ResourceType.SPARES, 12.0, 2)
    strategy = AIStrategy()
    trading = TradingEngine(market, DealLedger(), players=[manufacturer, farmer])

    actions = strategy.take_turn(
        farmer,
        market,
        [manufacturer],
        ProductionEngine(),
        trading,
        EventResult("Normal"),
        "Spring",
    )

    assert farmer.inventory.get(ResourceType.SPARES) == 2
    assert any("bought 2x Spares" in action for action in actions)
