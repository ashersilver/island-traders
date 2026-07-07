from __future__ import annotations
import math
from dataclasses import dataclass

from ..constants import FREIGHT_FEE_PER_TRADE_UNIT, FREIGHT_UNITS_PER_TRADE_UNIT
from ..models.player import Player, InsufficientFundsError
from ..models.market import Market, InsufficientSupplyError
from ..models.deal import DealProposal, DealLedger
from ..models.resource import ResourceType, InsufficientResourceError


class InvalidDealError(Exception):
    pass


class StaleResourceError(Exception):
    pass


@dataclass(frozen=True)
class FreightCharge:
    mode: str = "none"
    units: int = 0
    fee: float = 0.0
    recipient_id: int | None = None

    def as_dict(self) -> dict:
        return {
            "mode": self.mode,
            "units": self.units,
            "fee": round(self.fee, 2),
            "recipient_id": self.recipient_id,
        }


class TradingEngine:
    def __init__(
        self,
        market: Market,
        ledger: DealLedger,
        players: list[Player] | None = None,
    ):
        self.market = market
        self.ledger = ledger
        self.players = players or []

    # --- Central market ---

    def market_buy(
        self,
        buyer: Player,
        rtype: ResourceType,
        qty: int,
        players: list[Player] | None = None,
    ) -> float:
        self._preflight_cash_freight(
            buyer, rtype, qty, self.market.market_maker_ask(rtype) * qty, players
        )
        paid = self.market.execute_buy(buyer, rtype, qty)
        self.apply_freight_charge(buyer, rtype, qty, players)
        return paid

    def market_sell(
        self,
        seller: Player,
        rtype: ResourceType,
        qty: int,
        players: list[Player] | None = None,
    ) -> float:
        self._preflight_cash_freight(seller, rtype, qty, 0.0, players)
        paid = self.market.execute_sell(seller, rtype, qty)
        self.apply_freight_charge(seller, rtype, qty, players)
        return paid

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
                # Trade Blotter (#210): a resting order supersedes the player's
                # prior orders on this resource when ``replace`` is true, else it
                # *layers* alongside them.  Engine default stays True (supersede,
                # the historical behaviour) for backward-compatible callers; the
                # blotter client sends ``replace: false`` per order to layer.
                replace = bool((raw_order or {}).get("replace", True))
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
                    result = self._execute_buy_order(
                        index, player, rtype, qty, limit_price, players, replace
                    )
                else:
                    result = self._execute_sell_order(
                        index, player, rtype, qty, limit_price, players, replace
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
        players: list[Player],
        replace: bool = True,
    ) -> dict:
        before_cash = player.dollops
        if limit_price is None:
            total_quote = self._quoted_offer_cost(rtype, qty)
            self._preflight_cash_freight(player, rtype, qty, total_quote, players)
            total_cost, bought = self.market.buy_from_offers(player, rtype, qty)
            freight = self.apply_freight_charge(player, rtype, bought, players)
            return self._order_result(
                index, "buy", rtype.value, "filled", bought,
                self._avg_price(total_cost, bought), -round(total_cost, 2), "",
                freight,
            )

        bid = self.market.post_bid(player, rtype, limit_price, qty, replace=replace)
        filled = bid.quantity - bid.remaining
        spent = round(before_cash - player.dollops, 2)
        freight = self.apply_freight_charge(player, rtype, filled, players)
        if filled == qty:
            status = "filled"
            reason = ""
        else:
            status = "partial"
            reason = f"resting bid for {bid.remaining}"
        return self._order_result(
            index, "buy", rtype.value, status, filled,
            self._avg_price(spent, filled), -spent, reason, freight,
        )

    def _execute_sell_order(
        self,
        index: int,
        player: Player,
        rtype: ResourceType,
        qty: int,
        limit_price: float | None,
        players: list[Player],
        replace: bool = True,
    ) -> dict:
        before_cash = player.dollops
        if limit_price is None:
            fill_plan = self._planned_bid_fills(player, rtype, qty, players)
            for buyer, take, cost in fill_plan:
                self._preflight_cash_freight(buyer, rtype, take, cost, players)
            total_paid, sold = self.market.sell_to_bids(player, rtype, qty, players)
            freight = FreightCharge()
            for buyer, take, _cost in fill_plan:
                freight = self.apply_freight_charge(buyer, rtype, take, players)
            return self._order_result(
                index, "sell", rtype.value, "filled", sold,
                self._avg_price(total_paid, sold), round(total_paid, 2), "",
                freight,
            )

        offer = self.market.post_offer(player, rtype, limit_price, qty, replace=replace)
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
        freight: FreightCharge | None = None,
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
        if freight and freight.mode not in ("none", "waived"):
            result["freight"] = freight.as_dict()
        return result

    def _freight_units(self, rtype: ResourceType, qty: int) -> int:
        if qty <= 0 or rtype == ResourceType.FREIGHT:
            return 0
        return max(1, math.ceil(qty * FREIGHT_UNITS_PER_TRADE_UNIT))

    def _transporters(self, players: list[Player] | None = None) -> list[Player]:
        pool = players if players is not None else self.players
        return [p for p in pool if any(r.name == "Transporter" for r in p.roles)]

    def freight_quote(
        self,
        payer: Player,
        rtype: ResourceType,
        qty: int,
        players: list[Player] | None = None,
    ) -> FreightCharge:
        units = self._freight_units(rtype, qty)
        if units <= 0:
            return FreightCharge()
        if payer.inventory.get(ResourceType.FREIGHT) >= units:
            return FreightCharge(mode="resource", units=units)
        transporters = [p for p in self._transporters(players) if p.player_id != payer.player_id]
        if not transporters:
            return FreightCharge(mode="waived", units=units)
        fee = round(qty * FREIGHT_FEE_PER_TRADE_UNIT, 2)
        return FreightCharge(
            mode="fee",
            units=units,
            fee=fee,
            recipient_id=transporters[0].player_id,
        )

    def _preflight_cash_freight(
        self,
        payer: Player,
        rtype: ResourceType,
        qty: int,
        trade_cost: float,
        players: list[Player] | None = None,
    ) -> None:
        freight = self.freight_quote(payer, rtype, qty, players)
        if freight.mode == "fee" and payer.dollops < round(trade_cost + freight.fee, 2):
            raise InsufficientFundsError(
                f"{payer.name} needs {trade_cost + freight.fee:.2f} Dollops "
                f"including {freight.fee:.2f} freight"
            )

    def apply_freight_charge(
        self,
        payer: Player,
        rtype: ResourceType,
        qty: int,
        players: list[Player] | None = None,
    ) -> FreightCharge:
        freight = self.freight_quote(payer, rtype, qty, players)
        if freight.mode == "resource":
            payer.give_resources(ResourceType.FREIGHT, freight.units)
        elif freight.mode == "fee" and freight.fee > 0:
            payer.spend_dollops(freight.fee)
            recipient = next(
                (p for p in self._transporters(players) if p.player_id == freight.recipient_id),
                None,
            )
            if recipient is not None and recipient.player_id != payer.player_id:
                recipient.receive_dollops(freight.fee)
        return freight

    def _quoted_offer_cost(self, rtype: ResourceType, qty: int) -> float:
        planned = 0
        total = 0.0
        for offer in self.market.available_offers(rtype):
            if planned >= qty:
                break
            take = min(qty - planned, offer.remaining)
            total += round(offer.price_per_unit * take, 2)
            planned += take
        return round(total, 2)

    def _planned_bid_fills(
        self,
        seller: Player,
        rtype: ResourceType,
        qty: int,
        players: list[Player],
    ) -> list[tuple[Player, int, float]]:
        buyers = {p.player_id: p for p in players}
        fills: list[tuple[Player, int, float]] = []
        remaining = qty
        for bid in self.market.available_bids(rtype):
            buyer = buyers.get(bid.buyer_id)
            if buyer is None:
                continue
            take = min(remaining, bid.remaining)
            cost = round(bid.price_per_unit * take, 2)
            if buyer.dollops < cost:
                continue
            fills.append((buyer, take, cost))
            remaining -= take
            if remaining == 0:
                break
        return fills

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
        players: list[Player] | None = None,
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

        freight_charges: list[FreightCharge] = []
        if not self._same_island(proposer, acceptor):
            if deal.offer_resource and deal.offer_qty > 0:
                self._preflight_cash_freight(
                    acceptor, deal.offer_resource, deal.offer_qty, 0.0, players
                )
            if deal.request_resource and deal.request_qty > 0:
                self._preflight_cash_freight(
                    proposer, deal.request_resource, deal.request_qty, 0.0, players
                )

        # Atomic transfers
        if deal.offer_resource and deal.offer_qty > 0:
            proposer.give_resources(deal.offer_resource, deal.offer_qty)
            acceptor.receive_resources(
                deal.offer_resource,
                deal.offer_qty,
                acquired_tick=acquired_tick,
            )
            if not self._same_island(proposer, acceptor):
                freight_charges.append(self.apply_freight_charge(
                    acceptor, deal.offer_resource, deal.offer_qty, players
                ))
        if deal.request_resource and deal.request_qty > 0:
            acceptor.give_resources(deal.request_resource, deal.request_qty)
            proposer.receive_resources(
                deal.request_resource,
                deal.request_qty,
                acquired_tick=acquired_tick,
            )
            if not self._same_island(proposer, acceptor):
                freight_charges.append(self.apply_freight_charge(
                    proposer, deal.request_resource, deal.request_qty, players
                ))
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

    @staticmethod
    def _same_island(left: Player, right: Player) -> bool:
        if left.player_id == right.player_id:
            return True
        return bool({r.name for r in left.roles} & {r.name for r in right.roles})

    def reject_deal(self, deal: DealProposal) -> None:
        self.ledger.reject(deal.deal_id)

    def return_deal(
        self,
        deal: DealProposal,
        responder_id: int,
        offer_resource: ResourceType | None,
        offer_qty: int,
        request_resource: ResourceType | None,
        request_qty: int,
        gold_sweetener: float = 0.0,
        message: str = "",
    ) -> DealProposal:
        return self.ledger.return_to_proposer(
            deal.deal_id,
            responder_id,
            offer_resource,
            offer_qty,
            request_resource,
            request_qty,
            gold_sweetener,
            message,
        )
