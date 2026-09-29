"""Quality of stored forecasts (VKR §3.3): hit rate, Brier score, log-loss, calibration.

Only `ForecastRecord.evaluable` rows count: pre-match forecasts of finished matches.
Forecasts first made after kick-off are excluded. Nothing here changes a forecast.
"""

from __future__ import annotations

import csv
import math
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from football_prognoz.domain.history import (
    OUTCOMES,
    CalibrationBucket,
    CalibrationReport,
    ForecastRecord,
    HistoricalHint,
)
from football_prognoz.domain.prediction import Probabilities

BUCKET_WIDTH = 0.1
MIN_BUCKET_SAMPLE = 20  # below this the UI hides the historical hint
MIN_EVALUATED_FOR_LLM = 30  # below this the LLM gets no historical summary
LOG_LOSS_EPS = 1e-15
BUCKET_EPS = 1e-9  # 0.6 / 0.1 = 5.999…: keep 60% in the 60–70% bucket

CSV_COLUMNS = (
    "match_id",
    "model_version",
    "competition_code",
    "kickoff_utc",
    "home_name",
    "away_name",
    "p_home",
    "p_draw",
    "p_away",
    "predicted_outcome",
    "predicted_score",
    "score_probability",
    "expected_home",
    "expected_away",
    "sample_matches",
    "forecast_at",
    "made_after_kickoff",
    "evaluable",
    "status",
    "actual_score",
    "actual_outcome",
    "is_correct",
    "brier",
    "log_loss",
    "sources",
)


def _onehot(outcome: str) -> tuple[int, int, int]:
    return tuple(int(outcome == label) for label in OUTCOMES)  # type: ignore[return-value]


def brier_score(probs: Sequence[float], outcome: str) -> float:
    """Multi-class Brier: sum over 1/X/2 of (p - y)^2. 0 is perfect, 2 is worst."""
    return sum((p - y) ** 2 for p, y in zip(probs, _onehot(outcome), strict=True))


def log_loss(probs: Sequence[float], outcome: str) -> float:
    p = probs[OUTCOMES.index(outcome)]
    return -math.log(min(1.0, max(LOG_LOSS_EPS, p)))


def calibration(
    records: Iterable[ForecastRecord], model_version: str, *, width: float = BUCKET_WIDTH
) -> CalibrationReport:
    rows = list(records)
    evaluated = [r for r in rows if r.evaluable]
    excluded = sum(1 for r in rows if r.made_after_kickoff and r.status == "finished")
    n = len(evaluated)
    hit_by_outcome: dict[str, tuple[int, float | None]] = {}
    for label in OUTCOMES:
        predicted = [r for r in evaluated if r.predicted_outcome == label]
        hits = sum(1 for r in predicted if r.actual_outcome == label)
        hit_by_outcome[label] = (len(predicted), hits / len(predicted) if predicted else None)

    # Each forecast contributes three (probability, happened) pairs, one per outcome.
    edges = max(1, round(1 / width))
    sums = [[0, 0.0, 0] for _ in range(edges)]  # count, sum_p, hits
    for record in evaluated:
        assert record.actual_outcome is not None
        for p, y in zip(record.probabilities, _onehot(record.actual_outcome), strict=True):
            index = min(edges - 1, math.floor(p / width + BUCKET_EPS))
            sums[index][0] += 1
            sums[index][1] += p
            sums[index][2] += y
    buckets = tuple(
        CalibrationBucket(
            lower=round(i * width, 4),
            upper=round(min(1.0, (i + 1) * width), 4),
            count=count,
            mean_predicted=sum_p / count,
            observed_rate=hits / count,
        )
        for i, (count, sum_p, hits) in enumerate(sums)
        if count
    )
    return CalibrationReport(
        model_version=model_version,
        evaluated=n,
        excluded_post_kickoff=excluded,
        accuracy=(sum(1 for r in evaluated if r.is_correct) / n) if n else None,
        brier=(
            sum(brier_score(r.probabilities, r.actual_outcome or "X") for r in evaluated) / n
            if n
            else None
        ),
        log_loss=(
            sum(log_loss(r.probabilities, r.actual_outcome or "X") for r in evaluated) / n
            if n
            else None
        ),
        hit_rate_by_outcome=hit_by_outcome,
        buckets=buckets,
    )


def historical_hint(
    report: CalibrationReport | None,
    probabilities: Probabilities,
    *,
    min_sample: int = MIN_BUCKET_SAMPLE,
) -> HistoricalHint | None:
    """How often outcomes with a similar probability came true. None if too few data."""
    if report is None or not report.buckets:
        return None
    outcome = probabilities.favorite_label
    p = {"1": probabilities.home, "X": probabilities.draw, "2": probabilities.away}[outcome]
    bucket = report.bucket_for(p)
    if bucket is None or bucket.count < min_sample:
        return None
    return HistoricalHint(
        outcome=outcome,
        probability=p,
        bucket_label=bucket.label,
        observed_rate=bucket.observed_rate,
        sample=bucket.count,
    )


def llm_summary(
    report: CalibrationReport | None,
    hint: HistoricalHint | None,
    *,
    min_evaluated: int = MIN_EVALUATED_FOR_LLM,
) -> dict[str, Any] | None:
    """Short, factual block for the LLM so its confidence is grounded in history."""
    if report is None or report.evaluated < min_evaluated:
        return None
    summary: dict[str, Any] = {
        "model_version": report.model_version,
        "evaluated_prematch_forecasts": report.evaluated,
        "hit_rate": round(report.accuracy or 0.0, 3),
        "brier": round(report.brier or 0.0, 4),
        "log_loss": round(report.log_loss or 0.0, 4),
        "similar_probability": None,
        "note": "статистика прошлых прогнозов этой модели; вероятности матча не меняет",
    }
    if hint is not None:
        summary["similar_probability"] = {
            "outcome": hint.outcome,
            "bucket": hint.bucket_label,
            "observed_rate": round(hint.observed_rate, 3),
            "sample": hint.sample,
        }
    return summary


def export_csv(records: Iterable[ForecastRecord], path: Path) -> int:
    """Write every record (evaluable flag included) to CSV. Returns the row count."""
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for r in records:
            finished = r.actual_outcome is not None
            writer.writerow(
                {
                    "match_id": r.match_id,
                    "model_version": r.model_version,
                    "competition_code": r.competition_code,
                    "kickoff_utc": r.kickoff_utc.isoformat(),
                    "home_name": r.home_name,
                    "away_name": r.away_name,
                    "p_home": f"{r.p_home:.4f}",
                    "p_draw": f"{r.p_draw:.4f}",
                    "p_away": f"{r.p_away:.4f}",
                    "predicted_outcome": r.predicted_outcome,
                    "predicted_score": r.predicted_score,
                    "score_probability": f"{r.score_probability:.4f}",
                    "expected_home": f"{r.expected_home:.3f}",
                    "expected_away": f"{r.expected_away:.3f}",
                    "sample_matches": r.sample_matches,
                    "forecast_at": r.forecast_at.isoformat(),
                    "made_after_kickoff": int(r.made_after_kickoff),
                    "evaluable": int(r.evaluable),
                    "status": r.status,
                    "actual_score": r.actual_score or "",
                    "actual_outcome": r.actual_outcome or "",
                    "is_correct": "" if r.is_correct is None else int(r.is_correct),
                    "brier": (
                        f"{brier_score(r.probabilities, r.actual_outcome):.4f}"
                        if finished and r.actual_outcome
                        else ""
                    ),
                    "log_loss": (
                        f"{log_loss(r.probabilities, r.actual_outcome):.4f}"
                        if finished and r.actual_outcome
                        else ""
                    ),
                    "sources": "; ".join(r.sources),
                }
            )
            count += 1
    return count


def export_calibration_csv(report: CalibrationReport, path: Path) -> None:
    """Summary metrics + reliability table (bucket, mean predicted, observed, n)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["metric", "value"])
        writer.writerow(["model_version", report.model_version])
        writer.writerow(["evaluated_prematch_forecasts", report.evaluated])
        writer.writerow(["excluded_post_kickoff", report.excluded_post_kickoff])
        for name, value in (
            ("accuracy", report.accuracy),
            ("brier", report.brier),
            ("log_loss", report.log_loss),
        ):
            writer.writerow([name, "" if value is None else f"{value:.4f}"])
        for label, (count, rate) in report.hit_rate_by_outcome.items():
            writer.writerow([f"hit_rate_predicted_{label}", "" if rate is None else f"{rate:.4f}"])
            writer.writerow([f"count_predicted_{label}", count])
        writer.writerow([])
        writer.writerow(["bucket", "count", "mean_predicted", "observed_rate"])
        for bucket in report.buckets:
            writer.writerow(
                [
                    bucket.label,
                    bucket.count,
                    f"{bucket.mean_predicted:.4f}",
                    f"{bucket.observed_rate:.4f}",
                ]
            )
