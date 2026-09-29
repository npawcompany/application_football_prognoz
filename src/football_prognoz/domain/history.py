"""Forecast history (training / evaluation dataset) and calibration results."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# Record status values (lowercase, stable for CSV / SQL).
STATUS_SCHEDULED = "scheduled"
STATUS_LIVE = "live"
STATUS_FINISHED = "finished"
STATUS_POSTPONED = "postponed"
STATUS_SUSPENDED = "suspended"
STATUS_CANCELLED = "cancelled"

OUTCOMES = ("1", "X", "2")


def outcome_from_score(home: int | None, away: int | None) -> str | None:
    if home is None or away is None:
        return None
    if home > away:
        return "1"
    if home < away:
        return "2"
    return "X"


@dataclass(frozen=True)
class ForecastRecord:
    match_id: int
    model_version: str
    competition_code: str
    kickoff_utc: datetime
    home_id: int
    home_name: str
    away_id: int
    away_name: str
    p_home: float
    p_draw: float
    p_away: float
    predicted_outcome: str
    predicted_score: str
    score_probability: float
    expected_home: float
    expected_away: float
    likely_outcomes: tuple[dict[str, Any], ...]
    facts: dict[str, Any]
    sources: tuple[str, ...]
    sample_matches: int
    forecast_at: datetime
    made_after_kickoff: bool
    status: str = STATUS_SCHEDULED
    actual_home: int | None = None
    actual_away: int | None = None
    actual_outcome: str | None = None
    is_correct: bool | None = None
    result_updated_at: datetime | None = None

    @property
    def actual_score(self) -> str | None:
        if self.actual_home is None or self.actual_away is None:
            return None
        return f"{self.actual_home}:{self.actual_away}"

    @property
    def probabilities(self) -> tuple[float, float, float]:
        return (self.p_home, self.p_draw, self.p_away)

    @property
    def evaluable(self) -> bool:
        """Pre-match forecast of a finished match: the only rows used for quality stats."""
        return (
            not self.made_after_kickoff
            and self.status == STATUS_FINISHED
            and self.actual_outcome is not None
        )


@dataclass(frozen=True)
class CollectionResult:
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    results_filled: int = 0
    post_kickoff: int = 0
    total: int = 0
    cancelled: bool = False
    errors: tuple[str, ...] = field(default_factory=tuple)

    @property
    def summary(self) -> str:
        head = "Сбор остановлен" if self.cancelled else "Сбор завершён"
        text = (
            f"{head}: новых {self.inserted}, обновлено {self.updated}, "
            f"без изменений {self.unchanged}, результатов проставлено {self.results_filled}"
        )
        if self.post_kickoff:
            text += f", после начала матча (не для оценки) {self.post_kickoff}"
        return text + "."


@dataclass(frozen=True)
class CalibrationBucket:
    lower: float
    upper: float
    count: int
    mean_predicted: float
    observed_rate: float

    @property
    def label(self) -> str:
        return f"{round(self.lower * 100)}–{round(self.upper * 100)}%"


@dataclass(frozen=True)
class CalibrationReport:
    model_version: str
    evaluated: int
    excluded_post_kickoff: int
    accuracy: float | None
    brier: float | None
    log_loss: float | None
    hit_rate_by_outcome: dict[str, tuple[int, float | None]]
    buckets: tuple[CalibrationBucket, ...]

    def bucket_for(self, probability: float) -> CalibrationBucket | None:
        eps = 1e-9  # same edge rule as the binning in services.calibration
        for bucket in self.buckets:
            lower_ok = bucket.lower - eps <= probability
            if bucket.upper >= 1.0:
                if lower_ok and probability <= 1.0 + eps:
                    return bucket
            elif lower_ok and probability < bucket.upper - eps:
                return bucket
        return None


@dataclass(frozen=True)
class HistoricalHint:
    """'Historically such an outcome came true in N% of cases' for one forecast."""

    outcome: str  # "1" | "X" | "2"
    probability: float
    bucket_label: str
    observed_rate: float
    sample: int

    @property
    def text(self) -> str:
        return (
            f"Исторически такой исход сбывался в {round(self.observed_rate * 100)}% случаев "
            f"(выборка: {self.sample} прогнозов с вероятностью {self.bucket_label})."
        )
