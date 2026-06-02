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
    CARGO_TRANSIT_SEASONS, MAX_CLASS_SIZE_PER_COURSE,
)
from .profession import (
    Profession, WorkerBand, band_of,
    EDUCATION_SEASONS, APPRENTICESHIP_SEASONS,
)


def away_seasons(profession: str) -> int:
    """Seasons a trainee is away for the given profession.

    Manager-band → university course duration (EDUCATION_SEASONS, e.g.
    Doctor 3, Nurse 1, others 2).  Technician-band → apprenticeship
    away-duration (APPRENTICESHIP_SEASONS, 1 season; the post-return 75%
    settling season is tracked on the Worker, not here).  Unknown
    professions fall back to 1 season.
    """
    try:
        prof = Profession(profession)
    except ValueError:
        return 1
    band = band_of(prof)
    if band == WorkerBand.MANAGER:
        return EDUCATION_SEASONS.get(prof, 2)
    if band == WorkerBand.TECHNICIAN:
        return APPRENTICESHIP_SEASONS.get(prof, 1)
    return 1


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
    tickets_supplied_by_requester: int = 0
    counter_message: str = ""
    priority: int = 0
    decline_reason: str = ""
    decline_year: int = -1
    decline_season: int = -1
    original_dollops_to_educator: float = 0.0
    decision_acknowledged: bool = False
    # Tick at which an Educator last skipped this request without deciding.
    # Prevents the same request from re-appearing multiple times in the same
    # review session (it will appear again next season).
    last_skipped_tick: int = -1

    def describe(self, player_names: dict[int, str]) -> str:
        sym = CURRENCY_SYMBOL
        req = player_names.get(self.requester_id, f"Player{self.requester_id}")
        edu = player_names.get(self.educator_id, f"Player{self.educator_id}")
        if self.transport_mode == "air_ticket":
            requester_tickets = min(
                max(0, self.tickets_supplied_by_requester), len(self.worker_ids)
            )
            educator_tickets = len(self.worker_ids) - requester_tickets
            transport_str = (
                f"{len(self.worker_ids)} air ticket(s): requester supplies "
                f"{requester_tickets}, Educator supplies {educator_tickets}"
            )
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

    @staticmethod
    def _classrooms_needed(num_trainees: int) -> int:
        if num_trainees <= 0:
            return 0
        return -(-num_trainees // MAX_CLASS_SIZE_PER_COURSE)

    @staticmethod
    def _cohort_year_season(
        req: TrainingRequest,
        current_year: int | None = None,
        current_season: int | None = None,
    ) -> tuple[int, int]:
        if req.status == TrainingStatus.DISPATCHED:
            return req.dispatched_year, req.dispatched_season
        if current_year is not None and current_season is not None:
            return current_year, current_season
        return req.proposed_year, req.proposed_season

    def cohort_trainees_committed(
        self,
        educator_id: int,
        profession: str,
        year: int,
        season: int,
        exclude_batch_id: int | None = None,
    ) -> int:
        """Count committed trainees in one course-running cohort."""
        return sum(
            len(r.worker_ids)
            for r in self._requests
            if r.educator_id == educator_id
            and r.target_profession == profession
            and r.status in (TrainingStatus.AWAITING_TRANSPORT, TrainingStatus.DISPATCHED)
            and r.batch_id != exclude_batch_id
            and self._cohort_year_season(r, year, season) == (year, season)
        )

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
        tickets_supplied_by_requester: int = 0,
    ) -> TrainingRequest:
        count = len(worker_ids)
        if len(set(worker_ids)) != count:
            raise TrainingCapacityError("Training request contains duplicate worker ids.")
        already_committed = self.reserved_worker_ids(requester_id).intersection(worker_ids)
        if already_committed:
            ids = ", ".join(str(worker_id) for worker_id in sorted(already_committed))
            raise TrainingCapacityError(
                f"Worker(s) already committed to a training request: {ids}."
            )
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
            tickets_supplied_by_requester=max(
                0, min(tickets_supplied_by_requester, len(worker_ids))
            ),
            original_dollops_to_educator=dollops_to_educator,
        )
        self._requests.append(req)
        self._next_id += 1
        return req

    def educator_approve(self, batch_id: int) -> TrainingRequest:
        req = self._get(batch_id, TrainingStatus.AWAITING_EDUCATOR)
        req.status = TrainingStatus.AWAITING_TRANSPORT
        return req

    def educator_reject(
        self,
        batch_id: int,
        reason: str = "",
        year: int = -1,
        season: int = -1,
    ) -> TrainingRequest:
        req = self._get(batch_id, TrainingStatus.AWAITING_EDUCATOR)
        self._record_decision(req, reason, year, season)
        req.status = TrainingStatus.REJECTED
        return req

    def educator_counter(
        self,
        batch_id: int,
        dollops_to_educator: float,
        message: str = "",
        reason: str = "",
        year: int = -1,
        season: int = -1,
    ) -> TrainingRequest:
        req = self._get(batch_id, TrainingStatus.AWAITING_EDUCATOR)
        if req.original_dollops_to_educator == 0.0:
            req.original_dollops_to_educator = req.dollops_to_educator
        req.dollops_to_educator = dollops_to_educator
        req.counter_message = message.strip()
        self._record_decision(req, reason or req.counter_message, year, season)
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

    def requester_counter(
        self, batch_id: int, new_fee: float, message: str = ""
    ) -> TrainingRequest:
        """Counter a counter-offer: requester proposes a different price, sending
        the request back to AWAITING_EDUCATOR status for the Educator to review."""
        req = self._get(batch_id, TrainingStatus.COUNTERED)
        req.dollops_to_educator = new_fee
        req.counter_message = message.strip()
        req.decision_acknowledged = True
        req.status = TrainingStatus.AWAITING_EDUCATOR
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
        # Profession-dependent course/apprenticeship duration (Phase 3).
        away = away_seasons(req.target_profession)
        # Cargo adds one extra season of transit delay
        extra = CARGO_TRANSIT_SEASONS if req.transport_mode == "cargo" else 0
        ret_season = season + away + extra
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

    def drop_worker(self, worker_id: int) -> None:
        """Remove a worker from any non-terminal training request.

        Used when a worker retires while away at training: they no
        longer exist, so they must not 'return'.  A request left with
        no workers is rejected (frees its slot/Course accounting).
        """
        for r in self._requests:
            if r.status in (TrainingStatus.COMPLETED, TrainingStatus.REJECTED):
                continue
            if worker_id in r.worker_ids:
                r.worker_ids = [w for w in r.worker_ids if w != worker_id]
                if not r.worker_ids:
                    r.status = TrainingStatus.REJECTED

    def _courses_in_flight(
        self,
        educator_id: int,
        band: WorkerBand,
        year: int | None = None,
        season: int | None = None,
    ) -> int:
        cohorts: dict[tuple[str, int, int], int] = {}
        for r in self._requests:
            if (
                r.educator_id != educator_id
                or r.status not in (
                    TrainingStatus.AWAITING_TRANSPORT,
                    TrainingStatus.DISPATCHED,
                )
                or band_of(r.target_profession) != band
            ):
                continue
            cohort_year, cohort_season = self._cohort_year_season(r, year, season)
            key = (r.target_profession, cohort_year, cohort_season)
            cohorts[key] = cohorts.get(key, 0) + len(r.worker_ids)
        return sum(self._classrooms_needed(count) for count in cohorts.values())

    def manager_courses_in_flight(
        self,
        educator_id: int,
        year: int | None = None,
        season: int | None = None,
    ) -> int:
        """Count committed Manager-tier courses for this Educator.

        Staff are reserved as soon as the Educator approves, so both
        AWAITING_TRANSPORT and DISPATCHED batches count until completion
        or rejection.
        """
        return self._courses_in_flight(educator_id, WorkerBand.MANAGER, year, season)

    def technical_courses_in_flight(
        self,
        educator_id: int,
        year: int | None = None,
        season: int | None = None,
    ) -> int:
        """Count committed Technician-tier courses for this Educator."""
        return self._courses_in_flight(
            educator_id, WorkerBand.TECHNICIAN, year, season
        )

    def technical_trainees_in_flight(self, educator_id: int) -> int:
        """Sum of trainee headcount across committed Technician-tier
        batches for this Educator (AWAITING_TRANSPORT + DISPATCHED).

        Used to gate against the Technical Workshop physical-plant
        capacity (per-workshop trainee seats, not per-course). A 4-trainee
        batch and a 2-trainee batch together fill 6 workshop seats — fits
        in one Technical Workshop (cap 6), would need 2 workshops if a
        7th trainee tried to admit concurrently.
        """
        return sum(
            len(r.worker_ids)
            for r in self._requests
            if r.educator_id == educator_id
            and r.status in (TrainingStatus.AWAITING_TRANSPORT, TrainingStatus.DISPATCHED)
            and band_of(r.target_profession) == WorkerBand.TECHNICIAN
        )

    def visiting_trainees(self, educator_id: int) -> int:
        """Headcount currently on campus at this Educator's island.

        Counts only trainees physically away from their home island
        (status DISPATCHED) sent by *other* islands — self-training uses
        the Educator's own residents, already counted in its population.
        This is the "campus load" figure: extra mouths the Education
        Island must feed until the trainees return (consumed by the §21
        balance-aware sustenance model — see
        requirements/codex-tasks/sustenance-model.md).
        """
        return sum(
            len(r.worker_ids)
            for r in self._requests
            if r.educator_id == educator_id
            and r.requester_id != educator_id
            and r.status == TrainingStatus.DISPATCHED
        )

    def trainees_away_from_home(self, requester_id: int) -> int:
        """Headcount physically away from a requester's home island.

        These residents are already counted as campus load at the
        Educator, so the home island should not also feed them while
        their request is dispatched.
        """
        return sum(
            len(r.worker_ids)
            for r in self._requests
            if r.requester_id == requester_id
            and r.requester_id != r.educator_id
            and r.status == TrainingStatus.DISPATCHED
        )

    def reserved_worker_ids(self, requester_id: int) -> set[int]:
        """Workers already committed to non-terminal training requests."""
        reserved: set[int] = set()
        for req in self._requests:
            if req.requester_id != requester_id:
                continue
            if req.status in (TrainingStatus.COMPLETED, TrainingStatus.REJECTED):
                continue
            reserved.update(req.worker_ids)
        return reserved

    def pending_for_requester(self, requester_id: int) -> list[TrainingRequest]:
        """Requests this player filed that are still awaiting Educator action.

        Used by the AI Manufacturer's indirect-demand check (so a pending
        training request creates upstream LaboratoryEquipment demand) and
        by the requester-side dashboard payload.  (2026-05-27
        training-expertise-deadlock brief Layer 1 + Layer 3.)
        """
        return [
            r for r in self._requests
            if r.requester_id == requester_id
            and r.status == TrainingStatus.AWAITING_EDUCATOR
        ]

    def pending_for_educator(self, educator_id: int) -> list[TrainingRequest]:
        return [
            r for r in self._requests
            if r.educator_id == educator_id
            and r.status == TrainingStatus.AWAITING_EDUCATOR
        ]

    def sorted_pending_for_educator(self, educator_id: int) -> list[TrainingRequest]:
        return sorted(
            self.pending_for_educator(educator_id),
            key=lambda r: (r.priority, r.batch_id),
        )

    def reorder_pending(self, educator_id: int, ordered_batch_ids: list[int]) -> None:
        pending = {req.batch_id: req for req in self.pending_for_educator(educator_id)}
        seen: set[int] = set()
        for idx, batch_id in enumerate(ordered_batch_ids):
            req = pending.get(batch_id)
            if req is None:
                continue
            req.priority = idx
            seen.add(batch_id)
        next_priority = len(seen)
        for req in self.sorted_pending_for_educator(educator_id):
            if req.batch_id in seen:
                continue
            req.priority = next_priority
            next_priority += 1

    def countered_for_requester(self, requester_id: int) -> list[TrainingRequest]:
        return [
            r for r in self._requests
            if r.requester_id == requester_id
            and r.status == TrainingStatus.COUNTERED
        ]

    def decisions_for_requester(self, requester_id: int) -> list[TrainingRequest]:
        return [
            r for r in self._requests
            if r.requester_id == requester_id
            and r.status in (TrainingStatus.COUNTERED, TrainingStatus.REJECTED)
            and not r.decision_acknowledged
        ]

    def acknowledge_decision(self, requester_id: int, batch_id: int) -> bool:
        for req in self._requests:
            if req.batch_id == batch_id and req.requester_id == requester_id:
                req.decision_acknowledged = True
                return True
        return False

    def request_by_id(self, batch_id: int) -> TrainingRequest | None:
        return next((r for r in self._requests if r.batch_id == batch_id), None)

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

    def _record_decision(
        self, req: TrainingRequest, reason: str, year: int, season: int
    ) -> None:
        req.decline_reason = reason.strip()
        req.decline_year = year
        req.decline_season = season
        req.decision_acknowledged = False

    def _get(self, batch_id: int, expected_status: TrainingStatus) -> TrainingRequest:
        for r in self._requests:
            if r.batch_id == batch_id:
                if r.status != expected_status:
                    raise ValueError(
                        f"Request #{batch_id} is {r.status.value}, expected {expected_status.value}"
                    )
                return r
        raise KeyError(f"No training request with batch_id={batch_id}")
