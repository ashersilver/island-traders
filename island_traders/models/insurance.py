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
    # Equipment ("industrial") policies cover ONE named capital unit (#196).
    # Empty for the life/medical lines, which cover people, not plant.
    item_id: str = ""
    # Agreed payout if that unit fails. Fixed at inception alongside the
    # premium, so a claim is not re-priced against a later catalogue.
    insured_value: float = 0.0

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


# ---------------------------------------------------------------------------
# Equipment ("industrial") insurance pricing — #196
# ---------------------------------------------------------------------------

def annual_failure_probability(age_seasons: int) -> float:
    """Chance a unit of this age fails at least once over the next four seasons.

    Built from the #188 per-quarter Weibull table the engine already rolls
    against, so the premium is priced off the same hazard that causes the
    claim rather than a separate hand-tuned number.
    """
    from ..constants import EQUIPMENT_FAILURE_PROB_BY_QUARTER

    max_quarter = max(EQUIPMENT_FAILURE_PROB_BY_QUARTER)
    survives = 1.0
    for offset in range(4):
        quarter = min(max(1, age_seasons + 1 + offset), max_quarter)
        survives *= 1.0 - EQUIPMENT_FAILURE_PROB_BY_QUARTER[quarter]
    return 1.0 - survives


def equipment_insurance_quote(item_cost: float, age_seasons: int = 0) -> dict:
    """Price one year of cover on a single capital unit (#196).

    > "its premium will be a flat rate with a 20% markup, over percentage
    > (based on the actuarial tables in Issue #188) of the equipment
    > replacement value per year ... and will pay out 90% of the value of
    > the equipment."

    So: expected annual loss = payout x P(failure this year), and the premium
    is that loaded by the markup.  The rate is struck at inception and held
    flat for the life of the policy — the unit ages, the premium does not.
    """
    from ..constants import (
        EQUIPMENT_INSURANCE_MARKUP,
        EQUIPMENT_INSURANCE_PAYOUT_FRACTION,
    )

    probability = annual_failure_probability(age_seasons)
    payout = round(item_cost * EQUIPMENT_INSURANCE_PAYOUT_FRACTION, 2)
    expected_loss = payout * probability
    premium = round(expected_loss * (1.0 + EQUIPMENT_INSURANCE_MARKUP), 2)
    return {
        "annual_premium": premium,
        "payout": payout,
        "failure_probability": round(probability, 4),
        "expected_loss": round(expected_loss, 2),
        "loss_ratio": round(expected_loss / premium, 4) if premium else 0.0,
    }
