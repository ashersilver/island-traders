"""Tests for the medical staffing contract system."""
import pytest
from island_traders.models.staffing import (
    StaffingRegistry, StaffingStatus,
)


def make_registry() -> StaffingRegistry:
    return StaffingRegistry()


def _propose(reg, requester_id=1, provider_id=0, profession="Doctor",
             staff_count=1, duration_seasons=2, fee_total=40.0,
             year=0, season=0, tickets_by_requester=0):
    return reg.propose(
        requester_id=requester_id,
        provider_id=provider_id,
        profession=profession,
        staff_count=staff_count,
        duration_seasons=duration_seasons,
        fee_total=fee_total,
        year=year,
        season=season,
        tickets_supplied_by_requester=tickets_by_requester,
    )


# -------------------------------------------------------------------
# propose()
# -------------------------------------------------------------------

class TestPropose:
    def test_creates_contract_with_proposed_status(self):
        reg = make_registry()
        c = _propose(reg)
        assert c.status == StaffingStatus.PROPOSED

    def test_auto_increments_contract_id(self):
        reg = make_registry()
        c1 = _propose(reg)
        c2 = _propose(reg, requester_id=2)
        assert c2.contract_id == c1.contract_id + 1

    def test_round_trip_tickets_are_double_staff_count(self):
        reg = make_registry()
        c = _propose(reg, staff_count=3)
        assert c.tickets_required == 6

    def test_tickets_supplied_by_requester_capped_at_required(self):
        reg = make_registry()
        c = _propose(reg, staff_count=1, tickets_by_requester=99)
        assert c.tickets_supplied_by_requester == 2  # capped at tickets_required

    def test_tickets_supplied_by_provider_property(self):
        reg = make_registry()
        c = _propose(reg, staff_count=2, tickets_by_requester=1)
        # required=4, requester supplies 1 → provider supplies 3
        assert c.tickets_supplied_by_provider == 3

    def test_raises_for_zero_staff(self):
        reg = make_registry()
        with pytest.raises(ValueError, match="at least 1"):
            reg.propose(
                requester_id=1, provider_id=0, profession="Doctor",
                staff_count=0, duration_seasons=1, fee_total=20.0,
                year=0, season=0,
            )

    def test_raises_for_zero_duration(self):
        reg = make_registry()
        with pytest.raises(ValueError, match="at least 1"):
            reg.propose(
                requester_id=1, provider_id=0, profession="Doctor",
                staff_count=1, duration_seasons=0, fee_total=20.0,
                year=0, season=0,
            )


# -------------------------------------------------------------------
# Approval / rejection / counter flow
# -------------------------------------------------------------------

class TestApproveFlow:
    def test_provider_approve_moves_to_awaiting_transport(self):
        reg = make_registry()
        c = _propose(reg)
        reg.provider_approve(c.contract_id)
        assert c.status == StaffingStatus.AWAITING_TRANSPORT

    def test_provider_reject_moves_to_rejected(self):
        reg = make_registry()
        c = _propose(reg)
        reg.provider_reject(c.contract_id, reason="Too busy")
        assert c.status == StaffingStatus.REJECTED
        assert c.decline_reason == "Too busy"
        assert not c.decision_acknowledged

    def test_provider_counter_moves_to_countered(self):
        reg = make_registry()
        c = _propose(reg, fee_total=40.0)
        reg.provider_counter(c.contract_id, counter_fee=60.0, message="Higher rate required")
        assert c.status == StaffingStatus.COUNTERED
        assert c.counter_fee == 60.0
        assert c.counter_message == "Higher rate required"

    def test_requester_accept_counter(self):
        reg = make_registry()
        c = _propose(reg, fee_total=40.0)
        reg.provider_counter(c.contract_id, counter_fee=55.0)
        reg.requester_accept_counter(c.contract_id)
        assert c.status == StaffingStatus.AWAITING_TRANSPORT
        assert c.fee_total == 55.0

    def test_requester_reject_counter(self):
        reg = make_registry()
        c = _propose(reg)
        reg.provider_counter(c.contract_id, counter_fee=99.0)
        reg.requester_reject_counter(c.contract_id)
        assert c.status == StaffingStatus.REJECTED

    def test_cannot_approve_from_wrong_status(self):
        reg = make_registry()
        c = _propose(reg)
        reg.provider_reject(c.contract_id)
        with pytest.raises(ValueError):
            reg.provider_approve(c.contract_id)


# -------------------------------------------------------------------
# dispatch() and return date
# -------------------------------------------------------------------

class TestDispatch:
    def test_dispatch_sets_status_and_return_date(self):
        reg = make_registry()
        c = _propose(reg, duration_seasons=2)
        reg.provider_approve(c.contract_id)
        reg.dispatch(c.contract_id, year=0, season=1, num_seasons=4)
        assert c.status == StaffingStatus.DISPATCHED
        # dispatched season 1, duration 2 → return season 3
        assert c.return_year == 0
        assert c.return_season == 3

    def test_dispatch_return_wraps_year(self):
        reg = make_registry()
        c = _propose(reg, duration_seasons=3)
        reg.provider_approve(c.contract_id)
        reg.dispatch(c.contract_id, year=0, season=2, num_seasons=4)
        # season 2 + 3 = 5 → year 1, season 1
        assert c.return_year == 1
        assert c.return_season == 1

    def test_dispatch_stores_worker_ids(self):
        reg = make_registry()
        c = _propose(reg)
        reg.provider_approve(c.contract_id)
        reg.dispatch(c.contract_id, year=0, season=0, staff_worker_ids=[5, 6])
        assert c.staff_worker_ids == [5, 6]


# -------------------------------------------------------------------
# process_returns()
# -------------------------------------------------------------------

class TestProcessReturns:
    def test_process_returns_completes_due_contracts(self):
        reg = make_registry()
        c = _propose(reg, duration_seasons=1)
        reg.provider_approve(c.contract_id)
        reg.dispatch(c.contract_id, year=0, season=0, num_seasons=4)
        # return at year=0, season=1
        returned = reg.process_returns(0, 1)
        assert c in returned
        assert c.status == StaffingStatus.COMPLETED

    def test_process_returns_leaves_other_contracts_intact(self):
        reg = make_registry()
        c1 = _propose(reg, requester_id=1, duration_seasons=1)
        c2 = _propose(reg, requester_id=2, duration_seasons=2)
        for c in [c1, c2]:
            reg.provider_approve(c.contract_id)
            reg.dispatch(c.contract_id, year=0, season=0, num_seasons=4)
        reg.process_returns(0, 1)  # only c1 is due (0+1=season 1)
        assert c1.status == StaffingStatus.COMPLETED
        assert c2.status == StaffingStatus.DISPATCHED


# -------------------------------------------------------------------
# Population query helpers
# -------------------------------------------------------------------

class TestPopulationHelpers:
    def test_visiting_staff_counts_dispatched_contracts_at_host(self):
        reg = make_registry()
        c = _propose(reg, requester_id=1, provider_id=0, staff_count=2)
        reg.provider_approve(c.contract_id)
        reg.dispatch(c.contract_id, year=0, season=0)
        assert reg.visiting_staff(host_id=1) == 2
        assert reg.visiting_staff(host_id=0) == 0

    def test_visiting_staff_zero_when_not_dispatched(self):
        reg = make_registry()
        c = _propose(reg, requester_id=1, staff_count=3)
        # Still PROPOSED — not dispatched
        assert reg.visiting_staff(host_id=1) == 0

    def test_staff_away_from_home_counts_dispatched(self):
        reg = make_registry()
        c = _propose(reg, requester_id=1, provider_id=0, staff_count=2)
        reg.provider_approve(c.contract_id)
        reg.dispatch(c.contract_id, year=0, season=0)
        assert reg.staff_away_from_home(provider_id=0) == 2
        assert reg.staff_away_from_home(provider_id=1) == 0

    def test_visiting_staff_zero_after_completion(self):
        reg = make_registry()
        c = _propose(reg, requester_id=1, provider_id=0, staff_count=2, duration_seasons=1)
        reg.provider_approve(c.contract_id)
        reg.dispatch(c.contract_id, year=0, season=0, num_seasons=4)
        reg.process_returns(0, 1)
        assert reg.visiting_staff(host_id=1) == 0


# -------------------------------------------------------------------
# Query helpers
# -------------------------------------------------------------------

class TestQueryHelpers:
    def test_pending_for_provider_returns_proposed_contracts(self):
        reg = make_registry()
        c = _propose(reg, provider_id=0)
        assert c in reg.pending_for_provider(0)

    def test_pending_for_provider_excludes_approved(self):
        reg = make_registry()
        c = _propose(reg, provider_id=0)
        reg.provider_approve(c.contract_id)
        assert c not in reg.pending_for_provider(0)

    def test_active_for_player_includes_requester_and_provider(self):
        reg = make_registry()
        c = _propose(reg, requester_id=1, provider_id=0)
        assert c in reg.active_for_player(0)
        assert c in reg.active_for_player(1)

    def test_active_for_player_excludes_completed(self):
        reg = make_registry()
        c = _propose(reg, requester_id=1, provider_id=0, duration_seasons=1)
        reg.provider_approve(c.contract_id)
        reg.dispatch(c.contract_id, year=0, season=0, num_seasons=4)
        reg.process_returns(0, 1)
        assert c not in reg.active_for_player(1)

    def test_decisions_for_requester_surfaces_unacknowledged(self):
        reg = make_registry()
        c = _propose(reg, requester_id=1)
        reg.provider_reject(c.contract_id, reason="Full roster")
        decisions = reg.decisions_for_requester(1)
        assert c in decisions
        reg.acknowledge_decision(1, c.contract_id)
        assert c not in reg.decisions_for_requester(1)

    def test_contract_by_id(self):
        reg = make_registry()
        c = _propose(reg)
        assert reg.contract_by_id(c.contract_id) is c
        assert reg.contract_by_id(999) is None
