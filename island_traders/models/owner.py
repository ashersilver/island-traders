from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Owner:
    """Investor record above one or more island businesses."""

    owner_id: str
    name: str
    personal_cash: float = 0.0
    holdings: dict[str, int] = field(default_factory=dict)

    def net_worth(
        self,
        share_price_by_island: dict[str, float],
        loan_receivable: float = 0.0,
    ) -> float:
        total = self.personal_cash + loan_receivable
        for island_id, shares in self.holdings.items():
            total += shares * share_price_by_island.get(str(island_id), 0.0)
        return total

    def to_dict(self) -> dict:
        return {
            "owner_id": self.owner_id,
            "name": self.name,
            "personal_cash": self.personal_cash,
            "holdings": dict(self.holdings),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Owner":
        return cls(
            owner_id=str(data["owner_id"]),
            name=str(data.get("name", data["owner_id"])),
            personal_cash=float(data.get("personal_cash", 0.0)),
            holdings={str(k): int(v) for k, v in data.get("holdings", {}).items()},
        )
