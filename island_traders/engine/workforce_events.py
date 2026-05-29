from __future__ import annotations
import math
import random
from dataclasses import dataclass, field
from ..models.player import Player
from ..constants import (
    WORKPLACE_RISK, LIFE_INSURANCE_DEATH_BENEFIT,
    LIFE_INSURANCE_FATALITY_REDUCTION,
    MAX_WORKFORCE_LOSS_PER_TICK_FRACTION,
    MEDICAL_INSURANCE_INJURY_REDUCTION, SKILLED_PROFESSIONS,
)


@dataclass
class WorkforceEventReport:
    player_id: int
    player_name: str
    injured_worker_ids: list[int] = field(default_factory=list)
    fatality_worker_ids: list[int] = field(default_factory=list)
    death_benefit_paid: float = 0.0
    insurance_reduced_injuries: bool = False
    # 2026-05-27 disaster-mitigation brief.
    insurance_reduced_fatalities: bool = False
    # Set when the per-tick workforce-loss cap fired: would have lost
    # `would_have_lost` workers but the cap reduced it to
    # len(fatality_worker_ids).
    loss_cap_applied: bool = False
    would_have_lost: int = 0

    @property
    def has_events(self) -> bool:
        return bool(self.injured_worker_ids or self.fatality_worker_ids)

    def describe(self) -> str:
        parts = []
        if self.fatality_worker_ids:
            n = len(self.fatality_worker_ids)
            note = ""
            if self.death_benefit_paid:
                note += f" — death benefit {self.death_benefit_paid:.0f} Dp paid"
            if self.insurance_reduced_fatalities:
                note += " (rate halved by life insurance)"
            if self.loss_cap_applied:
                note += (
                    f" (loss-cap capped at {n}; "
                    f"would have lost {self.would_have_lost})"
                )
            parts.append(f"{n} worker fatality/fatalities{note}")
        if self.injured_worker_ids:
            n = len(self.injured_worker_ids)
            reduced = " (reduced by medical insurance)" if self.insurance_reduced_injuries else ""
            parts.append(f"{n} worker(s) injured — absent this season{reduced}")
        return "; ".join(parts) if parts else "no workplace incidents"


def _worker_risk_multiplier(worker, is_unskilled: bool) -> float:
    """
    Combined risk multiplier for an individual worker.

    - Unskilled workers face 2× the base rate vs skilled workers.
    - Risk increases by 5 % for each full year of experience on the job
      (years = experience_seasons // 4).
    """
    skew = 2.0 if is_unskilled else 1.0
    years_on_job = getattr(worker, "experience_seasons", 0) // 4
    experience_factor = 1.0 + 0.05 * years_on_job
    return skew * experience_factor


def apply_workplace_risks(
    players: list[Player],
    year: int,
    season_index: int,
    banker_players: list[Player],
    rng: random.Random | None = None,
) -> list[WorkforceEventReport]:
    """
    Roll injury and fatality events for each high-hazard player.

    Injuries: the worker is flagged absent for this season (dispatch_for_training reuse).
    Fatalities: the most-experienced skilled worker is permanently removed.

    Insurance effects:
    - Medical insurance halves the effective injury_rate for each worker.
    - Life insurance triggers a death-benefit payment from the Banker.

    Returns one WorkforceEventReport per player who has any events.
    """
    if rng is None:
        rng = random.Random()

    reports: list[WorkforceEventReport] = []

    for player in players:
        role_risks = _combined_risk(player)
        if not role_risks["injury_rate"] and not role_risks["fatality_rate"]:
            continue

        report = WorkforceEventReport(player_id=player.player_id, player_name=player.name)

        has_medical = player.has_active_insurance("medical", year, season_index)
        has_life = player.has_active_insurance("life", year, season_index)

        skilled_prof_names: set[str] = set()
        for role in player.roles:
            skilled_prof_names.update(SKILLED_PROFESSIONS.get(role.name, []))

        active = list(player.workforce.active_workers)

        # --- Injuries ---
        base_injury = role_risks["injury_rate"]
        injured_ids: list[int] = []
        for worker in active:
            is_unskilled = worker.profession not in skilled_prof_names
            multiplier = _worker_risk_multiplier(worker, is_unskilled)
            effective_rate = base_injury * multiplier
            if has_medical:
                effective_rate *= (1.0 - MEDICAL_INSURANCE_INJURY_REDUCTION)
                report.insurance_reduced_injuries = True
            if rng.random() < effective_rate:
                injured_ids.append(worker.worker_id)

        if injured_ids:
            player.workforce.dispatch_for_training(injured_ids)  # reuse "absent" mechanic
            report.injured_worker_ids = injured_ids

        # --- Fatalities ---
        # Re-check active workers (some may now be dispatched as injured)
        still_active = list(player.workforce.active_workers)
        active_count_at_start = len(still_active)
        base_fatal = role_risks["fatality_rate"]

        # Collect candidates with their individual probabilities
        # 2026-05-27 disaster-mitigation brief: Life insurance halves
        # each worker's fatality probability (mirroring how Medical
        # halves injury probability — see lines just above).  Before
        # this brief, Life insurance only paid a death benefit AFTER
        # the worker died; the policy was payout-only.  Now it actually
        # prevents some deaths.
        fatality_candidates = []
        for worker in still_active:
            is_unskilled = worker.profession not in skilled_prof_names
            multiplier = _worker_risk_multiplier(worker, is_unskilled)
            prob = base_fatal * multiplier
            if has_life:
                prob *= (1.0 - LIFE_INSURANCE_FATALITY_REDUCTION)
            fatality_candidates.append((worker, prob))

        # Roll each worker independently; collect those who die
        deceased = [w for w, p in fatality_candidates if rng.random() < p]
        if deceased and has_life:
            report.insurance_reduced_fatalities = True

        # 2026-05-27 disaster-mitigation brief: per-tick workforce-loss
        # cap.  Without this, a streak of bad rolls (especially on
        # high-risk Mining + Manufacturer) can wipe most of a 5-worker
        # starting workforce in one tick — exactly the Manny Fracture
        # cascade.  Cap at MAX_WORKFORCE_LOSS_PER_TICK_FRACTION of the
        # ACTIVE workforce (min 1).  When the cap fires, keep the
        # most-experienced workers (drop the youngest from the
        # deceased list) — domain logic: most-vulnerable die first, so
        # we keep the ones who would have survived.
        if deceased:
            cap = max(
                1,
                math.floor(
                    active_count_at_start * MAX_WORKFORCE_LOSS_PER_TICK_FRACTION
                ),
            )
            if len(deceased) > cap:
                report.loss_cap_applied = True
                report.would_have_lost = len(deceased)
                # Keep oldest (most experienced) workers; drop the rest
                # from this tick's deceased list.  They survive and may
                # still die on later ticks.
                deceased.sort(
                    key=lambda w: getattr(w, "age_seasons", 0),
                    reverse=True,
                )
                deceased = deceased[:cap]

        if deceased:
            # Remove deceased from workforce
            deceased_ids = [w.worker_id for w in deceased]
            player.workforce.remove_workers(deceased_ids)
            report.fatality_worker_ids = deceased_ids

            if has_life and banker_players:
                benefit = LIFE_INSURANCE_DEATH_BENEFIT * len(deceased)
                # Find the insuring Banker (first with enough funds, else split)
                paid = 0.0
                for banker in banker_players:
                    if banker.dollops >= benefit - paid:
                        banker.spend_dollops(benefit - paid)
                        player.receive_dollops(benefit - paid)
                        paid = benefit
                        break
                    elif banker.dollops > 0:
                        partial = banker.dollops
                        banker.spend_dollops(partial)
                        player.receive_dollops(partial)
                        paid += partial
                report.death_benefit_paid = paid

        if report.has_events:
            reports.append(report)

    return reports


def _combined_risk(player: Player) -> dict[str, float]:
    """Average risk across all of a player's roles (multi-role players blend their risks)."""
    injury_rates = []
    fatality_rates = []
    for role in player.roles:
        risk = WORKPLACE_RISK.get(role.name, {"injury_rate": 0.0, "fatality_rate": 0.0})
        injury_rates.append(risk["injury_rate"])
        fatality_rates.append(risk["fatality_rate"])
    if not injury_rates:
        return {"injury_rate": 0.0, "fatality_rate": 0.0}
    return {
        "injury_rate": sum(injury_rates) / len(injury_rates),
        "fatality_rate": sum(fatality_rates) / len(fatality_rates),
    }
