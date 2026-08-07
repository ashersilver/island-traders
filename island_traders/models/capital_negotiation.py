from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class CapitalNegotiationStatus(Enum):
    PROPOSED = "proposed"
    COUNTERED = "countered"
    QUEUED = "queued"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    # Buyer could not pay the balance once the build was ready: the deposit is
    # forfeit to the manufacturer, who keeps the goods to resell at list price.
    DEFAULTED = "defaulted"


ACTIVE_CAPITAL_NEGOTIATION_STATUSES = {
    CapitalNegotiationStatus.PROPOSED,
    CapitalNegotiationStatus.COUNTERED,
    CapitalNegotiationStatus.QUEUED,
}


@dataclass
class CapitalOrderNegotiation:
    negotiation_id: int
    buyer_id: int
    manufacturer_id: int
    item_id: str
    maintenance_term_years: int
    predictive_maintenance: bool
    spares_kits: int
    expedited_eligible: bool
    financing: bool
    list_price: float
    recommended_total: float
    buyer_offer: float
    units_required: int = 0
    units_short_at_order: int = 0
    # Cash the buyer put down when the order was placed. Applied against the
    # total on settlement; forfeit to the manufacturer if the buyer cannot pay
    # the balance on delivery; refunded if the order ends without a build.
    deposit_paid: float = 0.0
    counter_total: float | None = None
    status: CapitalNegotiationStatus = CapitalNegotiationStatus.PROPOSED
    awaiting_id: int | None = None

    def __post_init__(self) -> None:
        if self.awaiting_id is None and self.status in {
            CapitalNegotiationStatus.PROPOSED,
            CapitalNegotiationStatus.COUNTERED,
        }:
            self.awaiting_id = self.manufacturer_id

    @property
    def agreed_total(self) -> float | None:
        if self.status != CapitalNegotiationStatus.ACCEPTED:
            return None
        return self.counter_total if self.counter_total is not None else self.buyer_offer


@dataclass
class CapitalNegotiationLedger:
    negotiations: list[CapitalOrderNegotiation] = field(default_factory=list)
    _next_id: int = 0

    def create(
        self,
        *,
        buyer_id: int,
        manufacturer_id: int,
        item_id: str,
        maintenance_term_years: int,
        predictive_maintenance: bool,
        spares_kits: int,
        expedited_eligible: bool,
        financing: bool,
        list_price: float,
        recommended_total: float,
        buyer_offer: float,
        units_required: int = 0,
        units_short_at_order: int = 0,
    ) -> CapitalOrderNegotiation:
        negotiation = CapitalOrderNegotiation(
            negotiation_id=self._next_id,
            buyer_id=buyer_id,
            manufacturer_id=manufacturer_id,
            item_id=item_id,
            maintenance_term_years=maintenance_term_years,
            predictive_maintenance=predictive_maintenance,
            spares_kits=spares_kits,
            expedited_eligible=expedited_eligible,
            financing=financing,
            list_price=round(float(list_price), 2),
            recommended_total=round(float(recommended_total), 2),
            buyer_offer=round(float(buyer_offer), 2),
            units_required=max(0, int(units_required)),
            units_short_at_order=max(0, int(units_short_at_order)),
            awaiting_id=manufacturer_id,
        )
        self.negotiations.append(negotiation)
        self._next_id += 1
        return negotiation

    def get(self, negotiation_id: int) -> CapitalOrderNegotiation | None:
        for negotiation in self.negotiations:
            if negotiation.negotiation_id == negotiation_id:
                return negotiation
        return None

    def for_player(self, player_id: int) -> list[CapitalOrderNegotiation]:
        return [
            negotiation for negotiation in self.negotiations
            if negotiation.buyer_id == player_id or negotiation.manufacturer_id == player_id
        ]

    def awaiting(self, player_id: int) -> list[CapitalOrderNegotiation]:
        return [
            negotiation for negotiation in self.negotiations
            if negotiation.awaiting_id == player_id
            and negotiation.status in ACTIVE_CAPITAL_NEGOTIATION_STATUSES
        ]

    @staticmethod
    def require_active(negotiation: CapitalOrderNegotiation) -> None:
        if negotiation.status not in ACTIVE_CAPITAL_NEGOTIATION_STATUSES:
            raise ValueError(
                f"Capital negotiation #{negotiation.negotiation_id} is already "
                f"{negotiation.status.value}"
            )
