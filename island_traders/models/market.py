from __future__ import annotations
from dataclasses import dataclass, field
from .resource import ResourceType, NON_TRADABLE_RESOURCES
from .player import Player, InsufficientFundsError
from .resource import InsufficientResourceError
from ..constants import (
    BASE_PRICES,
    MARKET_MAKER_DEPTH_PER_RESOURCE,
    MARKET_MAKER_SPREAD,
    MAX_PRICE_MULTIPLIER,
    MIN_PRICE_MULTIPLIER,
    PRICE_ELASTICITY,
    SEASONS,
)


class InsufficientSupplyError(Exception):
    pass


@dataclass
class PriceSnapshot:
    year: int
    season: int
    prices: dict[ResourceType, float]


@dataclass
class PriceShock:
    resource: ResourceType
    multiplier: float
    seasons_remaining: int


@dataclass
class MarketOffer:
    """A standing sell order: seller offers qty units at a fixed price per unit."""
    offer_id: int
    seller_id: int
    seller_name: str
    resource: ResourceType
    price_per_unit: float
    quantity: int
    remaining: int
    season_key: tuple[int, int] = (0, 0)
    _seller: Player | None = field(default=None, repr=False, compare=False)

    @property
    def total_cost(self) -> float:
        return round(self.price_per_unit * self.remaining, 2)


@dataclass
class MarketBid:
    """A standing buy order: buyer offers to pay a fixed price per unit."""
    bid_id: int
    buyer_id: int
    buyer_name: str
    resource: ResourceType
    price_per_unit: float
    quantity: int
    remaining: int
    season_key: tuple[int, int] = (0, 0)
    _buyer: Player | None = field(default=None, repr=False, compare=False)

    @property
    def total_cost(self) -> float:
        return round(self.price_per_unit * self.remaining, 2)


@dataclass
class Market:
    base_prices: dict[ResourceType, float] = field(
        default_factory=lambda: {ResourceType(k): v for k, v in BASE_PRICES.items()}
    )
    supply: dict[ResourceType, int] = field(default_factory=dict)
    demand: dict[ResourceType, int] = field(default_factory=dict)
    price_history: list[PriceSnapshot] = field(default_factory=list)
    _shocks: list[PriceShock] = field(default_factory=list)
    _offers: list[MarketOffer] = field(default_factory=list)
    _bids: list[MarketBid] = field(default_factory=list)
    _next_offer_id: int = 0
    _next_bid_id: int = 0
    _current_season_key: tuple[int, int] = (0, 0)
    _maker_supply: dict[ResourceType, int] = field(default_factory=dict)
    _maker_buy_depth: dict[ResourceType, int] = field(default_factory=dict)
    _maker_sell_depth: dict[ResourceType, int] = field(default_factory=dict)
    # Discrete market events (posted asks/bids, fills) since the last drain.
    # The server drains these and pushes them to clients so they can react
    # between full-state broadcasts (Issue #4).
    _event_log: list[dict] = field(default_factory=list)
    # Optional ResourceFlowTelemetry (B1/B2, #73); set by Game.setup() in
    # simulation. None during normal play, so live games pay nothing.
    telemetry: object | None = None
    # Executed-trade ledger (Trade Blotter, #211). Every fill appends one
    # canonical record here; ``player_fills`` shapes it per-viewer for the UI.
    # Bounded to the most recent ``_FILLS_CAP`` fills to cap memory.
    _fills: list[dict] = field(default_factory=list)
    _next_fill_id: int = 0

    def _emit_market_event(self, rtype: ResourceType, side: str, action: str,
                           price: float, quantity: int, actor: str) -> None:
        if quantity <= 0:
            return
        self._event_log.append({
            "resource": rtype.value,
            "side": side,          # "ask" (sell offer) | "bid" (buy order)
            "action": action,      # "posted" | "filled"
            "price": round(price, 2),
            "quantity": int(quantity),
            "actor": actor,
        })

    def drain_events(self) -> list[dict]:
        """Return and clear the buffered market events."""
        events, self._event_log = self._event_log, []
        return events

    # Retain at most this many executed fills in the ledger (memory bound).
    _FILLS_CAP = 500

    def _record_fill(self, rtype: ResourceType, price: float, qty: int, *,
                     buyer_id: int | None, buyer_name: str,
                     seller_id: int | None, seller_name: str) -> None:
        """Append one executed trade to the ledger (Trade Blotter, #211).

        Records the canonical two-sided fill once; ``player_fills`` derives
        each viewer's perspective (buy vs sell, counterparty) from it.
        Self-trades (same island both sides) are not real trades and are
        skipped.  Market-maker fills pass ``None`` for the maker side's id
        and a ``"Market"`` name.
        """
        if qty <= 0:
            return
        if buyer_id is not None and buyer_id == seller_id:
            return
        self._fills.append({
            "fill_id": self._next_fill_id,
            "resource": rtype.value,
            "price_per_unit": round(price, 2),
            "quantity": int(qty),
            "buyer_id": buyer_id,
            "buyer_name": buyer_name,
            "seller_id": seller_id,
            "seller_name": seller_name,
            "season_key": list(self._current_season_key),
        })
        self._next_fill_id += 1
        if len(self._fills) > self._FILLS_CAP:
            self._fills = self._fills[-self._FILLS_CAP:]

    def current_price(self, rtype: ResourceType) -> float:
        s = self.supply.get(rtype, 0)
        d = self.demand.get(rtype, 0)
        # factor = 1 when supply == demand; rises with scarcity, falls with glut
        factor = 1.0 + PRICE_ELASTICITY * (d - s) / (s + d + 1)
        factor = max(MIN_PRICE_MULTIPLIER, min(MAX_PRICE_MULTIPLIER, factor))
        base = self.base_prices.get(rtype, BASE_PRICES.get(rtype.value, 10.0))
        # Apply active price shocks (e.g. from disasters)
        for shock in self._shocks:
            if shock.resource == rtype:
                factor *= shock.multiplier
        factor = max(MIN_PRICE_MULTIPLIER, min(MAX_PRICE_MULTIPLIER, factor))
        return round(base * factor, 2)

    def current_prices(self) -> dict[ResourceType, float]:
        # Non-tradable resources carry no market price.
        return {
            r: self.current_price(r)
            for r in ResourceType
            if r not in NON_TRADABLE_RESOURCES
        }

    def market_maker_ask(self, rtype: ResourceType) -> float:
        return round(self.current_price(rtype) * (1.0 + MARKET_MAKER_SPREAD), 2)

    def market_maker_bid(self, rtype: ResourceType) -> float:
        return round(self.current_price(rtype) * (1.0 - MARKET_MAKER_SPREAD), 2)

    def _maker_depth_remaining(
        self, bucket: dict[ResourceType, int], rtype: ResourceType
    ) -> int:
        return bucket.get(rtype, MARKET_MAKER_DEPTH_PER_RESOURCE)

    def market_maker_buy_depth(self, rtype: ResourceType) -> int:
        """Units the formula market will still sell this season."""
        return self._maker_depth_remaining(self._maker_buy_depth, rtype)

    def market_maker_sell_depth(self, rtype: ResourceType) -> int:
        """Units the formula market will still buy this season."""
        return self._maker_depth_remaining(self._maker_sell_depth, rtype)

    def post_supply(self, rtype: ResourceType, qty: int) -> None:
        self.supply[rtype] = self.supply.get(rtype, 0) + qty
        self._maker_supply[rtype] = self._maker_supply.get(rtype, 0) + qty

    def post_demand(self, rtype: ResourceType, qty: int) -> None:
        self.demand[rtype] = self.demand.get(rtype, 0) + qty

    def execute_buy(self, buyer: Player, rtype: ResourceType, qty: int) -> float:
        available = self._maker_supply.get(rtype, 0)
        if available < qty:
            raise InsufficientSupplyError(
                f"Market has only {available} {rtype.value}, requested {qty}"
            )
        depth = self.market_maker_buy_depth(rtype)
        if depth < qty:
            raise InsufficientSupplyError(
                f"Market maker will sell only {depth} {rtype.value} this season, requested {qty}"
            )
        price = self.market_maker_ask(rtype)
        total = price * qty
        buyer.spend_dollops(total)
        buyer.receive_resources(rtype, qty, acquired_tick=self._current_tick())
        self._maker_supply[rtype] = available - qty
        self.supply[rtype] = max(0, self.supply.get(rtype, 0) - qty)
        self._maker_buy_depth[rtype] = depth - qty
        self.post_demand(rtype, qty)
        self._record_fill(
            rtype, price, qty,
            buyer_id=buyer.player_id, buyer_name=buyer.name,
            seller_id=None, seller_name="Market",
        )
        if self.telemetry is not None:
            self.telemetry.record_traded(rtype, qty)
        return total

    def execute_sell(self, seller: Player, rtype: ResourceType, qty: int) -> float:
        depth = self.market_maker_sell_depth(rtype)
        if depth < qty:
            raise InsufficientSupplyError(
                f"Market maker will buy only {depth} {rtype.value} this season, requested {qty}"
            )
        seller.give_resources(rtype, qty)
        price = self.market_maker_bid(rtype)
        total = price * qty
        seller.receive_dollops(total)
        self.post_supply(rtype, qty)
        self._maker_sell_depth[rtype] = depth - qty
        self._record_fill(
            rtype, price, qty,
            buyer_id=None, buyer_name="Market",
            seller_id=seller.player_id, seller_name=seller.name,
        )
        if self.telemetry is not None:
            self.telemetry.record_traded(rtype, qty)
        return total

    def apply_price_shock(self, rtype: ResourceType, multiplier: float, duration_seasons: int) -> None:
        self._shocks.append(PriceShock(rtype, multiplier, duration_seasons))

    def tick_shocks(self) -> None:
        self._shocks = [s for s in self._shocks if s.seasons_remaining > 1]
        for s in self._shocks:
            s.seasons_remaining -= 1

    def snapshot_prices(self, year: int, season: int) -> None:
        self.price_history.append(PriceSnapshot(year, season, self.current_prices()))

    def set_season(self, year: int, season: int) -> None:
        self._current_season_key = (year, season)
        self._maker_buy_depth = {}
        self._maker_sell_depth = {}

    def _current_tick(self) -> int:
        year, season = self._current_season_key
        return year * len(SEASONS) + season

    def cancel_player_orders(self, player_id: int, rtype: ResourceType) -> None:
        """Cancel every standing bid AND ask by ``player_id`` on ``rtype``.

        Resting asks refund their unsold remainder of resources to the
        seller; supply / demand counters are decremented by the unsold
        portion so the price formula doesn't pretend the cancelled
        depth is still on the book.  Used by post_offer / post_bid to
        enforce the "a new order overrides the player's prior orders"
        rule.
        """
        for offer in self._offers:
            if (offer.seller_id == player_id
                    and offer.resource == rtype
                    and offer.remaining > 0):
                qty = offer.remaining
                if offer._seller is not None:
                    offer._seller.receive_resources(
                        rtype, qty, acquired_tick=self._current_tick()
                    )
                offer.remaining = 0
                self.supply[rtype] = max(0, self.supply.get(rtype, 0) - qty)
        for bid in self._bids:
            if (bid.buyer_id == player_id
                    and bid.resource == rtype
                    and bid.remaining > 0):
                qty = bid.remaining
                bid.remaining = 0
                self.demand[rtype] = max(0, self.demand.get(rtype, 0) - qty)

    def cancel_offer(self, seller: Player, offer_id: int) -> MarketOffer:
        """Cancel one live ask and refund its unsold resources to the seller."""
        for offer in self._offers:
            if offer.offer_id != offer_id:
                continue
            if offer.seller_id != seller.player_id:
                raise PermissionError("Cannot cancel another player's offer")
            if offer.remaining <= 0:
                raise ValueError("Offer is not active")
            qty = offer.remaining
            if offer._seller is not None:
                offer._seller.receive_resources(
                    offer.resource, qty, acquired_tick=self._current_tick()
                )
            else:
                seller.receive_resources(
                    offer.resource, qty, acquired_tick=self._current_tick()
                )
            offer.remaining = 0
            self.supply[offer.resource] = max(
                0, self.supply.get(offer.resource, 0) - qty
            )
            return offer
        raise ValueError("Offer not found")

    def reduce_offer(
        self, seller: Player, offer_id: int, new_remaining: int
    ) -> MarketOffer:
        """Reduce a live ask to ``new_remaining`` units, refunding the delta."""
        if new_remaining < 0:
            raise ValueError("Offer quantity cannot be negative")
        for offer in self._offers:
            if offer.offer_id != offer_id:
                continue
            if offer.seller_id != seller.player_id:
                raise PermissionError("Cannot reduce another player's offer")
            if offer.remaining <= 0:
                raise ValueError("Offer is not active")
            if new_remaining > offer.remaining:
                raise ValueError("Offer quantity can only be reduced")
            if new_remaining == 0:
                return self.cancel_offer(seller, offer_id)
            refund = offer.remaining - new_remaining
            if refund > 0:
                if offer._seller is not None:
                    offer._seller.receive_resources(
                        offer.resource, refund, acquired_tick=self._current_tick()
                    )
                else:
                    seller.receive_resources(
                        offer.resource, refund, acquired_tick=self._current_tick()
                    )
                offer.remaining = new_remaining
                self.supply[offer.resource] = max(
                    0, self.supply.get(offer.resource, 0) - refund
                )
            return offer
        raise ValueError("Offer not found")

    def cancel_bid(self, buyer: Player, bid_id: int) -> MarketBid:
        """Cancel one live bid."""
        for bid in self._bids:
            if bid.bid_id != bid_id:
                continue
            if bid.buyer_id != buyer.player_id:
                raise PermissionError("Cannot cancel another player's bid")
            if bid.remaining <= 0:
                raise ValueError("Bid is not active")
            qty = bid.remaining
            bid.remaining = 0
            self.demand[bid.resource] = max(
                0, self.demand.get(bid.resource, 0) - qty
            )
            return bid
        raise ValueError("Bid not found")

    def reduce_bid(
        self, buyer: Player, bid_id: int, new_remaining: int
    ) -> MarketBid:
        """Reduce a live bid to ``new_remaining`` units."""
        if new_remaining < 0:
            raise ValueError("Bid quantity cannot be negative")
        for bid in self._bids:
            if bid.bid_id != bid_id:
                continue
            if bid.buyer_id != buyer.player_id:
                raise PermissionError("Cannot reduce another player's bid")
            if bid.remaining <= 0:
                raise ValueError("Bid is not active")
            if new_remaining > bid.remaining:
                raise ValueError("Bid quantity can only be reduced")
            if new_remaining == 0:
                return self.cancel_bid(buyer, bid_id)
            reduction = bid.remaining - new_remaining
            if reduction > 0:
                bid.remaining = new_remaining
                self.demand[bid.resource] = max(
                    0, self.demand.get(bid.resource, 0) - reduction
                )
            return bid
        raise ValueError("Bid not found")

    def post_offer(self, seller: Player, rtype: ResourceType,
                   price_per_unit: float, qty: int,
                   replace: bool = True) -> MarketOffer:
        if rtype in NON_TRADABLE_RESOURCES:
            raise ValueError(f"{rtype.value} is not tradable")
        if qty <= 0:
            raise ValueError("Offer quantity must be positive")
        if price_per_unit <= 0:
            raise ValueError("Offer price must be positive")
        # When ``replace`` (the default), a new ask supersedes this player's
        # prior bids AND asks on this resource — cancel them first so any
        # refunded units from a prior ask are visible to the inventory check
        # below.  When ``replace`` is False the new ask *layers* on top of the
        # existing ones (Trade Blotter, #211), letting an island stack orders.
        if replace:
            self.cancel_player_orders(seller.player_id, rtype)
        if seller.inventory.get(rtype) < qty:
            raise InsufficientSupplyError(
                f"{seller.name} has only {seller.inventory.get(rtype)} {rtype.value}"
            )
        seller.give_resources(rtype, qty)
        price = round(price_per_unit, 2)
        offer = MarketOffer(
            offer_id=self._next_offer_id,
            seller_id=seller.player_id,
            seller_name=seller.name,
            resource=rtype,
            price_per_unit=price,
            quantity=qty,
            remaining=qty,
            season_key=self._current_season_key,
            _seller=seller,
        )
        self._offers.append(offer)
        self._next_offer_id += 1
        self.supply[rtype] = self.supply.get(rtype, 0) + qty
        self._emit_market_event(rtype, "ask", "posted", price, qty, seller.name)
        self._auto_match_offer(offer)
        self._check_tight_spread(rtype)
        return offer

    def post_bid(self, buyer: Player, rtype: ResourceType,
                 price_per_unit: float, qty: int,
                 replace: bool = True) -> MarketBid:
        if rtype in NON_TRADABLE_RESOURCES:
            raise ValueError(f"{rtype.value} is not tradable")
        if qty <= 0:
            raise ValueError("Bid quantity must be positive")
        if price_per_unit <= 0:
            raise ValueError("Bid price must be positive")
        total_cost = round(price_per_unit * qty, 2)
        if buyer.dollops < total_cost:
            raise InsufficientFundsError(
                f"{buyer.name} has {buyer.dollops:.2f} but bid needs {total_cost:.2f}"
            )
        # When ``replace`` (the default), a new bid supersedes this player's
        # prior bids AND asks on this resource (cancels both); resources from
        # any cancelled ask refund.  When ``replace`` is False the bid *layers*
        # on top of the existing orders (Trade Blotter, #211).
        if replace:
            self.cancel_player_orders(buyer.player_id, rtype)
        price = round(price_per_unit, 2)
        bid = MarketBid(
            bid_id=self._next_bid_id,
            buyer_id=buyer.player_id,
            buyer_name=buyer.name,
            resource=rtype,
            price_per_unit=price,
            quantity=qty,
            remaining=qty,
            season_key=self._current_season_key,
            _buyer=buyer,
        )
        self._bids.append(bid)
        self._next_bid_id += 1
        self.post_demand(rtype, qty)
        self._emit_market_event(rtype, "bid", "posted", price, qty, buyer.name)
        self._auto_match_bid(bid)
        self._check_tight_spread(rtype)
        return bid

    def _auto_match_bid(self, bid: MarketBid) -> None:
        """Cross a new bid against resting asks while the price covers them.

        Standard exchange semantics: the resting (older) order sets the
        trade price; the new order is the price-taker.  Partial fills are
        supported — the bid consumes asks in best-price (ascending) order
        until either the bid is filled or the next ask is too expensive.
        """
        buyer = bid._buyer
        if buyer is None or bid.remaining <= 0:
            return
        # `available_offers` returns asks sorted ascending by price.
        for offer in self.available_offers(bid.resource):
            if bid.remaining <= 0:
                break
            if offer.seller_id == bid.buyer_id:
                continue
            if offer.price_per_unit > bid.price_per_unit:
                # No further asks will cross — they're all >= this one.
                break
            seller = offer._seller
            if seller is None:
                continue
            qty = min(bid.remaining, offer.remaining)
            if qty <= 0:
                continue
            trade_price = offer.price_per_unit   # resting ask sets price
            cost = round(trade_price * qty, 2)
            if buyer.dollops < cost:
                # Even the cheapest crossing ask is unaffordable — stop.
                break
            buyer.spend_dollops(cost)
            buyer.receive_resources(
                bid.resource, qty, acquired_tick=self._current_tick()
            )
            seller.receive_dollops(cost)
            offer.remaining -= qty
            bid.remaining -= qty
            self._record_fill(
                bid.resource, trade_price, qty,
                buyer_id=bid.buyer_id, buyer_name=bid.buyer_name,
                seller_id=offer.seller_id, seller_name=offer.seller_name,
            )
            if self.telemetry is not None:
                self.telemetry.record_traded(bid.resource, qty)

    def _auto_match_offer(self, offer: MarketOffer) -> None:
        """Cross a new ask against resting bids while the price covers them.

        Resting bid sets the trade price; new ask is the price-taker.
        Partial fills supported — the ask consumes bids in best-price
        (descending) order until the ask is filled or the next bid is
        too low.
        """
        seller = offer._seller
        if seller is None or offer.remaining <= 0:
            return
        # `available_bids` returns bids sorted descending by price.
        for bid in self.available_bids(offer.resource):
            if offer.remaining <= 0:
                break
            if bid.buyer_id == offer.seller_id:
                continue
            if bid.price_per_unit < offer.price_per_unit:
                # No further bids will cross — they're all <= this one.
                break
            buyer = bid._buyer
            if buyer is None:
                continue
            qty = min(bid.remaining, offer.remaining)
            if qty <= 0:
                continue
            trade_price = bid.price_per_unit   # resting bid sets price
            cost = round(trade_price * qty, 2)
            if buyer.dollops < cost:
                # This buyer can no longer pay their bid — drop it and
                # continue to the next-best resting bid.
                bid.remaining = 0
                continue
            buyer.spend_dollops(cost)
            buyer.receive_resources(
                offer.resource, qty, acquired_tick=self._current_tick()
            )
            seller.receive_dollops(cost)
            offer.remaining -= qty
            bid.remaining -= qty
            self._record_fill(
                offer.resource, trade_price, qty,
                buyer_id=bid.buyer_id, buyer_name=bid.buyer_name,
                seller_id=offer.seller_id, seller_name=offer.seller_name,
            )
            if self.telemetry is not None:
                self.telemetry.record_traded(offer.resource, qty)

    # Threshold for automatic execution of near-crossing orders (2026-05-28).
    # A spread of 2.5% or less is close enough to be auto-accepted, executing
    # at the resting (earlier-placed) order's price.
    TIGHT_SPREAD_THRESHOLD: float = 0.025

    def _check_tight_spread(self, rtype: ResourceType) -> None:
        """Auto-execute if the best bid and ask are within TIGHT_SPREAD_THRESHOLD.

        When the spread is within 2.5%, instead of waiting for one side to
        move, we cross the orders at the price of whichever was placed first
        (lower sequential ID = placed earlier):
          - Ask existed first (ask.offer_id < bid.bid_id) → cross at ask price
          - Bid existed first (bid.bid_id < ask.offer_id) → cross at bid price

        Only executes one crossing per call; loops until the spread widens.
        """
        while True:
            ask = self.best_offer(rtype)
            bid = self.best_bid(rtype)
            if not ask or not bid:
                break
            if ask.seller_id == bid.buyer_id:
                break
            spread = (ask.price_per_unit - bid.price_per_unit) / ask.price_per_unit
            if spread < 0 or spread > self.TIGHT_SPREAD_THRESHOLD:
                break
            # Determine trade price from the older (resting) order.
            if ask.offer_id < bid.bid_id:
                # Ask was posted first → buyer gets the ask price.
                trade_price = ask.price_per_unit
            else:
                # Bid was posted first → seller gets the bid price.
                trade_price = bid.price_per_unit
            buyer = bid._buyer
            seller = ask._seller
            if buyer is None or seller is None:
                break
            qty = min(bid.remaining, ask.remaining)
            if qty <= 0:
                break
            cost = round(trade_price * qty, 2)
            if buyer.dollops < cost:
                break
            buyer.spend_dollops(cost)
            buyer.receive_resources(rtype, qty, acquired_tick=self._current_tick())
            seller.receive_dollops(cost)
            ask.remaining -= qty
            bid.remaining -= qty
            self._record_fill(
                rtype, trade_price, qty,
                buyer_id=bid.buyer_id, buyer_name=bid.buyer_name,
                seller_id=ask.seller_id, seller_name=ask.seller_name,
            )
            if self.telemetry is not None:
                self.telemetry.record_traded(rtype, qty)

    def available_offers(self, rtype: ResourceType) -> list[MarketOffer]:
        return sorted(
            [o for o in self._offers if o.resource == rtype and o.remaining > 0],
            key=lambda o: o.price_per_unit,
        )

    def best_offer(self, rtype: ResourceType) -> MarketOffer | None:
        offers = self.available_offers(rtype)
        return offers[0] if offers else None

    def available_bids(self, rtype: ResourceType) -> list[MarketBid]:
        return sorted(
            [b for b in self._bids if b.resource == rtype and b.remaining > 0],
            key=lambda b: b.price_per_unit,
            reverse=True,
        )

    def best_bid(self, rtype: ResourceType) -> MarketBid | None:
        bids = self.available_bids(rtype)
        return bids[0] if bids else None

    def player_orders(self, player_id: int) -> dict[str, list[dict]]:
        """Live orders owned by one player, shaped for API/UI payloads."""
        offers = [
            {
                "offer_id": offer.offer_id,
                "resource": offer.resource.value,
                "price_per_unit": offer.price_per_unit,
                "quantity": offer.quantity,
                "remaining": offer.remaining,
                "season_key": list(offer.season_key),
            }
            for offer in self._offers
            if offer.seller_id == player_id and offer.remaining > 0
        ]
        bids = [
            {
                "bid_id": bid.bid_id,
                "resource": bid.resource.value,
                "price_per_unit": bid.price_per_unit,
                "quantity": bid.quantity,
                "remaining": bid.remaining,
                "season_key": list(bid.season_key),
            }
            for bid in self._bids
            if bid.buyer_id == player_id and bid.remaining > 0
        ]
        return {"offers": offers, "bids": bids}

    def player_fills(self, player_id: int, limit: int = 50) -> list[dict]:
        """Executed trades involving ``player_id``, most recent first.

        Shaped for the Trade Blotter Fills tab (#211): each row is from the
        viewer's perspective — ``side`` is "buy" when the viewer received the
        resource, "sell" when they supplied it — with the counterparty's name
        (or "Market" for market-maker fills).
        """
        out: list[dict] = []
        for f in reversed(self._fills):
            if f["buyer_id"] == player_id:
                side, counterparty, cp_id = "buy", f["seller_name"], f["seller_id"]
            elif f["seller_id"] == player_id:
                side, counterparty, cp_id = "sell", f["buyer_name"], f["buyer_id"]
            else:
                continue
            out.append({
                "fill_id": f["fill_id"],
                "resource": f["resource"],
                "side": side,
                "price_per_unit": f["price_per_unit"],
                "quantity": f["quantity"],
                "counterparty": counterparty,
                "counterparty_id": cp_id,
                "season_key": f["season_key"],
            })
            if len(out) >= limit:
                break
        return out

    def buy_from_offers(self, buyer: Player, rtype: ResourceType,
                        qty: int) -> tuple[float, int]:
        offers = self.available_offers(rtype)
        total_available = sum(o.remaining for o in offers)
        if total_available < qty:
            raise InsufficientSupplyError(
                f"Only {total_available} {rtype.value} offered, requested {qty}"
            )
        total_cost = 0.0
        fills = []
        planned = 0
        for offer in offers:
            if planned >= qty:
                break
            take = min(qty - planned, offer.remaining)
            cost = round(offer.price_per_unit * take, 2)
            total_cost += cost
            fills.append((offer, take, cost))
            planned += take
        buyer.spend_dollops(total_cost)
        bought = 0
        for offer, take, cost in fills:
            offer.remaining -= take
            bought += take
            if offer._seller is not None and offer.seller_id != buyer.player_id:
                offer._seller.receive_dollops(cost)
                self._record_fill(
                    rtype, offer.price_per_unit, take,
                    buyer_id=buyer.player_id, buyer_name=buyer.name,
                    seller_id=offer.seller_id, seller_name=offer.seller_name,
                )
        buyer.receive_resources(rtype, bought, acquired_tick=self._current_tick())
        self.post_demand(rtype, bought)
        if bought > 0:
            avg = total_cost / bought
            self._emit_market_event(rtype, "ask", "filled", avg, bought, buyer.name)
        return total_cost, bought

    def sell_to_bids(self, seller: Player, rtype: ResourceType,
                     qty: int, players: list[Player]) -> tuple[float, int]:
        if seller.inventory.get(rtype) < qty:
            raise InsufficientSupplyError(
                f"{seller.name} has only {seller.inventory.get(rtype)} {rtype.value}"
            )
        buyers = {p.player_id: p for p in players}
        fills: list[tuple[MarketBid, Player, int, float]] = []
        remaining = qty
        for bid in self.available_bids(rtype):
            buyer = buyers.get(bid.buyer_id)
            if buyer is None:
                bid.remaining = 0
                continue
            take = min(remaining, bid.remaining)
            cost = round(bid.price_per_unit * take, 2)
            if buyer.dollops < cost:
                bid.remaining = 0
                continue
            fills.append((bid, buyer, take, cost))
            remaining -= take
            if remaining == 0:
                break
        if remaining > 0:
            available = qty - remaining
            raise InsufficientSupplyError(
                f"Only {available} affordable {rtype.value} bid for, requested {qty}"
            )

        seller.give_resources(rtype, qty)
        total_paid = 0.0
        sold = 0
        for bid, buyer, take, cost in fills:
            buyer.spend_dollops(cost)
            buyer.receive_resources(rtype, take, acquired_tick=self._current_tick())
            seller.receive_dollops(cost)
            bid.remaining -= take
            total_paid += cost
            sold += take
            self._record_fill(
                rtype, bid.price_per_unit, take,
                buyer_id=bid.buyer_id, buyer_name=bid.buyer_name,
                seller_id=seller.player_id, seller_name=seller.name,
            )
        if sold > 0:
            avg = total_paid / sold
            self._emit_market_event(rtype, "bid", "filled", avg, sold, seller.name)
        return total_paid, sold

    def market_summary(self) -> dict[str, dict]:
        result = {}
        for rtype in ResourceType:
            if rtype in NON_TRADABLE_RESOURCES:
                continue  # no order book for non-tradable resources.
            best_offer = self.best_offer(rtype)
            best_bid = self.best_bid(rtype)
            ask_qty = sum(o.remaining for o in self._offers
                          if o.resource == rtype and o.remaining > 0)
            bid_qty = sum(b.remaining for b in self._bids
                          if b.resource == rtype and b.remaining > 0)
            ask_price = best_offer.price_per_unit if best_offer else None
            bid_price = best_bid.price_per_unit if best_bid else None
            result[rtype.value] = {
                "bid_price": bid_price,
                "bid_quantity": bid_qty,
                "ask_price": ask_price,
                "ask_quantity": ask_qty,
                "best_price": ask_price,
                "quantity": ask_qty,
                "formula_price": self.current_price(rtype),
                "market_maker_bid": self.market_maker_bid(rtype),
                "market_maker_ask": self.market_maker_ask(rtype),
                "market_maker_buy_depth": self.market_maker_buy_depth(rtype),
                "market_maker_sell_depth": self.market_maker_sell_depth(rtype),
            }
        return result

    def open_offer_value(
        self,
        seller_id: int,
        prices: dict[ResourceType, float],
    ) -> float:
        """Inventory value still owned by a seller but escrowed in live asks."""
        return sum(
            offer.remaining * prices.get(offer.resource, self.current_price(offer.resource))
            for offer in self._offers
            if offer.seller_id == seller_id and offer.remaining > 0
        )

    def expire_season_offers(self, *, expire_current: bool = False) -> None:
        for offer in self._offers:
            if offer.remaining > 0 and (
                expire_current or offer.season_key != self._current_season_key
            ):
                if offer._seller is not None:
                    offer._seller.receive_resources(
                        offer.resource,
                        offer.remaining,
                        acquired_tick=self._current_tick(),
                    )
                self.supply[offer.resource] = max(
                    0,
                    self.supply.get(offer.resource, 0) - offer.remaining,
                )
                offer.remaining = 0
        for bid in self._bids:
            if bid.remaining > 0 and (
                expire_current or bid.season_key != self._current_season_key
            ):
                self.demand[bid.resource] = max(
                    0,
                    self.demand.get(bid.resource, 0) - bid.remaining,
                )
                bid.remaining = 0

    def reset_period_signals(self) -> None:
        self.demand = {}
