from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from .resource import ResourceType


class DealStatus(Enum):
    PENDING   = "pending"
    RETURNED  = "returned"
    ACCEPTED  = "accepted"
    REJECTED  = "rejected"
    EXPIRED   = "expired"
    WITHDRAWN = "withdrawn"


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
    awaiting_id: int | None = None
    message: str = ""
    last_response_by_id: int | None = None

    def __post_init__(self) -> None:
        if self.awaiting_id is None and self.status in ACTIVE_DEAL_STATUSES:
            self.awaiting_id = self.target_id

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
            awaiting_id=target_id,
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
        self._require_active(deal)
        deal.status = DealStatus.ACCEPTED
        deal.awaiting_id = None
        return deal

    def reject(self, deal_id: int) -> DealProposal:
        deal = self._get(deal_id)
        self._require_active(deal)
        deal.status = DealStatus.REJECTED
        deal.awaiting_id = None
        return deal

    def expire(self, deal_id: int) -> DealProposal:
        deal = self._get(deal_id)
        self._require_active(deal)
        deal.status = DealStatus.EXPIRED
        deal.awaiting_id = None
        return deal

    def withdraw(self, deal_id: int, proposer_id: int) -> DealProposal:
        """Proposer pulls back an unanswered proposal (PENDING/RETURNED).

        Guarded by _require_active first so a concurrent accept/reject wins:
        whichever mutation lands second raises here. No escrow exists, so
        withdrawal is a pure state transition with no resources to refund.
        """
        deal = self._get(deal_id)
        self._require_active(deal)
        if proposer_id != deal.proposer_id:
            raise ValueError(
                f"Player {proposer_id} did not propose deal #{deal_id}")
        deal.status = DealStatus.WITHDRAWN
        deal.awaiting_id = None
        return deal

    def return_to_proposer(
        self,
        deal_id: int,
        responder_id: int,
        offer_resource: ResourceType | None,
        offer_qty: int,
        request_resource: ResourceType | None,
        request_qty: int,
        gold_sweetener: float = 0.0,
        message: str = "",
    ) -> DealProposal:
        deal = self._get(deal_id)
        self._require_active(deal)
        if deal.awaiting_id != responder_id:
            raise ValueError(f"Deal #{deal_id} is not awaiting player {responder_id}")
        if responder_id == deal.proposer_id:
            deal.awaiting_id = deal.target_id
        elif responder_id == deal.target_id:
            deal.awaiting_id = deal.proposer_id
        else:
            raise ValueError(f"Player {responder_id} is not party to deal #{deal_id}")
        deal.offer_resource = offer_resource
        deal.offer_qty = max(0, int(offer_qty))
        deal.request_resource = request_resource
        deal.request_qty = max(0, int(request_qty))
        deal.gold_sweetener = float(gold_sweetener)
        deal.message = message.strip()
        deal.last_response_by_id = responder_id
        deal.status = DealStatus.RETURNED
        return deal

    def pending_for_player(self, player_id: int) -> list[DealProposal]:
        return [
            d for d in self.deals
            if d.awaiting_id == player_id and d.status in ACTIVE_DEAL_STATUSES
        ]

    def expire_for_player(self, player_id: int) -> list[DealProposal]:
        expired = []
        for deal in list(self.pending_for_player(player_id)):
            expired.append(self.expire(deal.deal_id))
        return expired

    def deal_by_id(self, deal_id: int) -> DealProposal | None:
        try:
            return self._get(deal_id)
        except KeyError:
            return None

    def _get(self, deal_id: int) -> DealProposal:
        for d in self.deals:
            if d.deal_id == deal_id:
                return d
        raise KeyError(f"Deal #{deal_id} not found")

    @staticmethod
    def _require_active(deal: DealProposal) -> None:
        if deal.status not in ACTIVE_DEAL_STATUSES:
            raise ValueError(f"Deal #{deal.deal_id} is already {deal.status.value}")


ACTIVE_DEAL_STATUSES = {DealStatus.PENDING, DealStatus.RETURNED}
