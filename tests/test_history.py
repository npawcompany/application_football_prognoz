from __future__ import annotations

import sqlite3
import threading
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from football_prognoz.data.store import SQLiteStore
from football_prognoz.domain.match import Match, MatchStatus, Score
from football_prognoz.models.predictor import MODEL_VERSION
from football_prognoz.services.history import ForecastHistoryService, record_status

T0 = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
TEAMS = {1: "Alpha FC", 2: "Beta FC", 3: "Gamma FC", 4: "Delta FC"}


def _m(
    match_id: int,
    when: datetime,
    home: int,
    away: int,
    status: MatchStatus = MatchStatus.SCHEDULED,
    score: tuple[int, int] | None = None,
) -> Match:
    return Match(
        id=match_id,
        competition_code="PL",
        utc_date=when,
        status=status,
        matchday=None,
        home_id=home,
        home_name=TEAMS[home],
        away_id=away,
        away_name=TEAMS[away],
        score=Score(*(score or (None, None))),
    )


def _history() -> list[Match]:
    """Twelve finished matches before T0 so features have a real sample."""
    pairs = [(1, 2), (3, 4), (1, 3), (2, 4), (1, 4), (2, 3)] * 2
    scores = [(2, 0), (1, 1), (3, 1), (0, 2), (2, 2), (1, 0)] * 2
    return [
        _m(
            100 + i,
            T0 - timedelta(days=40 - 3 * i),
            h,
            a,
            MatchStatus.FINISHED,
            scores[i],
        )
        for i, (h, a) in enumerate(pairs)
    ]


UPCOMING = _m(500, T0 + timedelta(days=2), 1, 2)
LATER = _m(501, T0 + timedelta(days=5), 3, 4)
FAR = _m(502, T0 + timedelta(days=40), 2, 1)  # outside the ±14 day window


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def store(tmp_path: Path) -> SQLiteStore:
    store = SQLiteStore(tmp_path / "h.db")
    store.upsert_matches([*_history(), UPCOMING, LATER, FAR])
    return store


def _service(store: SQLiteStore, clock: Clock, refresh=None) -> ForecastHistoryService:
    return ForecastHistoryService(store, refresh=refresh, now=clock)


def _rows(store: SQLiteStore) -> int:
    with sqlite3.connect(store.path) as conn:
        return conn.execute("SELECT COUNT(*) FROM forecast_history").fetchone()[0]


def test_collect_stores_forecasts_for_window_with_progress(store: SQLiteStore) -> None:
    clock = Clock(T0)
    seen: list[tuple[int, int, str]] = []
    result = _service(store, clock).collect(["pl"], progress=lambda d, t, m: seen.append((d, t, m)))
    ids = {r.match_id for r in store.list_forecast_records(MODEL_VERSION)}
    assert 500 in ids and 501 in ids and 502 not in ids
    assert result.inserted == len(ids)
    assert seen[-1][0] == seen[-1][1] == result.total
    record = store.get_forecast_record(500, MODEL_VERSION)
    assert record is not None
    assert record.made_after_kickoff is False
    assert record.status == "scheduled"
    assert abs(record.p_home + record.p_draw + record.p_away - 1) < 1e-6
    assert record.predicted_outcome in {"1", "X", "2"}
    assert record.likely_outcomes[0]["outcome"] == record.predicted_outcome
    assert len([x for x in record.likely_outcomes if "score" in x]) == 3
    assert record.facts["direct"]["sample_matches"] == 12
    assert "elo" in record.facts["indirect"]
    assert record.sources and record.forecast_at == T0
    assert record.actual_score is None


def test_rerun_is_idempotent(store: SQLiteStore) -> None:
    clock = Clock(T0)
    service = _service(store, clock)
    first = service.collect(["PL"])
    count = _rows(store)
    second = service.collect(["PL"])
    assert _rows(store) == count
    assert second.inserted == 0
    assert second.unchanged == first.inserted


def test_prematch_forecast_is_refreshed_before_kickoff(store: SQLiteStore) -> None:
    clock = Clock(T0)
    service = _service(store, clock)
    service.collect(["PL"])
    before = store.get_forecast_record(500, MODEL_VERSION)
    # New result before kick-off changes the features -> the pre-match row is updated.
    store.upsert_matches([_m(150, T0 + timedelta(hours=1), 2, 1, MatchStatus.FINISHED, (5, 0))])
    clock.now = T0 + timedelta(hours=3)
    result = service.collect(["PL"])
    after = store.get_forecast_record(500, MODEL_VERSION)
    assert result.updated >= 1
    assert after is not None and before is not None
    assert after.forecast_at == T0 + timedelta(hours=3)
    assert after.p_home != before.p_home
    assert _rows(store) == result.total


def test_prematch_forecast_is_frozen_after_kickoff_and_result_filled(
    store: SQLiteStore,
) -> None:
    clock = Clock(T0)
    service = _service(store, clock)
    service.collect(["PL"])
    frozen = store.get_forecast_record(500, MODEL_VERSION)
    assert frozen is not None
    # The match is played; new data would change the forecast, but it must not.
    store.upsert_matches(
        [
            _m(151, UPCOMING.utc_date - timedelta(hours=5), 2, 3, MatchStatus.FINISHED, (6, 0)),
            replace(UPCOMING, status=MatchStatus.FINISHED, score=Score(0, 3)),
        ]
    )
    clock.now = UPCOMING.utc_date + timedelta(hours=3)
    result = service.collect(["PL"])
    after = store.get_forecast_record(500, MODEL_VERSION)
    assert after is not None
    assert (after.p_home, after.p_draw, after.p_away) == (
        frozen.p_home,
        frozen.p_draw,
        frozen.p_away,
    )
    assert after.forecast_at == frozen.forecast_at
    assert after.facts == frozen.facts
    assert after.status == "finished"
    assert after.actual_score == "0:3"
    assert after.actual_outcome == "2"
    assert after.is_correct is (frozen.predicted_outcome == "2")
    assert after.evaluable is True
    assert result.results_filled >= 1


def test_store_guard_rejects_prediction_update_after_kickoff(store: SQLiteStore) -> None:
    clock = Clock(T0)
    service = _service(store, clock)
    service.collect(["PL"])
    record = store.get_forecast_record(500, MODEL_VERSION)
    assert record is not None
    late = replace(record, p_home=0.99, forecast_at=UPCOMING.utc_date + timedelta(minutes=1))
    assert store.update_forecast_prediction(late) is False
    assert store.get_forecast_record(500, MODEL_VERSION).p_home == record.p_home  # type: ignore[union-attr]


def test_forecast_first_made_after_kickoff_is_flagged(store: SQLiteStore) -> None:
    played = _m(600, T0 - timedelta(days=1), 3, 1, MatchStatus.FINISHED, (1, 1))
    store.upsert_matches([played])
    result = _service(store, Clock(T0)).collect(["PL"])
    record = store.get_forecast_record(600, MODEL_VERSION)
    assert record is not None
    assert record.made_after_kickoff is True
    assert record.actual_score == "1:1"
    assert record.evaluable is False
    assert result.post_kickoff >= 1


def test_cancel_stops_the_run(store: SQLiteStore) -> None:
    cancel = threading.Event()

    def progress(done: int, total: int, _message: str) -> None:
        if done == 1:
            cancel.set()

    result = _service(store, Clock(T0)).collect(["PL"], progress=progress, cancel=cancel)
    assert result.cancelled is True
    assert result.inserted == 1
    assert _rows(store) == 1
    assert "остановлен" in result.summary


def test_status_mapping() -> None:
    assert record_status(MatchStatus.TIMED) == "scheduled"
    assert record_status(MatchStatus.IN_PLAY) == "live"
    assert record_status(MatchStatus.PAUSED) == "live"
    assert record_status(MatchStatus.FINISHED) == "finished"
    assert record_status(MatchStatus.AWARDED) == "finished"
    assert record_status(MatchStatus.POSTPONED) == "postponed"
    assert record_status(MatchStatus.CANCELLED) == "cancelled"


def test_postponed_match_status_is_tracked(store: SQLiteStore) -> None:
    clock = Clock(T0)
    service = _service(store, clock)
    service.collect(["PL"])
    store.upsert_matches([replace(LATER, status=MatchStatus.POSTPONED)])
    service.collect(["PL"])
    record = store.get_forecast_record(501, MODEL_VERSION)
    assert record is not None and record.status == "postponed"
    assert record.made_after_kickoff is False


def test_refresh_forced_only_when_results_are_pending(store: SQLiteStore) -> None:
    calls: list[tuple[str, bool]] = []

    def refresh(code: str, force: bool) -> list[Match]:
        calls.append((code, force))
        return store.list_matches(code)

    clock = Clock(T0)
    service = _service(store, clock, refresh)
    service.collect(["PL"])
    assert calls[-1] == ("PL", False)
    clock.now = UPCOMING.utc_date + timedelta(hours=3)
    service.collect(["PL"])
    assert calls[-1] == ("PL", True)


def test_refresh_error_is_reported_and_cache_used(store: SQLiteStore) -> None:
    def refresh(_code: str, _force: bool) -> list[Match]:
        raise RuntimeError("HTTP 429")

    result = _service(store, Clock(T0), refresh).collect(["PL"])
    assert result.errors == ("PL: HTTP 429",)
    assert result.inserted >= 2


def test_clear_cache_keeps_forecast_history(store: SQLiteStore) -> None:
    _service(store, Clock(T0)).collect(["PL"])
    count = _rows(store)
    store.clear_all()
    assert _rows(store) == count
