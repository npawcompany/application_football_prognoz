from __future__ import annotations

import csv
import math
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from football_prognoz.ai.explainer import confidence_cap, parse_analysis
from football_prognoz.data.store import SQLiteStore
from football_prognoz.domain.history import ForecastRecord
from football_prognoz.domain.prediction import MatchFeatures, Probabilities
from football_prognoz.services.calibration import (
    CSV_COLUMNS,
    MIN_BUCKET_SAMPLE,
    brier_score,
    calibration,
    export_calibration_csv,
    export_csv,
    historical_hint,
    llm_summary,
    log_loss,
)

KICKOFF = datetime(2026, 9, 1, 15, 0, tzinfo=UTC)


def _rec(
    match_id: int,
    probs: tuple[float, float, float],
    actual: str | None,
    *,
    after_kickoff: bool = False,
) -> ForecastRecord:
    predicted = ("1", "X", "2")[probs.index(max(probs))]
    scores = {"1": (2, 0), "X": (1, 1), "2": (0, 1), None: (None, None)}
    home, away = scores[actual]
    return ForecastRecord(
        match_id=match_id,
        model_version="elo-poisson-v1",
        competition_code="PL",
        kickoff_utc=KICKOFF + timedelta(days=match_id),
        home_id=1,
        home_name="Alpha",
        away_id=2,
        away_name="Beta",
        p_home=probs[0],
        p_draw=probs[1],
        p_away=probs[2],
        predicted_outcome=predicted,
        predicted_score="1:0",
        score_probability=0.12,
        expected_home=1.5,
        expected_away=1.0,
        likely_outcomes=(),
        facts={},
        sources=("football-data.org",),
        sample_matches=20,
        forecast_at=KICKOFF
        + timedelta(days=match_id)
        + timedelta(hours=1 if after_kickoff else -5),
        made_after_kickoff=after_kickoff,
        status="finished" if actual else "scheduled",
        actual_home=home,
        actual_away=away,
        actual_outcome=actual,
        is_correct=None if actual is None else predicted == actual,
    )


def test_brier_and_log_loss_values() -> None:
    assert brier_score((1.0, 0.0, 0.0), "1") == 0.0
    assert brier_score((0.0, 0.0, 1.0), "1") == 2.0
    assert brier_score((0.5, 0.3, 0.2), "1") == pytest.approx(0.25 + 0.09 + 0.04)
    assert log_loss((0.5, 0.3, 0.2), "X") == pytest.approx(-math.log(0.3))
    assert math.isfinite(log_loss((1.0, 0.0, 0.0), "2"))  # clipped, not inf


def test_calibration_metrics_exclude_post_kickoff_and_unfinished() -> None:
    records = [
        _rec(1, (0.6, 0.25, 0.15), "1"),
        _rec(2, (0.6, 0.25, 0.15), "2"),
        _rec(3, (0.2, 0.3, 0.5), "2"),
        _rec(4, (0.2, 0.3, 0.5), "X"),
        _rec(5, (0.7, 0.2, 0.1), "1", after_kickoff=True),  # excluded
        _rec(6, (0.7, 0.2, 0.1), None),  # not finished
    ]
    report = calibration(records, "elo-poisson-v1")
    assert report.evaluated == 4
    assert report.excluded_post_kickoff == 1
    assert report.accuracy == pytest.approx(0.5)
    expected_brier = (
        brier_score((0.6, 0.25, 0.15), "1")
        + brier_score((0.6, 0.25, 0.15), "2")
        + brier_score((0.2, 0.3, 0.5), "2")
        + brier_score((0.2, 0.3, 0.5), "X")
    ) / 4
    assert report.brier == pytest.approx(expected_brier)
    assert report.hit_rate_by_outcome["1"] == (2, 0.5)
    assert report.hit_rate_by_outcome["2"] == (2, 0.5)
    assert report.hit_rate_by_outcome["X"] == (0, None)
    bucket = report.bucket_for(0.6)
    assert bucket is not None and bucket.label == "60–70%"
    assert bucket.count == 2 and bucket.observed_rate == pytest.approx(0.5)
    assert sum(b.count for b in report.buckets) == 12  # 3 outcomes x 4 forecasts
    assert report.bucket_for(1.0) is None or report.bucket_for(1.0).upper == 1.0


def test_empty_history_has_no_metrics() -> None:
    report = calibration([], "v")
    assert report.evaluated == 0 and report.accuracy is None and report.buckets == ()
    assert historical_hint(report, Probabilities(0.5, 0.3, 0.2)) is None
    assert llm_summary(report, None) is None


def _many(n: int, hit_every: int) -> list[ForecastRecord]:
    return [_rec(i, (0.55, 0.25, 0.2), "1" if i % hit_every == 0 else "2") for i in range(1, n + 1)]


def test_historical_hint_hidden_until_enough_samples() -> None:
    few = calibration(_many(MIN_BUCKET_SAMPLE - 1, 2), "v")
    assert historical_hint(few, Probabilities(0.52, 0.28, 0.2)) is None
    enough = calibration(_many(40, 2), "v")
    hint = historical_hint(enough, Probabilities(0.52, 0.28, 0.2))
    assert hint is not None
    assert hint.outcome == "1" and hint.sample == 40
    assert hint.observed_rate == pytest.approx(0.5)
    assert hint.text == (
        "Исторически такой исход сбывался в 50% случаев "
        "(выборка: 40 прогнозов с вероятностью 50–60%)."
    )


def test_llm_summary_needs_minimum_and_includes_bucket() -> None:
    report = calibration(_many(40, 4), "v")
    hint = historical_hint(report, Probabilities(0.55, 0.25, 0.2))
    summary = llm_summary(report, hint)
    assert summary is not None
    assert summary["evaluated_prematch_forecasts"] == 40
    assert summary["similar_probability"]["observed_rate"] == 0.25
    assert "не меняет" in summary["note"]
    assert llm_summary(calibration(_many(10, 2), "v"), None) is None


def test_export_csv_rows_and_flags(tmp_path: Path) -> None:
    records = [
        _rec(1, (0.6, 0.25, 0.15), "1"),
        _rec(2, (0.6, 0.25, 0.15), None),
        _rec(3, (0.2, 0.3, 0.5), "X", after_kickoff=True),
    ]
    path = tmp_path / "out" / "history.csv"
    assert export_csv(records, path) == 3
    with path.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert tuple(rows[0]) == CSV_COLUMNS
    assert rows[0]["evaluable"] == "1" and rows[0]["is_correct"] == "1"
    assert rows[0]["actual_score"] == "2:0"
    assert rows[0]["brier"] == f"{brier_score((0.6, 0.25, 0.15), '1'):.4f}"
    assert rows[1]["actual_score"] == "" and rows[1]["brier"] == ""
    assert rows[2]["made_after_kickoff"] == "1" and rows[2]["evaluable"] == "0"


def test_export_calibration_csv(tmp_path: Path) -> None:
    report = calibration(_many(30, 2), "v")
    path = tmp_path / "summary.csv"
    export_calibration_csv(report, path)
    text = path.read_text(encoding="utf-8")
    assert "evaluated_prematch_forecasts,30" in text
    assert "bucket,count,mean_predicted,observed_rate" in text
    assert "50–60%,30,0.5500,0.5000" in text


def test_store_roundtrip_and_stamp(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "c.db")
    assert store.forecast_history_stamp("elo-poisson-v1") == (0, None)
    record = _rec(1, (0.6, 0.25, 0.15), None)
    assert store.insert_forecast_record(record) is True
    assert store.insert_forecast_record(replace(record, p_home=0.1)) is False  # no duplicate
    loaded = store.get_forecast_record(1, "elo-poisson-v1")
    assert loaded == record
    assert store.forecast_history_stamp("elo-poisson-v1")[0] == 1


# --- confidence grounded in history (LLM never changes probabilities) -------------


def _features(sample: int = 30) -> MatchFeatures:
    return MatchFeatures("WWWWW", "LLLLL", 1700, 1400, "—", 1, 20, 2.5, 0.5, 0.6, 2.0, sample)


def test_confidence_cap_uses_history_rate() -> None:
    probs = Probabilities(0.7, 0.2, 0.1)
    assert confidence_cap(probs, _features()) == "high"
    assert confidence_cap(probs, _features(), history_rate=0.62) == "high"
    assert confidence_cap(probs, _features(), history_rate=0.41) == "medium"


def test_parse_analysis_lowers_high_confidence_when_history_is_weak() -> None:
    import json

    answer = json.dumps(
        {
            "summary": "Хозяева сильнее.",
            "home_factors": [],
            "away_factors": [],
            "favorite": "1",
            "verdict": "Перевес хозяев.",
            "confidence": "high",
            "confidence_reason": "Явный фаворит.",
        },
        ensure_ascii=False,
    )
    probs = Probabilities(0.7, 0.2, 0.1)
    assert parse_analysis(answer, probs, _features())["confidence"] == "high"
    weak = parse_analysis(answer, probs, _features(), history_rate=0.4)
    assert weak["confidence"] == "medium"
    assert "реже чем в половине случаев" in weak["confidence_reason"]


def test_bucket_edges_are_consistent() -> None:
    records = [_rec(i, (0.6, 0.3, 0.1), "1") for i in range(1, 4)]
    records.append(_rec(9, (1.0, 0.0, 0.0), "1"))
    report = calibration(records, "v")
    assert report.bucket_for(0.6).label == "60–70%"  # type: ignore[union-attr]
    assert report.bucket_for(0.6).count == 3  # type: ignore[union-attr]
    assert report.bucket_for(1.0).label == "90–100%"  # type: ignore[union-attr]
    assert report.bucket_for(0.3).label == "30–40%"  # type: ignore[union-attr]
