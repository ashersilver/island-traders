from __future__ import annotations
from dataclasses import dataclass, field
from .profession import (
    Profession, WorkerBand, band_of,
    APPRENTICESHIP_SETTLING_SEASONS, APPRENTICESHIP_SETTLING_EFFICIENCY,
)


# Efficiency caps per training level (0=Unskilled, 1=Basic, 2=Skilled, 3=Expert)
TRAINING_PLATEAUS = [0.40, 0.65, 0.85, 1.00]
EFFICIENCY_BASE = 0.20          # new worker starts at 20%
EFFICIENCY_GAIN_PER_SEASON = 0.05  # +5% per season worked, up to plateau


@dataclass
class Worker:
    worker_id: int
    experience_seasons: int = 0
    training_level: int = 0      # 0=Unskilled, 1=Basic professional, 2=Skilled, 3=Expert
    in_training: bool = False
    profession: str = Profession.UNSKILLED.value   # stored as string for simple serialisation
    # Seasons of reduced-productivity "settling" remaining after a returning
    # apprentice (Technician band) reaches their home island.  0 = at full
    # productivity.  University (Manager) graduates never settle.
    settling_seasons: int = 0
    # Seasons this worker has existed (advanced every season, including
    # while away at training).  Drives retirement — see
    # WORKING_LIFE_SEASONS / Workforce.advance_age_and_retire.
    age_seasons: int = 0
    # MBA credential (Phase D).  Meaningful only for Manager-band workers
    # whose profession is `Banker`: ≥3 MBA-qualified Banker Managers drop
    # the bank's reserve ratio from 0.50 to 0.20 (≈2x → ≈5x leverage).
    has_mba: bool = False
    # Set True while the worker is on a staffing contract at another island.
    # Excludes them from the home island's active workforce during the contract.
    on_contract: bool = False

    @property
    def plateau(self) -> float:
        return TRAINING_PLATEAUS[min(self.training_level, len(TRAINING_PLATEAUS) - 1)]

    @property
    def efficiency(self) -> float:
        raw = EFFICIENCY_BASE + self.experience_seasons * EFFICIENCY_GAIN_PER_SEASON
        eff = min(raw, self.plateau)
        if self.settling_seasons > 0:
            eff *= APPRENTICESHIP_SETTLING_EFFICIENCY
        return eff

    @property
    def tier_name(self) -> str:
        if self.in_training:
            return "At College"
        if self.profession == Profession.UNSKILLED.value:
            return "Unskilled"
        levels = ["", "Basic", "Skilled", "Expert"]
        level_str = levels[min(self.training_level, 3)]
        suffix = " — settling" if self.settling_seasons > 0 else ""
        return f"{self.profession} ({level_str}){suffix}"

    def gain_experience(self) -> None:
        self.experience_seasons += 1
        if self.settling_seasons > 0:
            self.settling_seasons -= 1

    def train(self, target_profession: str | None = None) -> None:
        """Advance this worker's training.

        If a target_profession is given and the worker is currently Unskilled,
        they enter that profession at level 1 (Basic).
        If the worker already has a profession, they advance one level within it.
        """
        if target_profession and self.profession == Profession.UNSKILLED.value:
            self.profession = target_profession
            self.training_level = 1
        elif self.training_level < len(TRAINING_PLATEAUS) - 1:
            self.training_level += 1

    def depart_for_training(self) -> None:
        self.in_training = True

    def return_from_training(self, target_profession: str | None = None) -> None:
        self.in_training = False
        self.train(target_profession)
        # Apprenticeship (Technician band) graduates work a reduced-output
        # settling season on the home island; university graduates do not.
        if band_of(self.profession) == WorkerBand.TECHNICIAN:
            self.settling_seasons = APPRENTICESHIP_SETTLING_SEASONS


@dataclass
class Workforce:
    workers: list[Worker] = field(default_factory=list)
    _next_id: int = 0

    def add_workers(
        self,
        count: int,
        training_level: int = 0,
        profession: str = Profession.UNSKILLED.value,
        age_seasons: int = 0,
    ) -> list[Worker]:
        new: list[Worker] = []
        for _ in range(count):
            w = Worker(
                self._next_id,
                training_level=training_level,
                profession=profession,
                age_seasons=age_seasons,
            )
            self._next_id += 1
            self.workers.append(w)
            new.append(w)
        return new

    def advance_age_and_retire(
        self, working_life_by_band: dict[str, int], default_life: int
    ) -> list[Worker]:
        """Age every worker one season; remove + return those who retire.

        Runs once per season (including for workers away at training).
        A worker retires when ``age_seasons >= working life`` for their
        band; retired workers are removed from the roster entirely (the
        seat must be re-recruited + retrained — the lifecycle pressure).
        """
        retired: list[Worker] = []
        for w in self.workers:
            w.age_seasons += 1
            life = working_life_by_band.get(band_of(w.profession).value, default_life)
            if w.age_seasons >= life:
                retired.append(w)
        if retired:
            retired_ids = {w.worker_id for w in retired}
            self.workers = [w for w in self.workers if w.worker_id not in retired_ids]
        return retired

    @property
    def count(self) -> int:
        return len(self.workers)

    @property
    def active_workers(self) -> list[Worker]:
        return [w for w in self.workers if not w.in_training and not w.on_contract]

    @property
    def active_count(self) -> int:
        return len(self.active_workers)

    @property
    def training_count(self) -> int:
        return sum(1 for w in self.workers if w.in_training)

    @property
    def average_efficiency(self) -> float:
        active = self.active_workers
        if not active:
            return 0.0
        return sum(w.efficiency for w in active) / len(active)

    def workers_by_profession(self, profession: str) -> list[Worker]:
        return [w for w in self.active_workers if w.profession == profession]

    def count_profession(self, profession: str) -> int:
        return len(self.workers_by_profession(profession))

    # ------------------------------------------------------------------ Band helpers

    def workers_by_band(self, band: WorkerBand) -> list[Worker]:
        """All active workers whose profession sits in the given WorkerBand."""
        return [w for w in self.active_workers if band_of(w.profession) == band]

    def count_by_band(self, band: WorkerBand) -> int:
        return len(self.workers_by_band(band))

    def band_summary(self) -> dict[str, int]:
        """Active-worker counts keyed by band name (Manager / Technician / Worker)."""
        out = {b.value: 0 for b in WorkerBand}
        for w in self.active_workers:
            out[band_of(w.profession).value] += 1
        return out

    def training_band_summary(self) -> dict[str, int]:
        """Away-at-training counts keyed by home band name."""
        out = {b.value: 0 for b in WorkerBand}
        for w in self.workers:
            if w.in_training:
                out[band_of(w.profession).value] += 1
        return out

    def profession_summary(self) -> dict[str, dict[str, int]]:
        """Per-profession counts: {"Factory Foreman": {"active": 2, "training": 1}, ...}.

        Uses the raw profession value as the key (e.g. "factory_foreman") and
        also includes a "label" entry for display.  Unskilled workers are
        omitted unless present.
        """
        from ..models.profession import PROFESSION_LABEL, Profession
        active: dict[str, int] = {}
        training: dict[str, int] = {}
        for w in self.workers:
            key = w.profession
            if w.in_training:
                training[key] = training.get(key, 0) + 1
            else:
                active[key] = active.get(key, 0) + 1
        all_profs = set(active) | set(training)
        result = {}
        for key in all_profs:
            try:
                label = PROFESSION_LABEL.get(Profession(key), key)
            except ValueError:
                label = key
            result[key] = {
                "label": label,
                "active": active.get(key, 0),
                "training": training.get(key, 0),
            }
        return result

    def repurpose_worker(self, worker_id: int, new_profession: str) -> bool:
        """Reassign a worker to a new profession, resetting all experience.

        The worker loses training_level, experience_seasons, and settling
        bonus.  They join the new profession at the unskilled level (level 0)
        with profession already set — effectively a direct placement rather
        than a formal training path.

        Returns True if the worker was found and reassigned; False otherwise.
        """
        worker = next(
            (w for w in self.active_workers if w.worker_id == worker_id), None
        )
        if worker is None:
            return False
        worker.profession = new_profession
        worker.training_level = 0
        worker.experience_seasons = 0
        worker.settling_seasons = 0
        return True

    def has_mechanic(self) -> bool:
        """True if at least one active Mechanic is on staff."""
        return self.count_profession(Profession.MECHANIC.value) > 0

    def mechanic_count(self) -> int:
        return self.count_profession(Profession.MECHANIC.value)

    def workforce_fill_rate(self, required: int) -> float:
        if required <= 0:
            return 1.0
        return min(self.active_count / required, 1.0)

    def productivity_factor(self, required: int) -> float:
        fill = self.workforce_fill_rate(required)
        avg_eff = self.average_efficiency if self.active_workers else EFFICIENCY_BASE
        return fill * avg_eff

    def apply_season_work(self) -> None:
        for w in self.active_workers:
            w.gain_experience()

    def dispatch_for_training(self, worker_ids: list[int]) -> list[Worker]:
        dispatched = []
        for w in self.workers:
            if w.worker_id in worker_ids and not w.in_training:
                w.depart_for_training()
                dispatched.append(w)
        return dispatched

    def remove_workers(self, worker_ids: list[int]) -> list[Worker]:
        """Permanently remove workers (fatalities). Returns removed workers."""
        id_set = set(worker_ids)
        removed = [w for w in self.workers if w.worker_id in id_set]
        self.workers = [w for w in self.workers if w.worker_id not in id_set]
        return removed

    def return_from_training(
        self, worker_ids: list[int], target_profession: str | None = None
    ) -> list[Worker]:
        returned = []
        for w in self.workers:
            if w.worker_id in worker_ids and w.in_training:
                w.return_from_training(target_profession)
                returned.append(w)
        return returned

    def get_trainable_ids(self, count: int) -> list[int]:
        """Pick up to count workers eligible for training (not already Expert or away)."""
        eligible = sorted(
            [w for w in self.active_workers if w.training_level < 3],
            key=lambda w: -w.experience_seasons,
        )[:count]
        return [w.worker_id for w in eligible]

    def labour_productivity_factor(
        self,
        required_skilled: int,
        required_unskilled: int,
        skilled_professions: list[str],
    ) -> float:
        """Weighted productivity: skilled workers count 70%, unskilled 30%.

        Skilled workers are those whose profession appears in skilled_professions.
        Efficiency is taken from the skilled pool (falls back to EFFICIENCY_BASE when absent).
        """
        skilled = [w for w in self.active_workers if w.profession in skilled_professions]
        unskilled_workers = [w for w in self.active_workers if w.profession not in skilled_professions]

        skilled_fill = min(1.0, len(skilled) / max(1, required_skilled))
        unskilled_fill = min(1.0, len(unskilled_workers) / max(1, required_unskilled))

        weighted_fill = 0.70 * skilled_fill + 0.30 * unskilled_fill

        avg_eff = (
            sum(w.efficiency for w in skilled) / len(skilled)
            if skilled else EFFICIENCY_BASE
        )
        return weighted_fill * avg_eff

    def get_unskilled_ids(self, count: int) -> list[int]:
        """Return IDs of up to count active Unskilled workers, most experienced first."""
        eligible = sorted(
            [w for w in self.active_workers if w.profession == Profession.UNSKILLED.value and w.training_level < 3],
            key=lambda w: -w.experience_seasons,
        )[:count]
        return [w.worker_id for w in eligible]

    def year_end_births(self, birth_rate: float) -> int:
        """Population grows but new people are NOT automatically workers.
        Returns the population growth count; caller updates player.population."""
        return max(0, round(self.count * birth_rate))

    def summary(self) -> dict:
        by_tier: dict[str, int] = {}
        for w in self.workers:
            tier = w.tier_name
            by_tier[tier] = by_tier.get(tier, 0) + 1
        return {
            "total": self.count,
            "active": self.active_count,
            "at_college": self.training_count,
            "avg_efficiency_pct": round(self.average_efficiency * 100, 1),
            "by_tier": by_tier,
        }

    def __repr__(self) -> str:
        s = self.summary()
        tiers = "  ".join(f"{k}:{v}" for k, v in s["by_tier"].items())
        return f"Workforce({s['active']}/{s['total']} active, {s['avg_efficiency_pct']}% avg  {tiers})"
