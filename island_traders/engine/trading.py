from __future__ import annotations
from ..models.player import Player, InsufficientFundsError
from ..models.market import Market, InsufficientSupplyError
from ..models.deal import DealProposal, DealLedger
from ..models.resource import ResourceType, InsufficientResourceError


class InvalidDealError(Exception):
    pass


class StaleResourceError(Exception):
    pass


class TradingEngine:
    def __init__(self, market: Market, ledger: DealLedger):
        self.market = market
        self.ledger = ledger

    # --- Central market ---

    def market_buy(self, buyer: Player, rtype: ResourceType, qty: int) -> float:
        return self.market.execute_buy(buyer, rtype, qty)

    def market_sell(self, seller: Player, rtype: ResourceType, qty: int) -> float:
        return self.market.execute_sell(seller, rtype, qty)

    def get_quote(self, rtype: ResourceType, qty: int) -> float:
        return round(self.market.current_price(rtype) * qty, 2)

    # --- Peer-to-peer deals ---

    def propose_deal(
        self,
        proposer: Player,
        target: Player,
        offer_resource: ResourceType | None,
        offer_qty: int,
        request_resource: ResourceType | None,
        request_qty: int,
        gold_sweetener: float = 0.0,
    ) -> DealProposal:
        if (
            (not offer_resource or offer_qty <= 0)
            and (not request_resource or request_qty <= 0)
            and gold_sweetener == 0
        ):
            raise InvalidDealError("Deal must offer, request, or pay something")

        # Validate proposer can cover their side
        if offer_resource and offer_qty > 0:
            if proposer.inventory.get(offer_resource) < offer_qty:
                raise InvalidDealError(
                    f"{proposer.name} does not have {offer_qty}x {offer_resource.value} to offer"
                )
        if gold_sweetener > 0 and proposer.dollops < gold_sweetener:
            raise InvalidDealError(
                f"{proposer.name} does not have {gold_sweetener:.2f} Dollops for the sweetener"
            )

        return self.ledger.create_proposal(
            proposer_id=proposer.player_id,
            target_id=target.player_id,
            offer_resource=offer_resource,
            offer_qty=offer_qty,
            request_resource=request_resource,
            request_qty=request_qty,
            gold_sweetener=gold_sweetener,
        )

    def accept_deal(
        self, deal: DealProposal, acceptor: Player, proposer: Player
    ) -> None:
        # Re-validate both sides before any mutation
        if deal.offer_resource and deal.offer_qty > 0:
            if proposer.inventory.get(deal.offer_resource) < deal.offer_qty:
                raise StaleResourceError(
                    f"{proposer.name} no longer has {deal.offer_qty}x {deal.offer_resource.value}"
                )
        if deal.request_resource and deal.request_qty > 0:
            if acceptor.inventory.get(deal.request_resource) < deal.request_qty:
                raise StaleResourceError(
                    f"{acceptor.name} no longer has {deal.request_qty}x {deal.request_resource.value}"
                )
        if deal.gold_sweetener > 0 and proposer.dollops < deal.gold_sweetener:
            raise StaleResourceError(f"{proposer.name} no longer has enough Dollops")
        if deal.gold_sweetener < 0 and acceptor.dollops < abs(deal.gold_sweetener):
            raise StaleResourceError(f"{acceptor.name} no longer has enough Dollops")

        # Atomic transfers
        if deal.offer_resource and deal.offer_qty > 0:
            proposer.give_resources(deal.offer_resource, deal.offer_qty)
            acceptor.receive_resources(deal.offer_resource, deal.offer_qty)
        if deal.request_resource and deal.request_qty > 0:
            acceptor.give_resources(deal.request_resource, deal.request_qty)
            proposer.receive_resources(deal.request_resource, deal.request_qty)
        if deal.gold_sweetener > 0:
            proposer.spend_dollops(deal.gold_sweetener)
            acceptor.receive_dollops(deal.gold_sweetener)
        elif deal.gold_sweetener < 0:
            acceptor.spend_dollops(abs(deal.gold_sweetener))
            proposer.receive_dollops(abs(deal.gold_sweetener))

        self.ledger.accept(deal.deal_id)

        telemetry = getattr(self.market, "telemetry", None)
        if telemetry is not None:
            if deal.offer_resource and deal.offer_qty > 0:
                telemetry.record_traded(deal.offer_resource, deal.offer_qty)
            if deal.request_resource and deal.request_qty > 0:
                telemetry.record_traded(deal.request_resource, deal.request_qty)

    def reject_deal(self, deal: DealProposal) -> None:
        self.ledger.reject(deal.deal_id)
