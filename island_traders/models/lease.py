from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from ..constants import CURRENCY_SYMBOL
from .capacity import CapitalItem
from .loan import posted_funding_rates


class LeaseStatus(Enum):
    ACTIVE = "active"
    AWAITING_BUYOUT = "awaiting_buyout"
    REPOSSESSED = "repossessed"
    BUYOUT_DEFAULTED = "buyout_defaulted"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


@dataclass
class Lease:
    lease_id: int
    item_id: str
    lessee_id: int
    lessor_id: int
    started_year: int
    started_season: int
    term_years: int
    annual_payment: float
    buyout_payment: float
    locked_lease_rate: float
    payments_made: int = 0
    last_payment_year: int = -1
    status: LeaseStatus = LeaseStatus.ACTIVE
    repossessed_year: int = -1
    repossessed_season: int = -1
    return_year: int = -1
    return_season: int = -1

    @property
    def maturity_year(self) -> int:
        return self.started_year + self.term_years

    @property
    def maturity_season(self) -> int:
        return self.started_season

    def annual_due(self, year: int, season: int) -> bool:
        return (
            self.status == LeaseStatus.ACTIVE
            and season == 0
            and self.payments_made < self.term_years
            and self.last_payment_year < year
        )

    def buyout_due(self, year: int, season: int) -> bool:
        return (
            self.status == LeaseStatus.AWAITING_BUYOUT
            and season == 0
            and year >= self.maturity_year
        )

    def summary(self, item_name: str, lessee_name: str, lessor_name: str) -> str:
        return (
            f"Lease #{self.lease_id}: {lessee_name} leases {item_name} from "
            f"{lessor_name} for {self.annual_payment:.1f} {CURRENCY_SYMBOL}/year "
            f"+ {self.buyout_payment:.1f} {CURRENCY_SYMBOL} buyout "
            f"[{self.status.value}]"
        )


def lease_quote(item: CapitalItem, year: int, season: int, cycle=None) -> dict:
    if not item.lease_terms:
        raise ValueError(f"{item.item_id} is not lease-eligible")
    term_years = int(item.lease_terms.get("term_years", 3))
    residual_fraction = float(item.lease_terms.get("residual_fraction", 0.25))
    margin = float(item.lease_terms.get("rate_margin", 0.02))
    posted_rates = posted_funding_rates(year, season, cycle=cycle)
    posted_rate = posted_rates.get(term_years, posted_rates[3])
    lease_rate = round(posted_rate + margin, 4)
    buyout = round(item.cost * residual_fraction, 1)
    annual = round((item.cost - buyout) / term_years * (1 + lease_rate), 1)
    return {
        "term_years": term_years,
        "posted_rate": posted_rate,
        "locked_lease_rate": lease_rate,
        "annual_payment": annual,
        "buyout_payment": buyout,
    }


@dataclass
class LeaseLedger:
    leases: list[Lease] = field(default_factory=list)
    _next_id: int = 0

    def create_lease(
        self,
        item_id: str,
        lessee_id: int,
        lessor_id: int,
        year: int,
        season: int,
        term_years: int,
        annual_payment: float,
        buyout_payment: float,
        locked_lease_rate: float,
        payments_made: int = 0,
        last_payment_year: int = -1,
    ) -> Lease:
        lease = Lease(
            lease_id=self._next_id,
            item_id=item_id,
            lessee_id=lessee_id,
            lessor_id=lessor_id,
            started_year=year,
            started_season=season,
            term_years=term_years,
            annual_payment=annual_payment,
            buyout_payment=buyout_payment,
            locked_lease_rate=locked_lease_rate,
            payments_made=payments_made,
            last_payment_year=last_payment_year,
        )
        self.leases.append(lease)
        self._next_id += 1
        if lease.payments_made >= lease.term_years:
            lease.status = LeaseStatus.AWAITING_BUYOUT
        return lease

    def active_leases_for(self, player_id: int) -> list[Lease]:
        return [
            l for l in self.leases
            if l.status in (LeaseStatus.ACTIVE, LeaseStatus.AWAITING_BUYOUT, LeaseStatus.REPOSSESSED)
            and (l.lessee_id == player_id or l.lessor_id == player_id)
        ]

    def repossessed_leases_for(self, player_id: int) -> list[Lease]:
        return [
            l for l in self.leases
            if l.status == LeaseStatus.REPOSSESSED and l.lessee_id == player_id
        ]

    def due_leases(self, year: int, season: int) -> list[Lease]:
        return [
            l for l in self.leases
            if l.annual_due(year, season) or l.buyout_due(year, season)
        ]

    def all_leases(self) -> list[Lease]:
        return list(self.leases)

    def get(self, lease_id: int) -> Lease:
        for lease in self.leases:
            if lease.lease_id == lease_id:
                return lease
        raise KeyError(f"No lease with id {lease_id}")

    def make_payment(self, lease_id: int, year: int, season: int) -> Lease:
        lease = self.get(lease_id)
        lease.payments_made += 1
        lease.last_payment_year = year
        lease.return_year = -1
        lease.return_season = -1
        if lease.payments_made >= lease.term_years:
            lease.status = LeaseStatus.AWAITING_BUYOUT
        else:
            lease.status = LeaseStatus.ACTIVE
        return lease

    def repossess(self, lease_id: int, year: int, season: int) -> Lease:
        lease = self.get(lease_id)
        lease.status = LeaseStatus.REPOSSESSED
        lease.repossessed_year = year
        lease.repossessed_season = season
        lease.return_year = -1
        lease.return_season = -1
        return lease

    def schedule_reinstatement(self, lease_id: int, year: int, season: int) -> Lease:
        lease = self.get(lease_id)
        next_season = season + 1
        lease.return_year = year + next_season // 4
        lease.return_season = next_season % 4
        return lease

    def reinstate(self, lease_id: int, year: int, season: int) -> Lease:
        lease = self.get(lease_id)
        lease.status = LeaseStatus.ACTIVE
        lease.return_year = -1
        lease.return_season = -1
        lease.repossessed_year = -1
        lease.repossessed_season = -1
        lease.last_payment_year = year
        return lease

    def complete(self, lease_id: int) -> Lease:
        lease = self.get(lease_id)
        lease.status = LeaseStatus.COMPLETED
        return lease

    def buyout_default(self, lease_id: int) -> Lease:
        lease = self.get(lease_id)
        lease.status = LeaseStatus.BUYOUT_DEFAULTED
        return lease
