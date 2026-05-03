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
class Market:
    base_prices: dict[ResourceType, float] = field(
        default_factory=lambda: {ResourceType(k): v for k, v in BASE_PRICES.items()}
    )
    supply: dict[ResourceType, int] = field(default_factory=dict)
    demand: dict[ResourceType, int] = field(default_factory=dict)
    price_history: list[PriceSnapshot] = field(default_factory=list)
    _shocks: list[PriceShock] = field(default_factory=list)

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

    def reset_period_signals(self) -> None:
        self.demand = {}
