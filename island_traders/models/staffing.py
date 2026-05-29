"""
Medical Staffing Contracts for Island Traders.

Any island may request Doctors or Nurses from the Healthcare island for a
fixed-term contract (1–4 seasons).  During the contract the staff are away
from the provider's workforce and are counted as extra residents at the host
island (consuming Food / sustenance there).  They need PassengerSeats to
travel both ways.

Status flow:
  PROPOSED → (provider approves) → AWAITING_TRANSPORT
           → (provider counters)  → COUNTERED
                                    → (requester accepts) → AWAITING_TRANSPORT
                                    → (requester rejects) → REJECTED
           → (provider rejects)   → REJECTED
  AWAITING_TRANSPORT → (dispatched) → DISPATCHED
  DISPATCHED → (season reached)     → COMPLETED
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum


class StaffingStatus(Enum):
    PROPOSED            = "proposed"
    COUNTERED           = "countered"
    AWAITING_TRANSPORT  = "awaiting_transport"
    DISPATCHED          = "dispatched"
    COMPLETED           = "completed"
    REJECTED            = "rejected"


# Terminal statuses — contracts in these states no longer affect game-state.
_TERMINAL = {StaffingStatus.COMPLETED, StaffingStatus.REJECTED}


@dataclass
class StaffingContract:
    contract_id: int
    requester_id: int
    provider_id: int            # always the Doctor/Healthcare island
    profession: str             # "Doctor" | "Nurse" (or other medical profession)
    staff_count: int
    duration_seasons: int       # how long the staff will be away (1–4)
    fee_total: float            # Dollops paid by requester to provider on dispatch
    tickets_required: int       # PassengerSeats needed (round-trip: staff_count × 2)
    tickets_supplied_by_requester: int  # how many the requester is supplying
    status: StaffingStatus = StaffingStatus.PROPOSED
    proposed_year: int = -1
    proposed_season: int = -1
    dispatched_year: int = -1
    dispatched_season: int = -1
    return_year: int = -1
    return_season: int = -1
    # Populated at dispatch time from the provider's available workers
    staff_worker_ids: list[int] = field(default_factory=list)
    # Counter-offer fields
    counter_fee: float = 0.0
    counter_message: str = ""
    # Decline info
    decline_reason: str = ""
    decision_acknowledged: bool = False
    original_fee: float = 0.0

    @property
    def tickets_supplied_by_provider(self) -> int:
        return max(0, self.tickets_required - self.tickets_supplied_by_requester)


class StaffingRegistry:
    """Central ledger of all staffing contracts in a game session."""

    def __init__(self) -> None:
        self._contracts: list[StaffingContract] = []
        self._next_id: int = 0

    # ------------------------------------------------------------------
    # CRUD / lifecycle
    # ------------------------------------------------------------------

    def propose(
        self,
        requester_id: int,
        provider_id: int,
        profession: str,
        staff_count: int,
        duration_seasons: int,
        fee_total: float,
        year: int,
        season: int,
        tickets_supplied_by_requester: int = 0,
    ) -> StaffingContract:
        """Requester proposes a staffing contract to the provider island."""
        if staff_count < 1:
            raise ValueError("Staff count must be at least 1.")
        if duration_seasons < 1:
            raise ValueError("Duration must be at least 1 season.")
        # Round-trip tickets: each staff member needs a seat each way.
        tickets_required = staff_count * 2
        contract = StaffingContract(
            contract_id=self._next_id,
            requester_id=requester_id,
            provider_id=provider_id,
            profession=profession,
            staff_count=staff_count,
            duration_seasons=duration_seasons,
            fee_total=fee_total,
            tickets_required=tickets_required,
            tickets_supplied_by_requester=max(
                0, min(tickets_supplied_by_requester, tickets_required)
            ),
            proposed_year=year,
            proposed_season=season,
            original_fee=fee_total,
        )
        self._contracts.append(contract)
        self._next_id += 1
        return contract

    def provider_approve(self, contract_id: int) -> StaffingContract:
        c = self._get(contract_id, StaffingStatus.PROPOSED)
        c.status = StaffingStatus.AWAITING_TRANSPORT
        return c

    def provider_reject(
        self,
        contract_id: int,
        reason: str = "",
    ) -> StaffingContract:
        c = self._get(contract_id, StaffingStatus.PROPOSED)
        c.decline_reason = reason.strip()
        c.decision_acknowledged = False
        c.status = StaffingStatus.REJECTED
        return c

    def provider_counter(
        self,
        contract_id: int,
        counter_fee: float,
        message: str = "",
    ) -> StaffingContract:
        c = self._get(contract_id, StaffingStatus.PROPOSED)
        c.counter_fee = counter_fee
        c.counter_message = message.strip()
        c.decision_acknowledged = False
        c.status = StaffingStatus.COUNTERED
        return c

    def requester_accept_counter(self, contract_id: int) -> StaffingContract:
        c = self._get(contract_id, StaffingStatus.COUNTERED)
        c.fee_total = c.counter_fee
        c.status = StaffingStatus.AWAITING_TRANSPORT
        return c

    def requester_reject_counter(self, contract_id: int) -> StaffingContract:
        c = self._get(contract_id, StaffingStatus.COUNTERED)
        c.decline_reason = "Requester declined counter-offer."
        c.decision_acknowledged = False
        c.status = StaffingStatus.REJECTED
        return c

    def dispatch(
        self,
        contract_id: int,
        year: int,
        season: int,
        num_seasons: int = 4,
        staff_worker_ids: list[int] | None = None,
    ) -> StaffingContract:
        """Mark staff as dispatched; calculate return date."""
        c = self._get(contract_id, StaffingStatus.AWAITING_TRANSPORT)
        c.status = StaffingStatus.DISPATCHED
        c.dispatched_year = year
        c.dispatched_season = season
        if staff_worker_ids is not None:
            c.staff_worker_ids = list(staff_worker_ids)
        ret_season = season + c.duration_seasons
        c.return_year = year + ret_season // num_seasons
        c.return_season = ret_season % num_seasons
        return c

    def process_returns(self, year: int, season: int) -> list[StaffingContract]:
        """Mark all contracts whose return date matches as COMPLETED."""
        due = [
            c for c in self._contracts
            if c.status == StaffingStatus.DISPATCHED
            and c.return_year == year
            and c.return_season == season
        ]
        for c in due:
            c.status = StaffingStatus.COMPLETED
        return due

    def acknowledge_decision(self, requester_id: int, contract_id: int) -> bool:
        for c in self._contracts:
            if c.contract_id == contract_id and c.requester_id == requester_id:
                c.decision_acknowledged = True
                return True
        return False

    # ------------------------------------------------------------------
    # Population / workforce queries
    # ------------------------------------------------------------------

    def visiting_staff(self, host_id: int) -> int:
        """Staff currently on the host island (physically away from provider).

        Used for sustenance calculations — these staff must be fed by the
        host island for the duration of the contract.
        """
        return sum(
            c.staff_count
            for c in self._contracts
            if c.requester_id == host_id
            and c.status == StaffingStatus.DISPATCHED
        )

    def staff_away_from_home(self, provider_id: int) -> int:
        """Staff from this provider island currently on contract elsewhere.

        The provider's workforce is reduced by this count while they are away.
        """
        return sum(
            c.staff_count
            for c in self._contracts
            if c.provider_id == provider_id
            and c.status == StaffingStatus.DISPATCHED
        )

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def pending_for_provider(self, provider_id: int) -> list[StaffingContract]:
        """Contracts awaiting the provider's decision."""
        return [
            c for c in self._contracts
            if c.provider_id == provider_id
            and c.status == StaffingStatus.PROPOSED
        ]

    def active_for_player(self, player_id: int) -> list[StaffingContract]:
        """All non-terminal contracts involving this player (as requester or provider)."""
        return [
            c for c in self._contracts
            if (c.requester_id == player_id or c.provider_id == player_id)
            and c.status not in _TERMINAL
        ]

    def decisions_for_requester(self, requester_id: int) -> list[StaffingContract]:
        """Unacknowledged counter/reject decisions the requester needs to see."""
        return [
            c for c in self._contracts
            if c.requester_id == requester_id
            and c.status in (StaffingStatus.COUNTERED, StaffingStatus.REJECTED)
            and not c.decision_acknowledged
        ]

    def contract_by_id(self, contract_id: int) -> StaffingContract | None:
        return next((c for c in self._contracts if c.contract_id == contract_id), None)

    def all_contracts(self) -> list[StaffingContract]:
        return list(self._contracts)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get(self, contract_id: int, expected: StaffingStatus) -> StaffingContract:
        for c in self._contracts:
            if c.contract_id == contract_id:
                if c.status != expected:
                    raise ValueError(
                        f"Contract #{contract_id} is {c.status.value}, "
                        f"expected {expected.value}"
                    )
                return c
        raise KeyError(f"No staffing contract with contract_id={contract_id}")
