from __future__ import annotations

from island_traders.cli.prompts import FakeIOAdapter
from island_traders.engine.production import ProductionEngine
from island_traders.engine.trading import TradingEngine
from island_traders.engine.turn import TurnManager, TurnResult
from island_traders.models.deal import DealLedger
from island_traders.models.market import Market
from island_traders.models.player import Player
from island_traders.models.profession import Profession
from island_traders.models.role import ROLES


class _RepurposeIO(FakeIOAdapter):
    def __init__(self, choices):
        super().__init__()
        self.choices = list(choices)

    def choose_option(self, prompt, options, request_summary=None):
        self.printed.append(prompt)
        return self.choices.pop(0)

    def confirm(self, prompt, request_summary=None):
        self.printed.append(prompt)
        return True


def test_repurpose_worker_can_return_trained_worker_to_unskilled_pool():
    player = Player(0, "Agricola", [ROLES["Farmer"]], 100.0, is_human=True)
    player.workforce.workers.clear()
    player.workforce._next_id = 0
    worker = player.workforce.add_workers(
        1,
        training_level=2,
        profession=Profession.FARMING_TECHNICIAN.value,
    )[0]
    worker.experience_seasons = 5

    market = Market()
    io = _RepurposeIO([str(worker.worker_id), Profession.UNSKILLED.value])
    tm = TurnManager(
        players=[player],
        production_engine=ProductionEngine(),
        trading_engine=TradingEngine(market, DealLedger()),
        market=market,
        io_adapter=io,
    )

    tm._action_repurpose_worker(player, TurnResult(player.player_id, "Spring", 0))

    assert worker.profession == Profession.UNSKILLED.value
    assert worker.training_level == 0
    assert worker.experience_seasons == 0
    assert player.dollops < 100.0
