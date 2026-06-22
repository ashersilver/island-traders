import random
import pytest
from island_traders.engine.workforce_events import apply_workplace_risks, _worker_risk_multiplier
from island_traders.models.insurance import InsurancePolicy
from island_traders.constants import (
    LIFE_INSURANCE_DEATH_BENEFIT, INSURANCE_DURATION_SEASONS,
)


class _FakeWorker:
    def __init__(self, worker_id, profession, experience_seasons=0):
        self.worker_id = worker_id
        self.profession = profession
        self.experience_seasons = experience_seasons
        self.in_training = False


def test_unskilled_multiplier_is_double_skilled():
    """Unskilled workers must have exactly 2× the base risk of skilled workers."""
    skilled = _FakeWorker(0, "Miner", experience_seasons=0)
    unskilled = _FakeWorker(1, "Unskilled", experience_seasons=0)
    m_skilled = _worker_risk_multiplier(skilled, is_unskilled=False)
    m_unskilled = _worker_risk_multiplier(unskilled, is_unskilled=True)
    assert m_unskilled == pytest.approx(m_skilled * 2)


def test_experience_increases_risk():
    """Each year of experience adds 5% to the individual risk multiplier."""
    worker_0yr = _FakeWorker(0, "Miner", experience_seasons=0)
    worker_4yr = _FakeWorker(1, "Miner", experience_seasons=16)  # 4 years
    m0 = _worker_risk_multiplier(worker_0yr, is_unskilled=False)
    m4 = _worker_risk_multiplier(worker_4yr, is_unskilled=False)
    assert m4 == pytest.approx(m0 * 1.20)   # 4 × 5% = +20%


def test_injuries_occur_with_certainty_rng(miner):
    """With a forced rng that always returns 0.0, every worker should be injured."""
    class AlwaysRNG:
        def random(self):
            return 0.0

    reports = apply_workplace_risks([miner], year=0, season_index=0, banker_players=[], rng=AlwaysRNG())
    assert len(reports) == 1
    assert len(reports[0].injured_worker_ids) > 0


def test_injuries_use_temporary_absence_not_training_flag(miner):
    class AlwaysRNG:
        def random(self):
            return 0.0

    reports = apply_workplace_risks(
        [miner], year=0, season_index=0, banker_players=[], rng=AlwaysRNG()
    )
    injured_ids = set(reports[0].injured_worker_ids)

    assert injured_ids
    assert miner.workforce.training_count == 0
    assert all(
        not worker.in_training
        for worker in miner.workforce.workers
        if worker.worker_id in injured_ids
    )
    assert all(
        worker.absent_seasons == 1
        for worker in miner.workforce.workers
        if worker.worker_id in injured_ids
    )
    assert injured_ids.isdisjoint(
        {worker.worker_id for worker in miner.workforce.active_workers}
    )

    miner.workforce.advance_absences()

    assert all(worker.absent_seasons == 0 for worker in miner.workforce.workers)


def test_no_injuries_with_never_rng(miner):
    """With a forced rng that always returns 1.0, no worker should be injured or die."""
    class NeverRNG:
        def random(self):
            return 1.0

    reports = apply_workplace_risks([miner], year=0, season_index=0, banker_players=[], rng=NeverRNG())
    assert reports == []


def test_low_risk_roles_produce_no_reports(banker):
    """Banker (zero risk) should never appear in reports."""
    rng = random.Random(0)
    reports = apply_workplace_risks([banker], year=0, season_index=0, banker_players=[], rng=rng)
    assert reports == []


def test_life_insurance_pays_death_benefit(miner, banker):
    """When a miner with life insurance suffers a fatality, the Banker pays the benefit."""
    # Give the banker enough to pay
    banker.receive_dollops(500.0)
    initial_banker_dollops = banker.dollops
    initial_miner_dollops = miner.dollops

    # Issue life insurance policy to the miner
    policy = InsurancePolicy(
        policy_id=1,
        policy_type="life",
        holder_player_id=miner.player_id,
        banker_player_id=banker.player_id,
        premium_paid=25.0,
        purchased_tick=0,
        expires_at_tick=INSURANCE_DURATION_SEASONS,
    )
    miner.add_insurance_policy(policy)

    class AlwaysFatalRNG:
        """Returns 0.0 so every risk roll triggers."""
        def random(self):
            return 0.0

    reports = apply_workplace_risks(
        [miner], year=0, season_index=0,
        banker_players=[banker], rng=AlwaysFatalRNG()
    )
    assert len(reports) == 1
    report = reports[0]
    if report.fatality_worker_ids:
        assert report.death_benefit_paid == pytest.approx(
            LIFE_INSURANCE_DEATH_BENEFIT * len(report.fatality_worker_ids)
        )
        # Banker paid, miner received
        assert banker.dollops < initial_banker_dollops
        assert miner.dollops > initial_miner_dollops


def test_medical_insurance_reduces_injuries(miner):
    """Medical insurance flag should be reflected in the report."""
    policy = InsurancePolicy(
        policy_id=1,
        policy_type="medical",
        holder_player_id=miner.player_id,
        banker_player_id=99,
        premium_paid=30.0,
        purchased_tick=0,
        expires_at_tick=INSURANCE_DURATION_SEASONS,
    )
    miner.add_insurance_policy(policy)

    class AlwaysRNG:
        def random(self):
            return 0.0

    reports = apply_workplace_risks([miner], year=0, season_index=0, banker_players=[], rng=AlwaysRNG())
    if reports:
        assert reports[0].insurance_reduced_injuries


def test_policy_validity():
    policy = InsurancePolicy(
        policy_id=1, policy_type="life",
        holder_player_id=0, banker_player_id=1,
        premium_paid=25.0,
        purchased_tick=0,         # bought at Year 1, Spring (tick 0)
        expires_at_tick=4,        # expires at Year 2, Spring (tick 4)
    )
    assert policy.is_valid(year=0, season_index=0)   # tick 0 < 4
    assert policy.is_valid(year=0, season_index=3)   # tick 3 < 4
    assert not policy.is_valid(year=1, season_index=0)  # tick 4 == 4, expired
    assert not policy.is_valid(year=1, season_index=1)  # tick 5 > 4
