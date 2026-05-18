from island_traders.engine.ai import AIStrategy
from island_traders.engine.events import EventResult
from island_traders.engine.production import ProductionEngine
from island_traders.engine.trading import TradingEngine
from island_traders.models.deal import DealLedger
from island_traders.models.market import Market
from island_traders.models.player import Player
from island_traders.models.resource import ResourceType
from island_traders.models.role import ROLES


def make_player(pid, name, role_names, dollops=300.0, is_human=False):
    return Player(
        player_id=pid,
        name=name,
        roles=[ROLES[r] for r in role_names],
        dollops=dollops,
        is_human=is_human,
    )


def test_banker_ai_does_not_auto_charge_humans_or_itself_for_insurance():
    ai = AIStrategy()
    banker = make_player(1, "Banker AI", ["Banker", "Manufacturer"])
    human = make_player(2, "Human", ["Farmer"], is_human=True)
    miner_ai = make_player(3, "Miner AI", ["Miner"])

    actions = ai.take_turn(
        banker,
        Market(),
        [banker, human, miner_ai],
        ProductionEngine(),
        TradingEngine(Market(), DealLedger()),
        EventResult("Normal"),
        "Spring",
        0,
        0,
    )

    assert human.insurance_policies == []
    assert banker.insurance_policies == []
    assert any("Miner AI" in action and "insurance" in action for action in actions)


def test_ai_keeps_required_input_reserve_when_listing_outputs():
    ai = AIStrategy()
    market = Market()
    miner = make_player(1, "Miner AI", ["Miner"])
    miner.receive_resources(ResourceType.OIL, 4)
    miner.receive_resources(ResourceType.FREIGHT, 1)
    miner.receive_resources(ResourceType.MINING_EQUIPMENT, 1)

    ai.take_turn(
        miner,
        market,
        [miner],
        ProductionEngine(),
        TradingEngine(market, DealLedger()),
        EventResult("Normal"),
        "Spring",
        0,
        0,
    )

    assert miner.inventory.get(ResourceType.OIL) >= 1
    summary = market.market_summary()[ResourceType.OIL.value]
    assert summary["ask_quantity"] == 82


def test_ai_produces_multiple_runs_when_inputs_available():
    ai = AIStrategy()
    market = Market()
    miner = make_player(1, "Miner AI", ["Miner"])
    miner.receive_resources(ResourceType.OIL, 5)
    miner.receive_resources(ResourceType.FREIGHT, 2)
    miner.receive_resources(ResourceType.MINING_EQUIPMENT, 2)

    actions = ai.take_turn(
        miner,
        market,
        [miner],
        ProductionEngine(),
        TradingEngine(market, DealLedger()),
        EventResult("Normal"),
        "Spring",
        0,
        0,
    )

    assert any(
        "160x Ore" in action and "80x Metal" in action and "160x Oil" in action
        for action in actions
    )
    summary = market.market_summary()
    assert summary[ResourceType.ORE.value]["ask_quantity"] == 160
    assert summary[ResourceType.METAL.value]["ask_quantity"] == 80
    assert summary[ResourceType.OIL.value]["ask_quantity"] == 162


def test_ai_places_bid_for_missing_required_inputs():
    ai = AIStrategy()
    market = Market()
    farmer = make_player(1, "Farmer AI", ["Farmer"])
    farmer.receive_resources(ResourceType.OIL, 2)

    ai.take_turn(
        farmer,
        market,
        [farmer],
        ProductionEngine(),
        TradingEngine(market, DealLedger()),
        EventResult("Normal"),
        "Spring",
        0,
        0,
    )

    bids = market.available_bids(ResourceType.FARM_MACHINERY)
    assert bids
    assert bids[0].remaining >= 1


def test_transporter_ai_lists_passenger_seats_after_production():
    ai = AIStrategy()
    market = Market()
    transporter = make_player(1, "Transporter AI", ["Transporter"])
    transporter.receive_resources(ResourceType.OIL, 4)
    transporter.receive_resources(ResourceType.FOOD, 2)

    ai.take_turn(
        transporter,
        market,
        [transporter],
        ProductionEngine(),
        TradingEngine(market, DealLedger()),
        EventResult("Normal"),
        "Spring",
        0,
        0,
    )

    offers = market.available_offers(ResourceType.PASSENGER_SEATS)
    assert offers
    assert offers[0].remaining > 0


def test_ai_accepts_profitable_deal_and_rejects_unprofitable_one():
    ai = AIStrategy()
    market = Market()
    ledger = DealLedger()
    trading = TradingEngine(market, ledger)
    miner = make_player(1, "Miner AI", ["Miner"])
    educator = make_player(2, "Educator AI", ["Educator"])
    miner.receive_resources(ResourceType.ORE, 3)
    educator.receive_resources(ResourceType.EXPERTISE, 3)

    profitable = trading.propose_deal(
        miner, educator, ResourceType.ORE, 2, ResourceType.EXPERTISE, 1, 20.0
    )
    unprofitable = trading.propose_deal(
        miner, educator, ResourceType.ORE, 1, ResourceType.EXPERTISE, 2, 0.0
    )

    ai.take_turn(
        educator,
        market,
        [miner, educator],
        ProductionEngine(),
        trading,
        EventResult("Normal"),
        "Spring",
        0,
        0,
    )

    assert profitable.status.value == "accepted"
    assert unprofitable.status.value == "rejected"
