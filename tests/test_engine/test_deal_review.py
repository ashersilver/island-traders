from island_traders.cli.prompts import FakeIOAdapter
from island_traders.engine.production import ProductionEngine
from island_traders.engine.trading import TradingEngine
from island_traders.engine.turn import TurnManager, TurnResult
from island_traders.models.deal import DealLedger, DealStatus
from island_traders.models.market import Market
from island_traders.models.player import Player
from island_traders.models.resource import ResourceType
from island_traders.models.role import ROLES


class ConfirmIO(FakeIOAdapter):
    def __init__(self, confirmations: list[bool]):
        super().__init__()
        self.confirmations = list(confirmations)

    def confirm(self, prompt):
        self.printed.append(prompt)
        return self.confirmations.pop(0)


def _player(player_id: int, name: str, role_name: str) -> Player:
    return Player(player_id, name, [ROLES[role_name]], 100.0, is_human=True)


def _turn_manager(players, ledger, io):
    market = Market()
    return TurnManager(
        players=players,
        production_engine=ProductionEngine(),
        trading_engine=TradingEngine(market, ledger),
        market=market,
        io_adapter=io,
    )


def test_pending_deal_prompts_counterparty_and_accepts():
    farmer = _player(0, "Farmer", "Farmer")
    banker = _player(1, "Banker", "Banker")
    farmer.receive_resources(ResourceType.FOOD, 3)
    banker.receive_resources(ResourceType.FINANCE, 2)
    ledger = DealLedger()
    deal = ledger.create_proposal(
        proposer_id=farmer.player_id,
        target_id=banker.player_id,
        offer_resource=ResourceType.FOOD,
        offer_qty=3,
        request_resource=ResourceType.FINANCE,
        request_qty=2,
    )
    tm = _turn_manager([farmer, banker], ledger, ConfirmIO([True]))
    result = TurnResult(player_id=banker.player_id, season=0, year=0)

    tm._review_pending_deals(banker, result)

    assert deal.status == DealStatus.ACCEPTED
    assert banker.inventory.get(ResourceType.FOOD) == 3
    assert farmer.inventory.get(ResourceType.FINANCE) == 2
    assert result.actions_taken == ["deal:accepted:0"]


def test_pending_deal_prompts_counterparty_and_rejects():
    farmer = _player(0, "Farmer", "Farmer")
    banker = _player(1, "Banker", "Banker")
    farmer.receive_resources(ResourceType.FOOD, 3)
    banker.receive_resources(ResourceType.FINANCE, 2)
    ledger = DealLedger()
    deal = ledger.create_proposal(
        proposer_id=farmer.player_id,
        target_id=banker.player_id,
        offer_resource=ResourceType.FOOD,
        offer_qty=3,
        request_resource=ResourceType.FINANCE,
        request_qty=2,
    )
    tm = _turn_manager([farmer, banker], ledger, ConfirmIO([False]))
    result = TurnResult(player_id=banker.player_id, season=0, year=0)

    tm._review_pending_deals(banker, result)

    assert deal.status == DealStatus.REJECTED
    assert banker.inventory.get(ResourceType.FOOD) == 0
    assert farmer.inventory.get(ResourceType.FINANCE) == 0
    assert result.actions_taken == ["deal:rejected:0"]


def test_pending_deal_accept_expires_if_resources_are_stale():
    farmer = _player(0, "Farmer", "Farmer")
    banker = _player(1, "Banker", "Banker")
    banker.receive_resources(ResourceType.FINANCE, 2)
    ledger = DealLedger()
    deal = ledger.create_proposal(
        proposer_id=farmer.player_id,
        target_id=banker.player_id,
        offer_resource=ResourceType.FOOD,
        offer_qty=3,
        request_resource=ResourceType.FINANCE,
        request_qty=2,
    )
    tm = _turn_manager([farmer, banker], ledger, ConfirmIO([True]))
    result = TurnResult(player_id=banker.player_id, season=0, year=0)

    tm._review_pending_deals(banker, result)

    assert deal.status == DealStatus.EXPIRED
    assert banker.inventory.get(ResourceType.FINANCE) == 2
    assert result.actions_taken == ["deal:expired:0"]
