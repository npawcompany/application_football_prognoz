"""football-data.org client and service fixes: errors, limiter, seasons, groups, day windows."""

from __future__ import annotations

import json
import threading
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from football_prognoz.config import ROOT_DIR
from football_prognoz.data.football_data_org import (
    FootballDataError,
    FootballDataOrgClient,
    RateLimiter,
)
from football_prognoz.data.store import SQLiteStore
from football_prognoz.domain.match import Match, MatchStatus, Score
from football_prognoz.domain.team import Competition, StandingRow
from football_prognoz.services.matches import (
    MatchService,
    current_season_year,
    matches_cache_key,
)

SAMPLES = ROOT_DIR / "data" / "samples"


def _client(handler, limiter: RateLimiter | None = None) -> FootballDataOrgClient:
    http = httpx.Client(
        transport=httpx.MockTransport(handler), base_url="https://api.football-data.org/v4"
    )
    return FootballDataOrgClient("k", client=http, limiter=limiter or RateLimiter(100))


def test_network_error_becomes_football_data_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    with pytest.raises(FootballDataError) as info:
        _client(handler).list_competitions()
    assert info.value.status_code is None
    assert "Нет связи" in str(info.value)


def test_unauthorized_key_has_status_and_russian_message() -> None:
    client = _client(lambda request: httpx.Response(401, json={"message": "x"}))
    with pytest.raises(FootballDataError) as info:
        client.list_competitions()
    assert info.value.status_code == 401
    assert "не принят" in str(info.value)


def test_competitions_keep_area_type_and_current_season(competitions_payload: dict) -> None:
    items = _client(lambda request: httpx.Response(200, json=competitions_payload))
    pl = next(item for item in items.list_competitions() if item.code == "PL")
    assert pl.area_name == "England"
    assert pl.area_code == "ENG"
    assert pl.type == "LEAGUE"
    assert pl.season_start == date(2026, 8, 15)
    assert pl.season_end == date(2027, 5, 23)


def test_tournament_standings_keep_every_group() -> None:
    def table(group: str, team_ids: list[int]) -> dict:
        return {
            "stage": "GROUP_STAGE",
            "type": "TOTAL",
            "group": group,
            "table": [
                {"position": pos, "team": {"id": tid, "name": f"T{tid}"}, "playedGames": 1}
                for pos, tid in enumerate(team_ids, start=1)
            ],
        }

    payload = {"standings": [table("GROUP_A", [1, 2]), table("GROUP_B", [3, 4])]}
    rows = _client(lambda request: httpx.Response(200, json=payload)).list_standings("WC")
    assert [row.team_id for row in rows] == [1, 2, 3, 4]
    assert {row.group for row in rows} == {"GROUP_A", "GROUP_B"}


def test_matches_between_reads_competition_code_and_skips_paid() -> None:
    payload = json.loads((SAMPLES / "matches_range.json").read_text(encoding="utf-8"))
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(dict(request.url.params))
        assert request.url.path.endswith("/matches")
        return httpx.Response(200, json=payload)

    matches = _client(handler).list_matches_between("2026-09-28", "2026-10-06")
    assert seen == {"dateFrom": "2026-09-28", "dateTo": "2026-10-06"}
    assert [(m.competition_code, m.id) for m in matches] == [("CL", 600002), ("PL", 600001)]


def test_rate_limiter_gives_up_instead_of_blocking_when_asked() -> None:
    limiter = RateLimiter(2)
    assert limiter.wait() and limiter.wait()
    started = time.monotonic()
    assert limiter.wait(max_wait=0.1) is False
    assert time.monotonic() - started < 0.5


def test_rate_limiter_does_not_hold_the_lock_while_sleeping(monkeypatch) -> None:
    limiter = RateLimiter(1)
    limiter.wait()
    sleeping = threading.Event()
    release = threading.Event()

    def fake_sleep(_seconds: float) -> None:
        sleeping.set()
        release.wait(2)

    monkeypatch.setattr("football_prognoz.data.football_data_org.time.sleep", fake_sleep)
    worker = threading.Thread(target=limiter.wait)
    worker.start()
    assert sleeping.wait(2)
    # another caller can still ask (and be told "too far") while the first one sleeps
    assert limiter.reserve(max_wait=0.0) is None
    release.set()
    worker.join(2)


def test_current_season_year_per_competition() -> None:
    march = datetime(2026, 3, 1, tzinfo=UTC)
    september = datetime(2026, 9, 1, tzinfo=UTC)
    assert current_season_year(march, "PL") == 2025
    assert current_season_year(september, "PL") == 2026
    assert current_season_year(march, "BSA") == 2026  # calendar-year league
    assert current_season_year(march, "WC") is None  # API currentSeason decides
    assert current_season_year(september, "EC") is None


class _FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.fail: FootballDataError | None = None

    def list_matches(self, code: str, **kwargs):
        self.calls.append(("matches", code, kwargs))
        return [_m(1, code, datetime.now(UTC) + timedelta(days=3))]

    def list_standings(self, code: str):
        self.calls.append(("standings", code))
        return [StandingRow(10, "Home", 1, 1, 1, 0, 0, 3, 1, 0)]

    def list_matches_between(self, date_from: str, date_to: str):
        self.calls.append(("between", date_from, date_to))
        if self.fail is not None:
            raise self.fail
        return [
            _m(101, "PL", datetime(2026, 10, 3, 14, 0, tzinfo=UTC)),
            _m(102, "CL", datetime(2026, 10, 1, 19, 0, tzinfo=UTC)),
        ]

    def list_competitions(self):
        self.calls.append(("competitions",))
        if self.fail is not None:
            raise self.fail
        return [Competition(2021, "PL", "Premier League")]


def _m(match_id: int, code: str, when: datetime) -> Match:
    return Match(
        match_id, code, when, MatchStatus.TIMED, 1, 10, "Home", 20, "Away", Score(None, None)
    )


def _service(tmp_path: Path) -> tuple[MatchService, _FakeClient, SQLiteStore]:
    from football_prognoz.ai.explainer import Explainer
    from football_prognoz.models.predictor import Predictor
    from football_prognoz.services.features import FeatureService

    store = SQLiteStore(tmp_path / "t.db")
    client = _FakeClient()
    service = MatchService(
        client=client,  # type: ignore[arg-type]
        store=store,
        features=FeatureService(store),
        predictor=Predictor(),
        explainer=Explainer(None, "m"),
    )
    return service, client, store


def test_refresh_competition_asks_api_for_current_season(tmp_path: Path) -> None:
    service, client, store = _service(tmp_path)
    service.refresh_competition("EC")
    assert client.calls[0] == ("matches", "EC", {})
    assert store.fetched_at(matches_cache_key("EC")) is not None


def test_day_matches_one_request_per_week_then_cache(tmp_path: Path) -> None:
    service, client, _store = _service(tmp_path)
    now = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)
    first = service.day_matches(date(2026, 10, 3), tz=UTC, now=now)
    second = service.day_matches(date(2026, 10, 1), tz=UTC, now=now)  # same week
    assert [m.id for m in first] == [101]
    assert [m.id for m in second] == [102]
    between = [call for call in client.calls if call[0] == "between"]
    assert between == [("between", "2026-09-27", "2026-10-05")]
    only_cl = service.day_matches(date(2026, 10, 1), tz=UTC, now=now, codes=["PL"])
    assert only_cl == []


def test_day_matches_falls_back_to_cache_on_errors(tmp_path: Path) -> None:
    service, client, _store = _service(tmp_path)
    now = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)
    service.day_matches(date(2026, 10, 3), tz=UTC, now=now)
    client.fail = FootballDataError("offline")
    again = service.day_matches(date(2026, 10, 3), tz=UTC, now=now, force=True)
    assert [m.id for m in again] == [101]
    client.fail = FootballDataError("bad key", status_code=401)
    with pytest.raises(FootballDataError):
        service.day_matches(date(2026, 12, 3), tz=UTC, now=now)


def test_list_competitions_flags_a_rejected_key(tmp_path: Path) -> None:
    service, client, _store = _service(tmp_path)
    client.fail = FootballDataError("bad", status_code=403)
    assert service.list_competitions(force=True)  # falls back to the free-tier list
    assert service.key_rejected is True
    client.fail = None
    service.validate_key()
    assert service.key_rejected is False


def test_store_competition_metadata_counts_and_teams(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "s.db")
    store.upsert_competitions(
        [
            Competition(
                2021,
                "PL",
                "Premier League",
                type="LEAGUE",
                area_name="England",
                season_start=date(2026, 8, 15),
                season_end=date(2027, 5, 23),
            )
        ]
    )
    [pl] = store.list_competitions()
    assert pl.area_name == "England" and pl.season_end == date(2027, 5, 23)
    now = datetime(2026, 9, 29, tzinfo=UTC)
    store.upsert_matches(
        [
            _m(1, "PL", now + timedelta(days=2)),
            _m(2, "PL", now + timedelta(days=400)),
            _m(3, "CL", now - timedelta(days=1)),
        ]
    )
    assert store.upcoming_counts(now, now + timedelta(days=183)) == {"PL": 1}
    day = store.list_matches_between(now, now + timedelta(days=3))
    assert [m.id for m in day] == [1]
    teams = store.teams_by_competition()
    assert sorted(teams) == ["CL", "PL"]
    assert [team.name for team in teams["PL"]] == ["Away", "Home"]


def test_enrich_reports_step_and_stops_when_cancelled(tmp_path: Path, monkeypatch) -> None:
    from football_prognoz.services.matches import Cancelled

    service, _client, _store = _service(tmp_path)
    order: list[str] = []
    names = (
        "attach_details",
        "attach_player_status",
        "attach_news",
        "attach_markets",
        "attach_saved_analyses",
        "explain_forecast",
        "summarize_news",
    )
    for name in names:
        monkeypatch.setattr(
            service, name, lambda fc, _n=name: (order.append(_n), fc)[1], raising=True
        )
    monkeypatch.setattr(type(service._explainer), "enabled", property(lambda self: True))
    steps: list[object] = []
    service.enrich("F", on_step=steps.append)  # type: ignore[arg-type]
    assert order == list(names)
    assert steps == ["F", "F"]  # before the LLM (squads, saved result) and after the analysis

    order.clear()
    cancel = threading.Event()
    monkeypatch.setattr(
        service, "attach_player_status", lambda fc: (order.append("status"), cancel.set(), fc)[2]
    )
    with pytest.raises(Cancelled):
        service.enrich("F", cancel=cancel)  # type: ignore[arg-type]
    assert order == ["attach_details", "status"]  # news and LLM never ran


def test_forecast_without_details_makes_no_requests(tmp_path: Path) -> None:
    service, client, store = _service(tmp_path)
    match = _m(7, "PL", datetime.now(UTC) + timedelta(days=1))
    store.upsert_matches([match])

    def boom(*_args, **_kwargs):
        raise AssertionError("no HTTP on the UI path")

    client.get_team = boom  # type: ignore[attr-defined]
    client.get_match = boom  # type: ignore[attr-defined]
    result = service.forecast(match, explain=False, details=False)
    assert result.match.id == 7
    assert client.calls == []


def test_check_key_tells_rejected_key_from_no_network(tmp_path: Path) -> None:
    service, client, _store = _service(tmp_path)
    assert service.check_key().ok is True
    client.fail = FootballDataError("Ключ не принят", status_code=401)
    result = service.check_key()
    assert (result.ok, result.rejected) == (False, True)
    assert service.key_rejected is True
    client.fail = FootballDataError("Нет связи с football-data.org")
    result = service.check_key()
    assert (result.ok, result.rejected) == (False, False)


def test_cached_match_days_marks_the_picker_month_without_http(tmp_path: Path) -> None:
    service, client, _store = _service(tmp_path)
    now = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)
    service.day_matches(date(2026, 10, 3), tz=UTC, now=now)
    calls = len(client.calls)
    days = service.cached_match_days(date(2026, 10, 1), date(2026, 10, 31), tz=UTC)
    assert days == [date(2026, 10, 1), date(2026, 10, 3)]
    assert service.cached_match_days(
        date(2026, 10, 1), date(2026, 10, 31), codes=["PL"], tz=UTC
    ) == [date(2026, 10, 3)]
    assert len(client.calls) == calls  # SQLite only
