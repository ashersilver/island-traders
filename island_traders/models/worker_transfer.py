from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4


@dataclass
class WorkerTransferOffer:
    offer_id: str
    from_player: int
    to_player: int
    profession: str
    count: int
    fee_per_head: float
    expires_season: int
    status: str = "pending"
    direction: str = "offer"

    @classmethod
    def create(
        cls,
        *,
        from_player: int,
        to_player: int,
        profession: str,
        count: int,
        fee_per_head: float,
        expires_season: int,
        direction: str = "offer",
    ) -> "WorkerTransferOffer":
        return cls(
            offer_id=str(uuid4()),
            from_player=from_player,
            to_player=to_player,
            profession=profession,
            count=count,
            fee_per_head=round(float(fee_per_head), 2),
            expires_season=expires_season,
            direction=direction,
        )

    def to_dict(self) -> dict:
        return {
            "offer_id": self.offer_id,
            "from_player": self.from_player,
            "to_player": self.to_player,
            "profession": self.profession,
            "count": self.count,
            "fee_per_head": self.fee_per_head,
            "expires_season": self.expires_season,
            "status": self.status,
            "direction": self.direction,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "WorkerTransferOffer":
        return cls(
            offer_id=str(raw["offer_id"]),
            from_player=int(raw["from_player"]),
            to_player=int(raw["to_player"]),
            profession=str(raw["profession"]),
            count=int(raw["count"]),
            fee_per_head=float(raw["fee_per_head"]),
            expires_season=int(raw["expires_season"]),
            status=str(raw.get("status", "pending")),
            direction=str(raw.get("direction", "offer")),
        )
