from island_traders.engine.ai import AIStrategy
from island_traders.engine.events import EventResult
from island_traders.engine.production import ProductionEngine
from island_traders.engine.trading import TradingEngine
from island_traders.models.deal import DealLedger
from island_traders.models.loan import LoanLedger, LoanStatus
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
    assert summary["ask_quantity"] == 42


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
        "80x Ore" in action and "40x Metal" in action and "80x Oil" in action
        for action in actions
    )
    summary = market.market_summary()
    assert summary[ResourceType.ORE.value]["ask_quantity"] == 80
    assert summary[ResourceType.METAL.value]["ask_quantity"] == 40
    assert summary[ResourceType.OIL.value]["ask_quantity"] == 82


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
    educator = make_player(2, "Educator AI", ["Educator"], dollops=500.0)
    transporter.receive_resources(ResourceType.OIL, 4)
    transporter.receive_resources(ResourceType.FOOD, 2)
    market.post_bid(educator, ResourceType.PASSENGER_SEATS, 18.0, 2)

    ai.take_turn(
        transporter,
        market,
        [transporter, educator],
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


def test_ai_banker_offers_loan_to_capital_short_ai_borrower():
    ai = AIStrategy()
    market = Market()
    loan_ledger = LoanLedger()
    banker = make_player(1, "Banker AI", ["Banker"], dollops=100.0)
    farmer = make_player(2, "Farmer AI", ["Farmer"], dollops=0.0)

    actions = ai.take_turn(
        banker,
        market,
        [banker, farmer],
        ProductionEngine(),
        TradingEngine(market, DealLedger()),
        EventResult("Normal"),
        "Spring",
        0,
        0,
        loan_ledger,
    )

    farmer_loans = [
        loan for loan in loan_ledger.active_loans_for(farmer.player_id)
        if loan.borrower_id == farmer.player_id
    ]
    assert farmer_loans
    assert any("issued Loan" in action and "Farmer AI" in action for action in actions)


def test_ai_banker_does_not_offer_loan_when_reserve_short():
    ai = AIStrategy()
    market = Market()
    loan_ledger = LoanLedger()
    banker = make_player(1, "Banker AI", ["Banker"], dollops=20.0)
    farmer = make_player(2, "Farmer AI", ["Farmer"], dollops=0.0)

    ai.take_turn(
        banker,
        market,
        [banker, farmer],
        ProductionEngine(),
        TradingEngine(market, DealLedger()),
        EventResult("Normal"),
        "Spring",
        0,
        0,
        loan_ledger,
    )

    farmer_loans = [
        loan for loan in loan_ledger.active_loans_for(farmer.player_id)
        if loan.borrower_id == farmer.player_id
    ]
    assert farmer_loans == []


def test_ai_borrower_accepts_loan_when_capital_short():
    ai = AIStrategy()
    market = Market()
    loan_ledger = LoanLedger()
    banker = make_player(1, "Banker AI", ["Banker"], dollops=100.0)
    farmer = make_player(2, "Farmer AI", ["Farmer"], dollops=0.0)

    actions = ai.take_turn(
        farmer,
        market,
        [banker, farmer],
        ProductionEngine(),
        TradingEngine(market, DealLedger()),
        EventResult("Normal"),
        "Spring",
        0,
        0,
        loan_ledger,
    )

    farmer_loans = [
        loan for loan in loan_ledger.active_loans_for(farmer.player_id)
        if loan.borrower_id == farmer.player_id
    ]
    assert farmer_loans
    assert farmer.dollops > 0
    assert any("issued Loan" in action and "Farmer AI" in action for action in actions)


def test_ai_rollover_loan_when_cannot_repay_at_maturity():
    ai = AIStrategy()
    market = Market()
    loan_ledger = LoanLedger()
    banker = make_player(1, "Banker AI", ["Banker"], dollops=300.0)
    farmer = make_player(2, "Farmer AI", ["Farmer"], dollops=10.0)
    old = loan_ledger.create_loan(
        borrower_id=farmer.player_id,
        lender_id=banker.player_id,
        principal=100.0,
        interest_rate=0.10,
        issued_year=0,
        issued_season=0,
        term_years=1,
    )

    actions = ai.take_turn(
        farmer,
        market,
        [banker, farmer],
        ProductionEngine(),
        TradingEngine(market, DealLedger()),
        EventResult("Normal"),
        "Winter",
        0,
        3,
        loan_ledger,
    )

    rolled = [
        loan for loan in loan_ledger.all_loans()
        if loan.rolled_over_from_loan_id == old.loan_id
    ]
    assert old.status == LoanStatus.ROLLED_OVER
    assert rolled
    assert any("rolled over Loan" in action for action in actions)


def test_ai_invests_in_unclaimed_catalogue_item():
    ai = AIStrategy()
    market = Market()
    farmer = make_player(1, "Farmer AI", ["Farmer"], dollops=1500.0)

    actions = ai.take_turn(
        farmer,
        market,
        [farmer],
        ProductionEngine(),
        TradingEngine(market, DealLedger()),
        EventResult("Normal"),
        "Spring",
        0,
        0,
        LoanLedger(),
    )

    assert farmer.capital_inventory
    assert "farmer.storage_building" in farmer.capital_inventory
    assert any("invested" in action for action in actions)


def test_manufacturer_ai_buys_freight_surcharge_before_producing():
    ai = AIStrategy()
    market = Market()
    transporter = make_player(1, "Transporter AI", ["Transporter"], dollops=300.0)
    manufacturer = make_player(2, "Manufacturer AI", ["Manufacturer"], dollops=500.0)
    transporter.receive_resources(ResourceType.FREIGHT, 10)
    manufacturer.receive_resources(ResourceType.METAL, 4)
    manufacturer.receive_resources(ResourceType.OIL, 2)
    market.post_offer(transporter, ResourceType.FREIGHT, 12.0, 10)
    market.post_bid(transporter, ResourceType.LABORATORY_EQUIPMENT, 45.0, 3)

    actions = ai.take_turn(
        manufacturer,
        market,
        [transporter, manufacturer],
        ProductionEngine(),
        TradingEngine(market, DealLedger()),
        EventResult("Normal"),
        "Spring",
        0,
        0,
        LoanLedger(),
    )

    assert any("bought" in action and "Freight" in action for action in actions)
    assert any("produced" in action for action in actions)


def test_manufacturer_ai_prefers_line_with_visible_bid():
    ai = AIStrategy()
    market = Market()
    educator = make_player(1, "Educator AI", ["Educator"], dollops=1000.0)
    manufacturer = make_player(2, "Manufacturer AI", ["Manufacturer"], dollops=1000.0)
    transporter = make_player(3, "Transporter AI", ["Transporter"], dollops=300.0)
    transporter.receive_resources(ResourceType.FREIGHT, 10)
    manufacturer.receive_resources(ResourceType.METAL, 4)
    manufacturer.receive_resources(ResourceType.OIL, 2)
    market.post_offer(transporter, ResourceType.FREIGHT, 12.0, 10)
    market.post_bid(educator, ResourceType.LABORATORY_EQUIPMENT, 40.0, 10)

    actions = ai.take_turn(
        manufacturer,
        market,
        [educator, manufacturer, transporter],
        ProductionEngine(),
        TradingEngine(market, DealLedger()),
        EventResult("Normal"),
        "Spring",
        0,
        0,
        LoanLedger(),
    )

    assert any("Laboratory Equipment" in action for action in actions)
    assert educator.inventory.get(ResourceType.LABORATORY_EQUIPMENT) > 0
