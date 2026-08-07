import pytest

from island_traders.engine.ai import AIStrategy
from island_traders.engine.events import EventResult
from island_traders.engine.production import ProductionEngine
from island_traders.engine.trading import TradingEngine
from island_traders.models.deal import DealLedger
from island_traders.models.loan import LoanLedger, LoanStatus
from island_traders.models.market import Market
from island_traders.models.player import Player
from island_traders.models.training import TrainingRegistry
from island_traders.models.equity import AUCTIONED_SHARES, CapTable
from island_traders.models.profession import Profession
from island_traders.models.resource import ResourceType
from island_traders.models.role import ROLES
from island_traders.engine.game import Game, GameConfig, PlayerSpec
from island_traders.simulation.runner import _SilentIO
from island_traders.constants import STARTING_DOLLOPS, WORKPLACE_RISK


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
    banker.workforce.add_workers(1, training_level=1, profession=Profession.ACTUARY.value)
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


def test_workplace_risk_retune_is_survivable_for_productive_roles():
    assert WORKPLACE_RISK["Miner"]["fatality_rate"] <= 0.025
    assert WORKPLACE_RISK["Miner"]["injury_rate"] <= 0.060
    assert WORKPLACE_RISK["Farmer"]["fatality_rate"] <= 0.012
    assert WORKPLACE_RISK["Manufacturer"]["fatality_rate"] <= 0.018
    assert WORKPLACE_RISK["Educator"]["fatality_rate"] > 0.0


def test_high_risk_ai_buys_workplace_insurance_when_solvent():
    ai = AIStrategy()
    market = Market()
    miner = make_player(1, "Miner AI", ["Miner"], dollops=500.0)
    banker = make_player(2, "Banker AI", ["Banker"], dollops=500.0)
    # #196: one Actuary per line, so a Bank writing both life and medical
    # needs two. The per-line rule itself is covered in test_actuary_per_line.py.
    banker.workforce.add_workers(
        2, training_level=1, profession=Profession.ACTUARY.value
    )

    actions = ai.take_turn(
        miner,
        market,
        [miner, banker],
        ProductionEngine(),
        TradingEngine(market, DealLedger()),
        EventResult("Normal"),
        "Spring",
        0,
        0,
    )

    policy_types = {policy.policy_type for policy in miner.insurance_policies}
    assert {"life", "medical"} <= policy_types
    assert any("bought life insurance" in action for action in actions)


def test_ai_requests_replacement_training_for_staffing_deficit():
    ai = AIStrategy()
    market = Market()
    training = TrainingRegistry()
    miner = make_player(1, "Miner AI", ["Miner"], dollops=800.0)
    educator = make_player(2, "Educator AI", ["Educator"], dollops=800.0)
    miner.workforce.workers.clear()
    miner.workforce.add_workers(5, profession=Profession.UNSKILLED.value)

    actions = ai.take_turn(
        miner,
        market,
        [miner, educator],
        ProductionEngine(),
        TradingEngine(market, DealLedger()),
        EventResult("Normal"),
        "Spring",
        0,
        0,
        training_registry=training,
    )

    requests = training.active_for_player(miner.player_id)
    assert requests
    assert any(req.target_profession == Profession.MINER.value for req in requests)
    assert any("requested replacement training" in action for action in actions)


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
    assert summary["ask_quantity"] == 44


def test_ai_produces_multiple_runs_when_inputs_available():
    ai = AIStrategy()
    market = Market()
    miner = make_player(1, "Miner AI", ["Miner"])
    miner.receive_resources(ResourceType.OIL, 5)
    miner.receive_resources(ResourceType.FREIGHT, 2)
    miner.receive_resources(ResourceType.MINING_EQUIPMENT, 2)
    # Metal is assayed (#26); stock Lab Tests so this measures production
    # quantities rather than the un-assayed yield penalty.
    miner.receive_resources(ResourceType.LABORATORY_TESTS, 4)

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
        "80x Ore" in action and "20x Metal" in action and "90x Oil" in action
        for action in actions
    )
    summary = market.market_summary()
    assert summary[ResourceType.ORE.value]["ask_quantity"] == 78
    assert summary[ResourceType.METAL.value]["ask_quantity"] == 20
    assert summary[ResourceType.OIL.value]["ask_quantity"] == 88


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
    assert bids[0].remaining == 1
    assert farmer.inventory.get(ResourceType.FARM_MACHINERY) == 0
    assert ResourceType.GRAIN in farmer.inventory.amounts


def test_farmer_ai_packages_food_for_visible_human_demand():
    ai = AIStrategy()
    market = Market()
    farmer = make_player(1, "Farmer AI", ["Farmer"], dollops=30.0)
    buyer = make_player(2, "Human Buyer", ["Transporter"], dollops=500.0, is_human=True)
    farmer.add_capital("farmer.industrial_kitchen")
    farmer.workforce.add_workers(1, training_level=1, profession=Profession.FARMER.value)
    farmer.workforce.add_workers(
        1, training_level=1, profession=Profession.FARMING_TECHNICIAN.value
    )
    farmer.workforce.add_workers(8, profession=Profession.UNSKILLED.value)
    farmer.receive_resources(ResourceType.GRAIN, 3)
    farmer.receive_resources(ResourceType.PRODUCE, 3)
    farmer.receive_resources(ResourceType.FISH, 3)
    farmer.receive_resources(ResourceType.FARM_MACHINERY, 1)
    farmer.receive_resources(ResourceType.OIL, 1)
    bid_price = round(market.current_price(ResourceType.FOOD) * 1.6, 2)
    market.post_bid(buyer, ResourceType.FOOD, bid_price, 3)

    actions = ai.take_turn(
        farmer,
        market,
        [farmer, buyer],
        ProductionEngine(),
        TradingEngine(market, DealLedger()),
        EventResult("Normal"),
        "Spring",
        0,
        0,
    )

    assert buyer.inventory.get(ResourceType.FOOD) == 3
    assert farmer.dollops == pytest.approx(30.0 + bid_price * 3)
    assert any("produced" in action and "Food" in action for action in actions)


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


def test_ai_banker_originates_working_capital_loan_to_healthy_ai_borrower():
    ai = AIStrategy()
    market = Market()
    loan_ledger = LoanLedger()
    banker = make_player(1, "Banker AI", ["Banker"], dollops=100.0)
    banker.workforce.add_workers(1, training_level=1, profession=Profession.BANKER.value)
    farmer = make_player(2, "Farmer AI", ["Farmer"], dollops=300.0)

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
    assert len(farmer_loans) == 1
    loan = farmer_loans[0]
    assert loan.principal >= 50.0
    assert loan.interest_rate == round(loan.posted_at_issue + 0.02, 4)
    assert loan.own_committed > 0
    assert loan.external_funded > 0
    assert any("issued Loan" in action and "Farmer AI" in action for action in actions)


def test_ai_banker_originates_loans_in_normal_all_ai_game():
    specs = [
        PlayerSpec(
            name=role_name,
            role_names=[role_name],
            is_human=False,
            starting_dollops=STARTING_DOLLOPS,
        )
        for role_name in ROLES
    ]
    game = Game(
        GameConfig(player_specs=specs, num_years=1, starting_dollops=STARTING_DOLLOPS),
        _SilentIO(),
    )
    game.setup()
    summary = game.run()

    customer_loans = [
        loan for loan in game.loan_ledger.all_loans()
        if loan.lender_id >= 0 and loan.borrower_id != loan.lender_id
    ]
    assert summary.winner is not None
    assert customer_loans
    assert len([
        loan for loan in customer_loans
        if loan.status == LoanStatus.ACTIVE
    ]) <= 2


def test_ai_banker_does_not_offer_loan_when_reserve_short():
    ai = AIStrategy()
    market = Market()
    loan_ledger = LoanLedger()
    banker = make_player(1, "Banker AI", ["Banker"], dollops=1.0)
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


def test_ai_banker_declines_new_loans_when_at_active_cap():
    ai = AIStrategy()
    market = Market()
    loan_ledger = LoanLedger()
    banker = make_player(1, "Banker AI", ["Banker"], dollops=100.0)
    banker.workforce.add_workers(1, training_level=1, profession="Banker")
    farmer = make_player(2, "Farmer AI", ["Farmer"], dollops=0.0)
    miner = make_player(3, "Miner AI", ["Miner"], dollops=0.0)
    transporter = make_player(4, "Transporter AI", ["Transporter"], dollops=0.0)
    loan_ledger.create_loan(farmer.player_id, banker.player_id, 10.0, 0.05, 0, 0)
    loan_ledger.create_loan(miner.player_id, banker.player_id, 10.0, 0.05, 0, 0)

    action = ai._ai_issue_loan(
        banker,
        transporter,
        50.0,
        loan_ledger,
        year=0,
        season_index=0,
    )

    transporter_loans = [
        loan for loan in loan_ledger.active_loans_for(transporter.player_id)
        if loan.borrower_id == transporter.player_id
    ]
    assert transporter_loans == []
    assert "active-loan cap reached (2/2)" in action


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


def test_ai_borrower_can_take_human_banker_loan_when_capital_short():
    ai = AIStrategy()
    market = Market()
    loan_ledger = LoanLedger()
    banker = make_player(1, "Human Banker", ["Banker"], dollops=100.0, is_human=True)
    banker.workforce.add_workers(1, training_level=1, profession=Profession.BANKER.value)
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
    assert any("Human Banker issued Loan" in action for action in actions)


def test_ai_recapitalizes_with_unissued_shares_when_loan_unavailable():
    ai = AIStrategy()
    market = Market()
    loan_ledger = LoanLedger()
    banker = make_player(1, "Tapped Banker", ["Banker"], dollops=0.0)
    farmer = make_player(2, "Farmer AI", ["Farmer"], dollops=0.0)
    farmer.personal_cash = 500.0
    farmer.cap_table = CapTable.new_with_majority(str(farmer.player_id))
    farmer.holdings = {str(farmer.player_id): AUCTIONED_SHARES}
    money0 = farmer.dollops + farmer.personal_cash

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
    assert farmer_loans == []
    assert farmer.dollops > 0
    assert farmer.personal_cash < 500.0
    assert farmer.dollops + farmer.personal_cash == money0
    assert farmer.cap_table.held_by(str(farmer.player_id)) > AUCTIONED_SHARES
    assert farmer.cap_table.unissued() < 100 - AUCTIONED_SHARES
    assert any("recapitalized" in action for action in actions)


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
    # Reagents moved to Medical Sciences; use a remaining Manufacturer line.
    market.post_bid(transporter, ResourceType.MEDICAL_DEVICES, 55.0, 3)

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
    # Reagents moved to Medical Sciences; use a remaining Manufacturer line.
    # Bid well above MedicalDevices' base price (50) so the AI's ask auto-matches.
    market.post_bid(educator, ResourceType.MEDICAL_DEVICES, 90.0, 10)

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

    assert any("Medical" in action for action in actions)
    assert educator.inventory.get(ResourceType.MEDICAL_DEVICES) > 0
