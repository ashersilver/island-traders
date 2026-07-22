from __future__ import annotations

from dataclasses import dataclass, field

from .equity import CapTable


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


def sync_holdings_mirror(
    island_id: int | str,
    cap_table: CapTable,
    owners: dict[str, Owner],
) -> None:
    """Make every owner's holding for one island mirror its cap table stake."""
    island_key = str(island_id)
    for owner_id, owner in owners.items():
        shares = cap_table.held_by(owner_id)
        if shares:
            owner.holdings[island_key] = shares
        else:
            owner.holdings.pop(island_key, None)


def holdings_mirror_consistent(
    island_id: int | str,
    cap_table: CapTable,
    owners: dict[str, Owner],
) -> bool:
    """Return whether issued cap-table stakes equal all owner mirrors."""
    island_key = str(island_id)
    return set(cap_table.player_holders()).issubset(owners) and all(
        owner.holdings.get(island_key, 0) == cap_table.held_by(owner_id)
        for owner_id, owner in owners.items()
    )
