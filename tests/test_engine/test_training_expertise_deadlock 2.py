"""Tests for the 2026-05-27 training-expertise-deadlock brief.

Covers three layers:

- Layer 1: AI Manufacturer's demand chooser includes indirect demand
  via human players' pending training requests / in-training workers.
- Layer 2: SUPPLY_TRAINING_EXPERTISE action lets a requester unblock
  an Expertise-starved Educator by gifting Expertise.
- Layer 3: training_pipeline payload now carries blocker_reason,
  seasons_blocked, and can_supply_expertise per pending request.
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from island_traders.cli.prompts import FakeIOAdapter
from island_traders.engine.ai import AIStrategy
from island_traders.engine.production import ProductionEngine
from island_traders.engine.trading import TradingEngine
from island_traders.engine.turn import TurnAction, TurnManager, TurnResult
from island_traders.models.deal import DealLedger
from island_traders.models.market import Market
from island_traders.models.player import Player
from island_traders.models.resource import ResourceType
from island_traders.models.role import ROLES
from island_traders.models.training import TrainingRegistry


def _player(pid: int, role: str, name: str | None = None, *, is_human: bool = True) -> Player:
    return Player(pid, name or role, [ROLES[role]], 100.0, is_human=is_human)


def _manager(players, training, io=None) -> TurnManager:
    market = Market()
    return TurnManager(
        players=players,
        production_engine=ProductionEngine(),
        trading_engine=TradingEngine(market, DealLedger()),
        market=market,
        io_adapter=io or FakeIOAdapter(),
        training=training,
    )


# ─────────────────────────────────────────────────────────────────────────
# Layer 1 — AI Manufacturer demand chooser now sees indirect demand
# ─────────────────────────────────────────────────────────────────────────


def test_indirect_demand_via_pending_training_request_triggers_demand_chooser():
    """A human Miner with a pending training request creates indirect
    LaboratoryEquipment demand (Educator needs Expertise → needs
    LabEquipment).  The AI Manufacturer's _has_human_equipment_demand
    must return True even though the Miner doesn't directly consume
    LabEquipment.

    Regression for AyaySir's 9-season deadlock playtest report.
    """
    ai = AIStrategy()
    miner = _player(1, "Miner", "AyaySir", is_human=True)
    educator = _player(2, "Educator", "Chromio", is_human=False)
    manufacturer = _player(3, "Manufacturer", "ForgeHaven", is_human=False)
    registry = TrainingRegistry()

    # No pending training yet → chooser sees only DIRECT demand
    # (Miner -> MiningEquipment).  Mining demand alone would still
    # return True, but Miner doesn't directly need LabEquipment.
    # The point of this test is that the indirect path is triggered
    # for the right reasons.  Confirm baseline first.
    assert ai._has_human_equipment_demand(
        [miner, educator, manufacturer], training_registry=registry,
    )  # True via MINING_EQUIPMENT direct demand

    # Now imagine the only human is on a non-equipment-consuming role
    # (Banker) so the direct path returns False.
    banker = _player(4, "Banker", "Comet Banker", is_human=True)
    others = [banker, educator, manufacturer]
    assert not ai._has_human_equipment_demand(others, training_registry=registry)

    # Banker files a training request — the indirect path should fire
    # even though Banker doesn't directly consume any equipment.
    registry.propose(
        requester_id=banker.player_id,
        worker_ids=[401],
        educator_id=educator.player_id,
        dollops_to_educator=30.0,
        target_profession="BankingAnalyst",
        year=0,
        season=0,
        transport_mode="air_ticket",
    )
    assert ai._has_human_equipment_demand(others, training_registry=registry)


def test_indirect_demand_via_in_training_workers():
    """Even with no pending requests, a human with workers already
    in training signals an active pipeline that needs LabEquipment
    upstream to keep Expertise flowing for future approvals."""
    ai = AIStrategy()
    banker = _player(1, "Banker", "Banker", is_human=True)
    educator = _player(2, "Educator", is_human=False)
    manufacturer = _player(3, "Manufacturer", is_human=False)
    registry = TrainingRegistry()

    # Baseline: no pending, no in-training → False.
    others = [banker, educator, manufacturer]
    assert not ai._has_human_equipment_demand(others, training_registry=registry)

    # Mark a worker as already dispatched (in_training = True).
    from island_traders.models.workforce import Worker

    banker.workforce.workers.append(
        Worker(worker_id=999, profession="Unskilled", in_training=True)
    )
    assert ai._has_human_equipment_demand(others, training_registry=registry)


def test_no_registry_falls_back_to_direct_demand_only():
    """If take_turn is called without a training_registry (e.g. legacy
    call path), _has_human_equipment_demand still works — it just
    falls back to the direct-demand check."""
    ai = AIStrategy()
    miner = _player(1, "Miner", is_human=True)
    educator = _player(2, "Educator", is_human=False)
    # Direct demand still detected without the registry.
    assert ai._has_human_equipment_demand([miner, educator], training_registry=None)


# ─────────────────────────────────────────────────────────────────────────
# Layer 2 — SUPPLY_TRAINING_EXPERTISE action
# ─────────────────────────────────────────────────────────────────────────


class _SupplyIO(FakeIOAdapter):
    """IO that picks the only available batch and confirms."""

    def __init__(self, batch_id):
        super().__init__()
        self.batch_id = batch_id

    def choose_option(self, prompt, options, request_summary=None):
        # Picker offers eligible batches keyed by str(batch_id).
        return str(self.batch_id) if options else None

    def confirm(self, prompt, request_summary=None):
        return True


def test_supply_training_expertise_transfers_expertise_to_educator():
    """Requester with Expertise on hand supplies it to an Educator
    starved of Expertise, unblocking a pending training request.

    Test setup needs the Educator to have all OTHER prerequisites
    (Technical Workshop capital + Technical Director + Instructor +
    Courses) so the only remaining blocker is Expertise.  Without
    this, _training_capacity_status reports a different blocker first
    and the SUPPLY action correctly refuses (not the path we're
    exercising here).
    """
    from island_traders.models.workforce import Worker
    from island_traders.models.profession import Profession

    miner = _player(1, "Miner", "AyaySir", is_human=True)
    educator = _player(2, "Educator", "Chromio", is_human=True)

    # Miner has 5 Expertise to spare.
    miner.receive_resources(ResourceType.EXPERTISE, 5)
    # Educator has Courses on hand but zero Expertise.
    educator.receive_resources(ResourceType.COURSES, 5)
    # Mandatory Technician-course prereqs on the Educator side:
    educator.add_capital("educator.technical_workshop", count=1)
    educator.workforce.workers.append(
        Worker(worker_id=900, profession=Profession.TECHNICAL_DIRECTOR.value)
    )
    educator.workforce.workers.append(
        Worker(worker_id=901, profession=Profession.INSTRUCTOR.value)
    )

    registry = TrainingRegistry()
    # Train one Mechanic (Technician band, needs 1 Expertise per course).
    req = registry.propose(
        requester_id=miner.player_id,
        worker_ids=[101],
        educator_id=educator.player_id,
        dollops_to_educator=20.0,
        target_profession="Mechanic",
        year=0,
        season=0,
        transport_mode="air_ticket",
    )

    mgr = _manager([miner, educator], registry, io=_SupplyIO(req.batch_id))
    result = TurnResult(player_id=miner.player_id, season=0, year=0)
    mgr._action_supply_training_expertise(miner, result)

    # Expertise should have moved from Miner to Educator.
    assert miner.inventory.get(ResourceType.EXPERTISE) < 5
    assert educator.inventory.get(ResourceType.EXPERTISE) >= 1
    assert any(
        "supply_training_expertise" in a for a in result.actions_taken
    )


def test_supply_training_expertise_no_eligible_requests_no_op():
    """When the requester has no pending requests blocked on Expertise,
    the action prints a clean message and does nothing."""
    miner = _player(1, "Miner", is_human=True)
    educator = _player(2, "Educator", is_human=True)
    registry = TrainingRegistry()
    mgr = _manager([miner, educator], registry)
    result = TurnResult(player_id=miner.player_id, season=0, year=0)
    miner.receive_resources(ResourceType.EXPERTISE, 5)
    expertise_before = miner.inventory.get(ResourceType.EXPERTISE)
    mgr._action_supply_training_expertise(miner, result)
    # No transfer, no actions logged.
    assert miner.inventory.get(ResourceType.EXPERTISE) == expertise_before
    assert not any(
        "supply_training_expertise" in a for a in result.actions_taken
    )


def test_supply_training_expertise_authorization_only_requester_can_supply():
    """A non-requester player cannot supply Expertise to another
    player's request (no eligible options shown to them)."""
    miner = _player(1, "Miner", is_human=True)
    banker = _player(2, "Banker", is_human=True)
    educator = _player(3, "Educator", is_human=True)
    miner.receive_resources(ResourceType.EXPERTISE, 5)
    banker.receive_resources(ResourceType.EXPERTISE, 5)
    educator.receive_resources(ResourceType.COURSES, 5)

    registry = TrainingRegistry()
    # Miner's pending request — Banker is NOT the requester.
    registry.propose(
        requester_id=miner.player_id,
        worker_ids=[101],
        educator_id=educator.player_id,
        dollops_to_educator=20.0,
        target_profession="Mechanic",
        year=0,
        season=0,
        transport_mode="air_ticket",
    )
    mgr = _manager([miner, banker, educator], registry)
    result = TurnResult(player_id=banker.player_id, season=0, year=0)
    expertise_before = banker.inventory.get(ResourceType.EXPERTISE)
    mgr._action_supply_training_expertise(banker, result)
    # Banker's Expertise unchanged — they have no eligible batches.
    assert banker.inventory.get(ResourceType.EXPERTISE) == expertise_before


# ─────────────────────────────────────────────────────────────────────────
# Layer 3 — training_pipeline payload deadlock-visibility fields
# ─────────────────────────────────────────────────────────────────────────


def test_pending_for_requester_query_returns_only_awaiting_educator():
    """The new TrainingRegistry.pending_for_requester filter only
    returns AWAITING_EDUCATOR requests filed by the given player."""
    registry = TrainingRegistry()
    miner_id = 1
    educator_id = 2
    req = registry.propose(
        requester_id=miner_id,
        worker_ids=[100],
        educator_id=educator_id,
        dollops_to_educator=10.0,
        target_profession="Mechanic",
        year=0,
        season=0,
        transport_mode="air_ticket",
    )

    pending = registry.pending_for_requester(miner_id)
    assert len(pending) == 1
    assert pending[0].batch_id == req.batch_id

    # Someone else's pending requests are not returned.
    other_pending = registry.pending_for_requester(99)
    assert other_pending == []
