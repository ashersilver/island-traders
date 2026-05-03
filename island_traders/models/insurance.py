from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class InsurancePolicy:
    """A single insurance contract sold by the Banker to another island."""

    policy_id: int
    policy_type: str          # "life" or "medical"
    holder_player_id: int
    banker_player_id: int
    premium_paid: float
    # Policy is valid while current game (year * 4 + season_index) < expires_at_tick
    purchased_tick: int       # year * 4 + season_index at time of purchase
    expires_at_tick: int      # exclusive upper bound
    active: bool = True

    def is_valid(self, year: int, season_index: int) -> bool:
        return self.active and (year * 4 + season_index) < self.expires_at_tick

    def describe(self) -> str:
        expires_year = self.expires_at_tick // 4 + 1
        expires_season = self.expires_at_tick % 4
        from ..constants import SEASONS
        return (
            f"{self.policy_type.title()} Insurance  "
            f"(premium: {self.premium_paid:.0f} Dp  |  "
            f"expires start of Year {expires_year} {SEASONS[expires_season]})"
        )
