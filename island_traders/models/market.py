from __future__ import annotations
from dataclasses import dataclass, field
from .resource import ResourceType
from .player import Player, InsufficientFundsError
from .resource import InsufficientResourceError
from ..constants import BASE_PRICES, PRICE_ELASTICITY, MIN_PRICE_MULTIPLIER, MAX_PRICE_MULTIPLIER


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
        return {r: self.current_price(r) for r in ResourceType}

    def post_supply(self, rtype: ResourceType, qty: int) -> None:
        self.supply[rtype] = self.supply.get(rtype, 0) + qty

    def post_demand(self, rtype: ResourceType, qty: int) -> None:
        self.demand[rtype] = self.demand.get(rtype, 0) + qty

    def execute_buy(self, buyer: Player, rtype: ResourceType, qty: int) -> float:
        available = self.supply.get(rtype, 0)
        if available < qty:
            raise InsufficientSupplyError(
                f"Market has only {available} {rtype.value}, requested {qty}"
            )
        price = self.current_price(rtype)
        total = price * qty
        buyer.spend_dollops(total)
        buyer.receive_resources(rtype, qty)
        self.supply[rtype] = available - qty
        self.post_demand(rtype, qty)
        return total

    def execute_sell(self, seller: Player, rtype: ResourceType, qty: int) -> float:
        seller.give_resources(rtype, qty)
        price = self.current_price(rtype)
        total = price * qty
        seller.receive_dollops(total)
        self.post_supply(rtype, qty)
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

    def post_offer(self, seller: Player, rtype: ResourceType,
                   price_per_unit: float, qty: int) -> MarketOffer:
        if qty <= 0:
            raise ValueError("Offer quantity must be positive")
        if price_per_unit <= 0:
            raise ValueError("Offer price must be positive")
        if seller.inventory.get(rtype) < qty:
            raise InsufficientSupplyError(
                f"{seller.name} has only {seller.inventory.get(rtype)} {rtype.value}"
            )
        seller.give_resources(rtype, qty)
        offer = MarketOffer(
            offer_id=self._next_offer_id,
            seller_id=seller.player_id,
            seller_name=seller.name,
            resource=rtype,
            price_per_unit=round(price_per_unit, 2),
            quantity=qty,
            remaining=qty,
            season_key=self._current_season_key,
            _seller=seller,
        )
        self._offers.append(offer)
        self._next_offer_id += 1
        self.post_supply(rtype, qty)
        self._auto_match_offer(offer)
        return offer

    def post_bid(self, buyer: Player, rtype: ResourceType,
                 price_per_unit: float, qty: int) -> MarketBid:
        if qty <= 0:
            raise ValueError("Bid quantity must be positive")
        if price_per_unit <= 0:
            raise ValueError("Bid price must be positive")
        total_cost = round(price_per_unit * qty, 2)
        if buyer.dollops < total_cost:
            raise InsufficientFundsError(
                f"{buyer.name} has {buyer.dollops:.2f} but bid needs {total_cost:.2f}"
            )
        bid = MarketBid(
            bid_id=self._next_bid_id,
            buyer_id=buyer.player_id,
            buyer_name=buyer.name,
            resource=rtype,
            price_per_unit=round(price_per_unit, 2),
            quantity=qty,
            remaining=qty,
            season_key=self._current_season_key,
            _buyer=buyer,
        )
        self._bids.append(bid)
        self._next_bid_id += 1
        self.post_demand(rtype, qty)
        self._auto_match_bid(bid)
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
            buyer.receive_resources(bid.resource, qty)
            seller.receive_dollops(cost)
            offer.remaining -= qty
            bid.remaining -= qty

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
            buyer.receive_resources(offer.resource, qty)
            seller.receive_dollops(cost)
            offer.remaining -= qty
            bid.remaining -= qty

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

    def buy_from_offers(self, buyer: Player, rtype: ResourceType,
                        qty: int) -> tuple[float, int]:
        offers = self.available_offers(rtype)
        total_available = sum(o.remaining for o in offers)
        if total_available < qty:
            raise InsufficientSupplyError(
                f"Only {total_available} {rtype.value} offered, requested {qty}"
            )
        total_cost = 0.0
        bought = 0
        for offer in offers:
            if bought >= qty:
                break
            take = min(qty - bought, offer.remaining)
            cost = round(offer.price_per_unit * take, 2)
            total_cost += cost
            offer.remaining -= take
            bought += take
        buyer.spend_dollops(total_cost)
        buyer.receive_resources(rtype, bought)
        self.post_demand(rtype, bought)
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
            buyer.receive_resources(rtype, take)
            seller.receive_dollops(cost)
            bid.remaining -= take
            total_paid += cost
            sold += take
        return total_paid, sold

    def market_summary(self) -> dict[str, dict]:
        result = {}
        for rtype in ResourceType:
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
            }
        return result

    def expire_season_offers(self) -> None:
        for offer in self._offers:
            if offer.remaining > 0 and offer.season_key != self._current_season_key:
                offer.remaining = 0
        for bid in self._bids:
            if bid.remaining > 0 and bid.season_key != self._current_season_key:
                bid.remaining = 0

    def reset_period_signals(self) -> None:
        self.demand = {}
