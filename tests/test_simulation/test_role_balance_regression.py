"""Role-balance regression gate (#213).

The re-tune brought wealth share from a 12.6–16.9 spread down to 12.9–15.0
across six seeds. These tests pin the *shape* of that result so a later
economic change cannot silently undo it.

They run the simulator, so they are slower than the rest of the suite — kept
to a small game count and a single seed, with the full multi-seed sweep left
to `island-traders-sim` during calibration.
"""
from __future__ import annotations

import pytest

from island_traders.simulation.runner import SimulationRunner


ROLES = ["Farmer", "Miner", "Transporter", "Educator", "Banker", "Manufacturer", "Doctor"]
EVEN_SHARE = 100.0 / len(ROLES)   # 14.29%


@pytest.fixture(scope="module")
def stats():
    return SimulationRunner(num_games=60, seed=42).run()


def _shares(stats) -> dict[str, float]:
    """Mean wealth share per role, as a percentage.

    `RoleStats.wealth_shares` is a per-game list of fractions, so the mean is
    taken here and scaled to a percentage.
    """
    by_role = stats.role_stats
    assert by_role, "simulation stats expose no per-role breakdown"
    out = {}
    for role in ROLES:
        entry = by_role.get(role)
        assert entry is not None, f"no stats for {role}"
        shares = entry.wealth_shares
        assert shares, f"no wealth shares recorded for {role}"
        out[role] = 100.0 * sum(shares) / len(shares)
    return out


def test_every_role_holds_a_meaningful_share_of_the_economy(stats):
    """No island should be economically irrelevant, nor should any dominate."""
    shares = _shares(stats)

    for role, share in shares.items():
        assert 10.0 <= share <= 19.0, f"{role} at {share:.1f}% wealth share"


def test_the_spread_between_best_and_worst_island_stays_tight(stats):
    """Pre-re-tune this was 4.3 points (12.6-16.9); the re-tune closed it."""
    shares = _shares(stats)

    spread = max(shares.values()) - min(shares.values())
    assert spread <= 6.0, f"wealth-share spread {spread:.1f} points: {shares}"


def test_shares_stay_centred_on_an_even_split(stats):
    shares = _shares(stats)

    mean_abs_error = sum(abs(s - EVEN_SHARE) for s in shares.values()) / len(shares)
    assert mean_abs_error <= 2.0, (
        f"mean deviation from an even {EVEN_SHARE:.1f}% split is "
        f"{mean_abs_error:.2f} points: {shares}"
    )
