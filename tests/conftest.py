import pytest
from island_traders.models.resource import ResourceType, ResourceBundle
from island_traders.models.role import ROLES
from island_traders.models.player import Player
from island_traders.models.market import Market
from island_traders.models.deal import DealLedger
from island_traders.models.workforce import Workforce
from island_traders.engine.events import EventResult
from island_traders.cli.prompts import FakeIOAdapter


def _make_player(player_id, name, role_name, dollops=100.0):
    """Create a player with fully experienced expert workers (efficiency=1.0) so
    production formula tests remain deterministic regardless of workforce scaling."""
    p = Player(player_id=player_id, name=name, roles=[ROLES[role_name]], dollops=dollops, is_human=False)
    workers = p.workforce.add_workers(8, training_level=3)
    for w in workers:
        w.experience_seasons = 20   # well above any plateau; efficiency = 1.0
    return p


@pytest.fixture
def base_market():
    return Market()


@pytest.fixture
def farmer():
    return _make_player(0, "Alice", "Farmer")


@pytest.fixture
def banker():
    return _make_player(1, "Bob", "Banker")


@pytest.fixture
def miner():
    return _make_player(2, "Carol", "Miner")


@pytest.fixture
def manufacturer():
    return _make_player(3, "Dave", "Manufacturer")


@pytest.fixture
def normal_event():
    return EventResult("Normal Operations", yield_modifier=1.0)


@pytest.fixture
def outage_event():
    return EventResult("Strike", outage=True)


@pytest.fixture
def bumper_event():
    return EventResult("Bumper Harvest", yield_modifier=1.8, productivity_bonus=2)


@pytest.fixture
def ledger():
    return DealLedger()


@pytest.fixture
def fake_io():
    return FakeIOAdapter()
