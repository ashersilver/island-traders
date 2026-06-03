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
    # How many workers/students this policy covers (2026-06-02).  Medical
    # policies are priced per head; student travel to the Education island
    # consumes coverage seats.  Defaults to 1 for backward compatibility with
    # older single-head policies / saves.
    covered_count: int = 1

    def is_valid(self, year: int, season_index: int) -> bool:
        return self.active and (year * 4 + season_index) < self.expires_at_tick

    def seasons_remaining(self, year: int, season_index: int) -> int:
        """Seasons left until expiry (0 if expired or inactive)."""
        if not self.active:
            return 0
        now_tick = year * 4 + season_index
        return max(0, self.expires_at_tick - now_tick)

    def cancel_refund(self, year: int, season_index: int) -> float:
        """Pro-rata refund if cancelled now (Issue #5).

        Refund = premium_paid * seasons_remaining / total_term_seasons.
        Zero if the policy is already expired or inactive.
        """
        if not self.active:
            return 0.0
        total = self.expires_at_tick - self.purchased_tick
        if total <= 0:
            return 0.0
        remaining = self.seasons_remaining(year, season_index)
        return round(self.premium_paid * remaining / total, 1)

    def describe(self) -> str:
        expires_year = self.expires_at_tick // 4 + 1
        expires_season = self.expires_at_tick % 4
        from ..constants import SEASONS
        return (
            f"{self.policy_type.title()} Insurance  "
            f"(premium: {self.premium_paid:.0f} Dp  |  "
            f"expires start of Year {expires_year} {SEASONS[expires_season]})"
        )
