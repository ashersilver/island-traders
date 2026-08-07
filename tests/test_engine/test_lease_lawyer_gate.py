"""Lawyer profession + lease-inception gate (GitHub #44).

Lawyers are a Manager-tier profession trainable from every island through the
existing Educator Manager-course pipeline.  Writing a **new** lease requires
at least one active Lawyer on the lessee's roster.  The gate is one-shot at
inception: leases already running are unaffected by later roster changes, and
leases that predate the rule are grandfathered.

The Banker starts with 1 Lawyer (in-house counsel) so the Bank can lease its
own equipment from turn 1; no other island does.
"""
from __future__ import annotations

from island_traders.cli.prompts import FakeIOAdapter
from island_traders.constants import (
    SKILLED_PROFESSIONS,
    STARTING_WORKERS_BY_PROFESSION,
    UNIVERSITY_CAPACITY,
)
from island_traders.constants_capacity import CAPITAL_CATALOGUE
from island_traders.engine.game import Game, GameConfig, PlayerSpec
from island_traders.engine.production import ProductionEngine
from island_traders.engine.trading import TradingEngine
from island_traders.engine.turn import TurnManager, TurnResult
from island_traders.models.capacity import find_item
from island_traders.models.deal import DealLedger
from island_traders.models.lease import (
    NO_LAWYER_MESSAGE,
    LeaseLedger,
    LeaseStatus,
    lessee_has_lawyer,
)
from island_traders.models.market import Market
from island_traders.models.player import Player
from island_traders.models.profession import (
    EDUCATION_SEASONS,
    PROFESSION_BAND,
    PROFESSION_LABEL,
    ROLE_PROFESSIONS,
    Profession,
    WorkerBand,
    band_of,
)
from island_traders.models.role import ROLES


WORKSHOP_ID = "educator.technical_workshop"


def _player(pid: int, name: str, role: str, dollops: float = 500.0) -> Player:
    return Player(pid, name, [ROLES[role]], dollops, is_human=True)


def _tm(players, leases=None, io=None) -> TurnManager:
    market = Market()
    return TurnManager(
        players=players,
        production_engine=ProductionEngine(),
        trading_engine=TradingEngine(market, DealLedger()),
        market=market,
        io_adapter=io or FakeIOAdapter(),
        lease_ledger=leases or LeaseLedger(),
    )


def _workshop():
    item = find_item(CAPITAL_CATALOGUE, WORKSHOP_ID)
    assert item is not None
    return item


# ---------------------------------------------------------------------------
# Profession wiring
# ---------------------------------------------------------------------------

def test_lawyer_is_a_manager_band_profession():
    assert PROFESSION_BAND[Profession.LAWYER] == WorkerBand.MANAGER
    assert band_of("Lawyer") == WorkerBand.MANAGER
    assert PROFESSION_LABEL[Profession.LAWYER] == "Lawyer"


def test_lawyer_is_trainable_from_every_island():
    """Same treatment Chef got — every island can send someone to law school."""
    for role_name, professions in ROLE_PROFESSIONS.items():
        assert Profession.LAWYER in professions, f"{role_name} cannot train a Lawyer"
    for role_name, professions in SKILLED_PROFESSIONS.items():
        assert "Lawyer" in professions, f"{role_name} does not count Lawyers as skilled"


def test_lawyer_training_terms():
    assert EDUCATION_SEASONS[Profession.LAWYER] == 2
    assert UNIVERSITY_CAPACITY["Lawyer"] == 2


def test_only_the_banker_starts_with_a_lawyer():
    seeded = {
        role: dict(breakdown).get("Lawyer", 0)
        for role, breakdown in STARTING_WORKERS_BY_PROFESSION.items()
    }
    assert seeded.pop("Banker") == 1
    assert all(count == 0 for count in seeded.values()), seeded


def test_game_setup_gives_the_banker_exactly_one_lawyer():
    game = Game(
        GameConfig([
            PlayerSpec("Bank", ["Banker"], is_human=False),
            PlayerSpec("School", ["Educator"], is_human=False),
        ]),
        FakeIOAdapter(),
    )
    game.setup()
    banker, educator = game.players

    assert banker.workforce.count_profession("Lawyer") == 1
    assert lessee_has_lawyer(banker)
    assert educator.workforce.count_profession("Lawyer") == 0
    assert not lessee_has_lawyer(educator)


# ---------------------------------------------------------------------------
# lessee_has_lawyer
# ---------------------------------------------------------------------------

def test_lessee_has_lawyer_counts_only_active_lawyers():
    player = _player(0, "Counsel", "Educator")
    assert not lessee_has_lawyer(player)

    lawyer = player.workforce.add_workers(1, profession=Profession.LAWYER.value)[0]
    assert lessee_has_lawyer(player)

    # A Lawyer still away at law school doesn't count.
    lawyer.in_training = True
    assert not lessee_has_lawyer(player)


# ---------------------------------------------------------------------------
# Mid-game LEASE_CAPITAL gate
# ---------------------------------------------------------------------------

def test_lease_action_refused_without_a_lawyer():
    educator = _player(0, "Educator", "Educator", dollops=500.0)
    leases = LeaseLedger()
    io = FakeIOAdapter()
    tm = _tm([educator], leases, io=io)

    tm._action_lease_capital(educator, TurnResult(educator.player_id, 0, 0), year=0, season_index=0)

    assert leases.leases == []
    assert educator.capital_inventory.get(WORKSHOP_ID, 0) == 0
    assert educator.dollops == 500.0
    assert any(NO_LAWYER_MESSAGE in line for line in io.printed), io.printed


def test_lease_action_succeeds_once_a_lawyer_is_on_the_roster():
    educator = _player(0, "Educator", "Educator", dollops=500.0)
    educator.workforce.add_workers(1, profession=Profession.LAWYER.value)
    leases = LeaseLedger()
    io = FakeIOAdapter()
    tm = _tm([educator], leases, io=io)

    result = TurnResult(educator.player_id, 0, 0)
    tm._action_lease_capital(educator, result, year=0, season_index=0)

    assert len(leases.leases) == 1
    assert leases.leases[0].lessee_id == educator.player_id
    assert leases.leases[0].status == LeaseStatus.ACTIVE
    assert educator.dollops < 500.0
    assert not any(NO_LAWYER_MESSAGE in line for line in io.printed), io.printed
    assert any(a.startswith("lease_capital:") for a in result.actions_taken)


def test_certification_is_one_shot_at_inception():
    """Losing the Lawyer after signing does not disturb a running lease."""
    educator = _player(0, "Educator", "Educator", dollops=500.0)
    lawyer = educator.workforce.add_workers(1, profession=Profession.LAWYER.value)[0]
    leases = LeaseLedger()
    tm = _tm([educator], leases)
    tm._action_lease_capital(educator, TurnResult(educator.player_id, 0, 0), year=0, season_index=0)
    lease = leases.leases[0]

    # Counsel retires the following season.
    educator.workforce.workers.remove(lawyer)
    assert not lessee_has_lawyer(educator)

    assert lease.status == LeaseStatus.ACTIVE
    assert lease.annual_due(year=1, season=0)


def test_investing_phase_is_exempt_from_the_lawyer_gate():
    """Opening leases are standard-form contracts drawn by the Bank's counsel.

    No island has had a turn to train a Lawyer at investing-phase, and the
    only lease-eligible item in the catalogue is Educator-only — gating here
    would remove the opening lease path rather than gate it.  Pinned so the
    exemption is a decision, not an oversight; revisit if the lease
    catalogue grows.
    """
    import pytest

    pytest.importorskip("fastapi")
    from island_traders.server.app import GameManager, GameRoom, InvestingState, LobbyPlayer

    mgr = GameManager()
    room = GameRoom("lawyer-gate", "Test", 2, 1, True, "GS0003", "p0", starting_capital=100.0)
    room.players = [
        LobbyPlayer("p0", "Educator", role_names=["Educator"]),
        LobbyPlayer("p1", "Banker", role_names=["Banker"]),
    ]
    mgr.rooms[room.room_id] = room
    room.status = "investing"
    room.investing = InvestingState()
    mgr.submit_investment(room.room_id, "p0", [f"lease:{WORKSHOP_ID}"], ready=False)
    mgr.submit_investment(room.room_id, "p1", [], ready=False)

    mgr._resolve_investing(room.room_id)

    educator = room.game.players[0]
    assert not lessee_has_lawyer(educator)
    assert len(room.game.lease_ledger.all_leases()) == 1
    assert educator.capital_inventory[WORKSHOP_ID] == 1


def test_grandfathered_lease_predating_the_rule_keeps_running():
    """A lease written straight into the ledger (no Lawyer) is untouched."""
    educator = _player(0, "Educator", "Educator", dollops=500.0)
    leases = LeaseLedger()
    lease = leases.create_lease(
        item_id=WORKSHOP_ID,
        lessee_id=educator.player_id,
        lessor_id=-1,
        year=0,
        season=0,
        term_years=3,
        annual_payment=10.0,
        buyout_payment=5.0,
        locked_lease_rate=0.05,
        payments_made=1,
        last_payment_year=0,
    )
    educator.add_capital(WORKSHOP_ID, 1)

    assert not lessee_has_lawyer(educator)
    assert lease.status == LeaseStatus.ACTIVE
    assert lease.annual_due(year=1, season=0)
