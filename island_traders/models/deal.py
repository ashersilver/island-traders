from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from .resource import ResourceType


class DealStatus(Enum):
    PENDING  = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED  = "expired"


@dataclass
class DealProposal:
    deal_id: int
    proposer_id: int
    target_id: int
    offer_resource: ResourceType | None   # None = gold-only deal
    offer_qty: int
    request_resource: ResourceType | None
    request_qty: int
    gold_sweetener: float = 0.0           # extra gold from proposer to target
    status: DealStatus = DealStatus.PENDING

    def summary(self, proposer_name: str, target_name: str) -> str:
        parts = []
        if self.offer_resource and self.offer_qty:
            parts.append(f"{self.offer_qty}x {self.offer_resource.value}")
        if self.gold_sweetener > 0:
            parts.append(f"{self.gold_sweetener:.1f} gold")
        offer_str = " + ".join(parts) or "nothing"

        req_parts = []
        if self.request_resource and self.request_qty:
            req_parts.append(f"{self.request_qty}x {self.request_resource.value}")
        if self.gold_sweetener < 0:
            req_parts.append(f"{abs(self.gold_sweetener):.1f} gold")
        req_str = " + ".join(req_parts) or "nothing"

        return (
            f"Deal #{self.deal_id}: {proposer_name} offers {offer_str} "
            f"to {target_name} in exchange for {req_str} [{self.status.value}]"
        )


@dataclass
class DealLedger:
    deals: list[DealProposal] = field(default_factory=list)
    _next_id: int = 0

    def create_proposal(
        self,
        proposer_id: int,
        target_id: int,
        offer_resource: ResourceType | None,
        offer_qty: int,
        request_resource: ResourceType | None,
        request_qty: int,
        gold_sweetener: float = 0.0,
    ) -> DealProposal:
        deal = DealProposal(
            deal_id=self._next_id,
            proposer_id=proposer_id,
            target_id=target_id,
            offer_resource=offer_resource,
            offer_qty=offer_qty,
            request_resource=request_resource,
            request_qty=request_qty,
            gold_sweetener=gold_sweetener,
        )
        self.deals.append(deal)
        self._next_id += 1
        return deal

    def accept(self, deal_id: int) -> DealProposal:
        deal = self._get(deal_id)
        deal.status = DealStatus.ACCEPTED
        return deal

    def reject(self, deal_id: int) -> DealProposal:
        deal = self._get(deal_id)
        deal.status = DealStatus.REJECTED
        return deal

    def pending_for_player(self, player_id: int) -> list[DealProposal]:
        return [d for d in self.deals if d.target_id == player_id and d.status == DealStatus.PENDING]

    def _get(self, deal_id: int) -> DealProposal:
        for d in self.deals:
            if d.deal_id == deal_id:
                return d
        raise KeyError(f"Deal #{deal_id} not found")
