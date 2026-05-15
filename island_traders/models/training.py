"""
Training system for Island Traders.

Workers are sent to the University (Education Island) for one season, then
return with a specific profession at Basic level (or advance one level if
already a professional in that field).

The University has per-profession annual training quotas; the Professor
profession also has a per-season cap.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum

from ..constants import (
    UNIVERSITY_CAPACITY, UNIVERSITY_SEASONAL_CAP, CURRENCY_SYMBOL,
    CARGO_TRANSIT_SEASONS,
)


class TrainingCapacityError(Exception):
    pass


class TrainingStatus(Enum):
    AWAITING_EDUCATOR   = "awaiting_educator"
    COUNTERED           = "countered"
    AWAITING_TRANSPORT  = "awaiting_transport"
    DISPATCHED          = "dispatched"
    COMPLETED           = "completed"
    REJECTED            = "rejected"


@dataclass
class TrainingRequest:
    batch_id: int
    requester_id: int
    worker_ids: list[int]
    educator_id: int
    transporter_id: int | None
    dollops_to_educator: float
    dollops_to_transporter: float
    target_profession: str          # profession workers will graduate into
    proposed_year: int = -1
    proposed_season: int = -1       # for per-season caps (e.g. Professor)
    status: TrainingStatus = TrainingStatus.AWAITING_EDUCATOR
    dispatched_year: int = -1
    dispatched_season: int = -1
    return_year: int = -1
    return_season: int = -1
    # "air_ticket" is the current rule: Educator supplies 1 PassengerSeats per
    # trainee, with the return journey assumed. Older saved games may still
    # contain "transporter" / "flight" / "cargo".
    transport_mode: str = "air_ticket"
    counter_message: str = ""

    def describe(self, player_names: dict[int, str]) -> str:
        sym = CURRENCY_SYMBOL
        req = player_names.get(self.requester_id, f"Player{self.requester_id}")
        edu = player_names.get(self.educator_id, f"Player{self.educator_id}")
        if self.transport_mode == "air_ticket":
            transport_str = f"{len(self.worker_ids)} air ticket(s), Educator supplied"
        elif self.transport_mode == "flight":
            transport_str = f"Flight ({self.dollops_to_transporter:.0f} {sym})"
        elif self.transport_mode == "cargo":
            transport_str = "Cargo vessel (free, +1 season)"
        elif self.transport_mode == "self_training":
            transport_str = "on-island (no transport, no fee)"
        else:
            trn = (
                player_names.get(self.transporter_id, f"Player{self.transporter_id}")
                if self.transporter_id is not None else "unassigned"
            )
            transport_str = f"{trn} ({self.dollops_to_transporter:.0f} {sym})"
        return (
            f"TrainingRequest #{self.batch_id}: {req} → {len(self.worker_ids)} × {self.target_profession}  "
            f"| Educator: {edu} ({self.dollops_to_educator:.0f} {sym})  "
            f"| Transport: {transport_str}  "
            f"| Status: {self.status.value}"
            f"{'  | Message: ' + self.counter_message if self.counter_message else ''}"
        )


class TrainingRegistry:
    """Central ledger of all training requests in a game session."""

    def __init__(self) -> None:
        self._requests: list[TrainingRequest] = []
        self._next_id: int = 0

    # ------------------------------------------------------------------
    # Capacity queries
    # ------------------------------------------------------------------

    def trained_this_year(self, year: int, profession: str) -> int:
        """Count workers actively being trained (or already trained) in the given
        profession this year — used to check against UNIVERSITY_CAPACITY."""
        return sum(
            len(r.worker_ids)
            for r in self._requests
            if r.proposed_year == year
            and r.target_profession == profession
            and r.status not in (TrainingStatus.REJECTED,)
        )

    def trained_this_season(self, year: int, season: int, profession: str) -> int:
        """For professions with per-season caps (e.g. Professor)."""
        return sum(
            len(r.worker_ids)
            for r in self._requests
            if r.proposed_year == year
            and r.proposed_season == season
            and r.target_profession == profession
            and r.status not in (TrainingStatus.REJECTED,)
        )

    def capacity_remaining(self, year: int, season: int, profession: str) -> int:
        """How many more workers can be trained in this profession this year."""
        annual_cap = UNIVERSITY_CAPACITY.get(profession, 0)
        seasonal_cap = UNIVERSITY_SEASONAL_CAP.get(profession)

        annual_remaining = annual_cap - self.trained_this_year(year, profession)
        if seasonal_cap is not None:
            seasonal_remaining = seasonal_cap - self.trained_this_season(year, season, profession)
            return max(0, min(annual_remaining, seasonal_remaining))
        return max(0, annual_remaining)

    def capacity_summary(self, year: int, season: int) -> dict[str, dict]:
        """Return capacity status for all professions."""
        result = {}
        for prof, cap in UNIVERSITY_CAPACITY.items():
            trained = self.trained_this_year(year, prof)
            seasonal_cap = UNIVERSITY_SEASONAL_CAP.get(prof)
            remaining = self.capacity_remaining(year, season, prof)
            result[prof] = {
                "annual_cap": cap,
                "trained": trained,
                "remaining": remaining,
                "seasonal_cap": seasonal_cap,
            }
        return result

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def propose(
        self,
        requester_id: int,
        worker_ids: list[int],
        educator_id: int,
        dollops_to_educator: float,
        dollops_to_transporter: float = 0.0,
        target_profession: str = "Unskilled",
        year: int = 0,
        season: int = 0,
        transport_mode: str = "transporter",
    ) -> TrainingRequest:
        count = len(worker_ids)
        remaining = self.capacity_remaining(year, season, target_profession)
        if remaining <= 0:
            annual_cap = UNIVERSITY_CAPACITY.get(target_profession, 0)
            seasonal_cap = UNIVERSITY_SEASONAL_CAP.get(target_profession)
            if seasonal_cap:
                raise TrainingCapacityError(
                    f"University {target_profession} intake is full this season "
                    f"(seasonal cap: {seasonal_cap})."
                )
            raise TrainingCapacityError(
                f"University {target_profession} intake is full for this year "
                f"(annual cap: {annual_cap})."
            )
        if count > remaining:
            raise TrainingCapacityError(
                f"Only {remaining} {target_profession} slot(s) remaining this year "
                f"(requested {count})."
            )

        req = TrainingRequest(
            batch_id=self._next_id,
            requester_id=requester_id,
            worker_ids=list(worker_ids),
            educator_id=educator_id,
            transporter_id=None,
            dollops_to_educator=dollops_to_educator,
            dollops_to_transporter=dollops_to_transporter,
            target_profession=target_profession,
            proposed_year=year,
            proposed_season=season,
            transport_mode=transport_mode,
        )
        self._requests.append(req)
        self._next_id += 1
        return req

    def educator_approve(self, batch_id: int) -> TrainingRequest:
        req = self._get(batch_id, TrainingStatus.AWAITING_EDUCATOR)
        req.status = TrainingStatus.AWAITING_TRANSPORT
        return req

    def educator_reject(self, batch_id: int) -> TrainingRequest:
        req = self._get(batch_id, TrainingStatus.AWAITING_EDUCATOR)
        req.status = TrainingStatus.REJECTED
        return req

    def educator_counter(
        self, batch_id: int, dollops_to_educator: float, message: str = ""
    ) -> TrainingRequest:
        req = self._get(batch_id, TrainingStatus.AWAITING_EDUCATOR)
        req.dollops_to_educator = dollops_to_educator
        req.counter_message = message.strip()
        req.status = TrainingStatus.COUNTERED
        return req

    def requester_accept_counter(self, batch_id: int) -> TrainingRequest:
        req = self._get(batch_id, TrainingStatus.COUNTERED)
        req.status = TrainingStatus.AWAITING_TRANSPORT
        return req

    def requester_reject_counter(self, batch_id: int) -> TrainingRequest:
        req = self._get(batch_id, TrainingStatus.COUNTERED)
        req.status = TrainingStatus.REJECTED
        return req

    def arrange_transport(
        self, batch_id: int, transporter_id: int, dollop_amount: float | None = None
    ) -> TrainingRequest:
        req = self._get(batch_id, TrainingStatus.AWAITING_TRANSPORT)
        req.transporter_id = transporter_id
        if dollop_amount is not None:
            req.dollops_to_transporter = dollop_amount
        return req

    def dispatch(
        self, batch_id: int, year: int, season: int, num_seasons: int = 4
    ) -> TrainingRequest:
        req = self._get(batch_id, TrainingStatus.AWAITING_TRANSPORT)
        req.status = TrainingStatus.DISPATCHED
        req.dispatched_year = year
        req.dispatched_season = season
        # Cargo adds one extra season of transit delay
        extra = CARGO_TRANSIT_SEASONS if req.transport_mode == "cargo" else 0
        ret_season = season + 1 + extra
        ret_year = year + ret_season // num_seasons
        req.return_year = ret_year
        req.return_season = ret_season % num_seasons
        return req

    def process_returns(self, year: int, season: int) -> list[TrainingRequest]:
        due = [
            r for r in self._requests
            if r.status == TrainingStatus.DISPATCHED
            and r.return_year == year
            and r.return_season == season
        ]
        for r in due:
            r.status = TrainingStatus.COMPLETED
        return due

    def pending_for_educator(self, educator_id: int) -> list[TrainingRequest]:
        return [
            r for r in self._requests
            if r.educator_id == educator_id
            and r.status == TrainingStatus.AWAITING_EDUCATOR
        ]

    def countered_for_requester(self, requester_id: int) -> list[TrainingRequest]:
        return [
            r for r in self._requests
            if r.requester_id == requester_id
            and r.status == TrainingStatus.COUNTERED
        ]

    def pending_transport(self) -> list[TrainingRequest]:
        return [r for r in self._requests if r.status == TrainingStatus.AWAITING_TRANSPORT]

    def active_for_player(self, player_id: int) -> list[TrainingRequest]:
        return [
            r for r in self._requests
            if r.requester_id == player_id
            and r.status not in (TrainingStatus.COMPLETED, TrainingStatus.REJECTED)
        ]

    def all_requests(self) -> list[TrainingRequest]:
        return list(self._requests)

    def _get(self, batch_id: int, expected_status: TrainingStatus) -> TrainingRequest:
        for r in self._requests:
            if r.batch_id == batch_id:
                if r.status != expected_status:
                    raise ValueError(
                        f"Request #{batch_id} is {r.status.value}, expected {expected_status.value}"
                    )
                return r
        raise KeyError(f"No training request with batch_id={batch_id}")
