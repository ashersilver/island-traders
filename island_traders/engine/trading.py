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

    def execute_order_list(
        self,
        player: Player,
        orders,
        players: list[Player] | None = None,
    ) -> list[dict]:
        """Execute buy/sell orders in submission order with per-row results."""
        results: list[dict] = []
        players = players or [player]
        for index, raw_order in enumerate(orders or []):
            side = str((raw_order or {}).get("side", "")).lower()
            resource_value = (raw_order or {}).get("resource")
            try:
                rtype = (
                    resource_value
                    if isinstance(resource_value, ResourceType)
                    else ResourceType(str(resource_value))
                )
                qty = int((raw_order or {}).get("quantity", 0))
                limit_raw = (raw_order or {}).get("limit_price", None)
                limit_price = (
                    None if limit_raw in (None, "", 0, 0.0) else float(limit_raw)
                )
                if side not in ("buy", "sell"):
                    raise ValueError("side must be buy or sell")
                if qty <= 0:
                    raise ValueError("quantity must be positive")
                if limit_price is not None and limit_price <= 0:
                    raise ValueError("limit_price must be positive")
            except Exception as exc:
                results.append(self._order_result(
                    index, side, str(resource_value or ""), "rejected", 0,
                    None, 0.0, str(exc),
                ))
                continue

            try:
                if side == "buy":
                    result = self._execute_buy_order(index, player, rtype, qty, limit_price)
                else:
                    result = self._execute_sell_order(
                        index, player, rtype, qty, limit_price, players
                    )
            except Exception as exc:
                result = self._order_result(
                    index, side, rtype.value, "rejected", 0, None, 0.0, str(exc)
                )
            results.append(result)
        return results

    def _execute_buy_order(
        self,
        index: int,
        player: Player,
        rtype: ResourceType,
        qty: int,
        limit_price: float | None,
    ) -> dict:
        before_cash = player.dollops
        if limit_price is None:
            total_cost, bought = self.market.buy_from_offers(player, rtype, qty)
            return self._order_result(
                index, "buy", rtype.value, "filled", bought,
                self._avg_price(total_cost, bought), -round(total_cost, 2), "",
            )

        bid = self.market.post_bid(player, rtype, limit_price, qty)
        filled = bid.quantity - bid.remaining
        spent = round(before_cash - player.dollops, 2)
        if filled == qty:
            status = "filled"
            reason = ""
        else:
            status = "partial"
            reason = f"resting bid for {bid.remaining}"
        return self._order_result(
            index, "buy", rtype.value, status, filled,
            self._avg_price(spent, filled), -spent, reason,
        )

    def _execute_sell_order(
        self,
        index: int,
        player: Player,
        rtype: ResourceType,
        qty: int,
        limit_price: float | None,
        players: list[Player],
    ) -> dict:
        before_cash = player.dollops
        if limit_price is None:
            total_paid, sold = self.market.sell_to_bids(player, rtype, qty, players)
            return self._order_result(
                index, "sell", rtype.value, "filled", sold,
                self._avg_price(total_paid, sold), round(total_paid, 2), "",
            )

        offer = self.market.post_offer(player, rtype, limit_price, qty)
        filled = offer.quantity - offer.remaining
        received = round(player.dollops - before_cash, 2)
        if filled == qty:
            status = "filled"
            reason = ""
        else:
            status = "partial"
            reason = f"resting offer for {offer.remaining}"
        return self._order_result(
            index, "sell", rtype.value, status, filled,
            self._avg_price(received, filled), received, reason,
        )

    @staticmethod
    def _avg_price(total: float, qty: int) -> float | None:
        if qty <= 0:
            return None
        return round(total / qty, 2)

    @staticmethod
    def _order_result(
        index: int,
        side: str,
        resource: str,
        status: str,
        quantity: int,
        unit_price: float | None,
        total: float,
        reason: str = "",
    ) -> dict:
        result = {
            "index": index,
            "side": side,
            "resource": resource,
            "status": status,
            "quantity": quantity,
            "unit_price": unit_price,
            "total": round(total, 2),
        }
        if reason:
            result["reason"] = reason
        return result

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
        self,
        deal: DealProposal,
        acceptor: Player,
        proposer: Player,
        *,
        acquired_tick: int = 0,
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
            acceptor.receive_resources(
                deal.offer_resource,
                deal.offer_qty,
                acquired_tick=acquired_tick,
            )
        if deal.request_resource and deal.request_qty > 0:
            acceptor.give_resources(deal.request_resource, deal.request_qty)
            proposer.receive_resources(
                deal.request_resource,
                deal.request_qty,
                acquired_tick=acquired_tick,
            )
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
