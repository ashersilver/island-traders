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
    assert summary["ask_quantity"] == 7
