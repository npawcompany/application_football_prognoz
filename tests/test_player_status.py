from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from football_prognoz.ai.explainer import Explainer
from football_prognoz.config import ROOT_DIR
from football_prognoz.data.api_football import ApiFootballClient, StoreBudget
from football_prognoz.data.football_data_org import RateLimiter
from football_prognoz.data.store import SQLiteStore
from football_prognoz.domain.match import Match, MatchStatus, Score
from football_prognoz.models.predictor import Predictor
from football_prognoz.services.features import FeatureService
from football_prognoz.services.matches import MatchService
from football_prognoz.services.player_status import PlayerStatusService

AF = ROOT_DIR / "data" / "samples" / "api_football"
KICKOFF = datetime(2026, 9, 26, 14, 0, tzinfo=UTC)


def _sample(name: str) -> dict:
    return json.loads((AF / name).read_text(encoding="utf-8"))


def _envelope(items: list) -> dict:
    return {"errors": [], "results": len(items), "response": items}


RATINGS = _envelope(
    [
        {
            "team": {"id": 42, "name": "Arsenal"},
            "players": [
                {
                    "player": {"id": 1460, "name": "B. Saka"},
                    "statistics": [{"games": {"minutes": 90, "rating": "8.1", "position": "F"}}],
                },
                {
                    "player": {"id": 22224, "name": "G. Martinelli"},
                    "statistics": [{"games": {"minutes": 20, "rating": "6.5", "position": "F"}}],
                },
            ],
        }
    ]
)
SIDELINED = _envelope(
    [
        {
            "id": 1460,
            "sidelined": [{"type": "Hamstring Injury", "start": "2026-09-20", "end": "2026-10-10"}],
        }
    ]
)
TRANSFERS = _envelope(
    [
        {
            "player": {"id": 777, "name": "N. Newcomer"},
            "update": "2026-08-30T00:00:00+00:00",
            "transfers": [
                {
                    "date": "2026-08-15",
                    "type": "€ 40M",
                    "teams": {"in": {"id": 42, "name": "Arsenal"}, "out": {"id": 1, "name": "X"}},
                }
            ],
        }
    ]
)


class Router:
    def __init__(self, overrides: dict[str, dict] | None = None) -> None:
        self.calls: list[str] = []
        self.overrides = overrides or {}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.calls.append(path)
        if path in self.overrides:
            return httpx.Response(200, json=self.overrides[path])
        fixture = request.url.params.get("fixture")
        if path == "/fixtures":
            return httpx.Response(200, json=_sample("fixtures_season.json"))
        if path == "/injuries":
            return httpx.Response(200, json=_sample("injuries_fixture_pl.json"))
        if path == "/fixtures/events":
            if fixture == "1299990":
                return httpx.Response(200, json=_sample("fixtures_events_pl.json"))
            return httpx.Response(200, json=_envelope([]))
        if path == "/fixtures/players":
            return httpx.Response(200, json=RATINGS)
        if path == "/sidelined":
            return httpx.Response(200, json=SIDELINED)
        if path == "/transfers":
            team = request.url.params.get("team")
            return httpx.Response(200, json=TRANSFERS if team == "42" else _envelope([]))
        if path == "/fixtures/lineups":
            return httpx.Response(200, json=_sample("fixtures_lineups.json"))
        return httpx.Response(404)


def _match(status: MatchStatus = MatchStatus.SCHEDULED) -> Match:
    return Match(
        id=201,
        competition_code="PL",
        utc_date=KICKOFF,
        status=status,
        matchday=6,
        home_id=57,
        home_name="Arsenal FC",
        away_id=65,
        away_name="Manchester City FC",
        score=Score(None, None),
    )


def _service(
    tmp_path: Path,
    router: Router,
    *,
    now: datetime | None = None,
    budget_limit: int = 90,
) -> tuple[PlayerStatusService, SQLiteStore]:
    store = SQLiteStore(tmp_path / "ps.db")
    budget = StoreBudget(store, budget_limit)
    http = httpx.Client(
        base_url="https://v3.football.api-sports.io", transport=httpx.MockTransport(router)
    )
    client = ApiFootballClient("af-key", client=http, limiter=RateLimiter(1000), budget=budget)
    moment = now or KICKOFF - timedelta(days=2)
    return PlayerStatusService(client, store, budget=budget, now=lambda: moment), store


def test_disabled_without_key_makes_zero_calls(tmp_path: Path) -> None:
    router = Router()
    store = SQLiteStore(tmp_path / "off.db")
    http = httpx.Client(transport=httpx.MockTransport(router))
    service = PlayerStatusService(ApiFootballClient("", client=http), store)
    assert service.enabled is False
    assert service.report_for(_match()) is None
    assert PlayerStatusService(None, store).report_for(_match()) is None
    assert router.calls == []


def test_match_service_without_api_football_is_unchanged(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "ms.db")
    store.upsert_matches([_match()])

    class NoHttp:
        """football-data.org stub without get_team/get_match: cache-only forecast."""

    service = MatchService(
        client=NoHttp(),  # type: ignore[arg-type]
        store=store,
        features=FeatureService(store),
        predictor=Predictor(),
        explainer=Explainer(None, "deepseek-v4.1-flash"),
    )
    assert service.player_status_enabled is False
    assert service.llm_enabled is False
    base = service.forecast(_match(), explain=False)
    enriched = service.enrich(base)
    assert enriched.player_status is None
    assert enriched.explanation is None
    assert enriched.explanation_error is None
    assert enriched.probabilities == base.probabilities


def test_full_report_maps_match_and_marks_key_absences(tmp_path: Path) -> None:
    router = Router()
    service, store = _service(tmp_path, router)
    report = service.report_for(_match())
    assert report is not None
    assert report.af_fixture_id == 1300001
    assert store.get_af_fixture(201) == 1300001
    assert store.get_af_team(57) == 42
    assert store.get_af_team(65) == 50
    home = {a.player_name: a for a in report.home.absences}
    assert home["B. Saka"].key_player is True
    assert home["B. Saka"].expected_return == "2026-10-10"
    assert home["G. Martinelli"].is_certain is False
    assert home["G. Martinelli"].key_player is False  # 20 minutes only
    assert report.away.absences[0].is_suspension
    assert [c.player_name for c in report.home.red_cards] == ["W. Saliba"]
    assert report.away.red_cards == ()
    assert report.home.transfers[0].player_name == "N. Newcomer"
    assert report.home.lineup is None  # two days before kick-off: no lineup request
    assert "/fixtures/lineups" not in router.calls
    assert any("травмы" in source for source in report.sources)
    assert report.notes == ()


def test_second_report_is_served_from_sqlite(tmp_path: Path) -> None:
    router = Router()
    service, _store = _service(tmp_path, router)
    service.report_for(_match())
    first = len(router.calls)
    again = service.report_for(_match())
    assert again is not None and again.has_data()
    assert len(router.calls) == first


def test_lineups_requested_near_kickoff(tmp_path: Path) -> None:
    router = Router(
        overrides={
            "/fixtures/lineups": {
                "errors": [],
                "response": [
                    {
                        "team": {"id": 50, "name": "Manchester City"},
                        "formation": "4-3-3",
                        "startXI": [{"player": {"id": 617, "name": "Ederson", "pos": "G"}}],
                        "substitutes": [],
                        "coach": {"id": 4, "name": "Guardiola"},
                    }
                ],
            }
        }
    )
    service, _store = _service(tmp_path, router, now=KICKOFF - timedelta(minutes=30))
    report = service.report_for(_match())
    assert report is not None
    assert "/fixtures/lineups" in router.calls
    assert report.away.lineup is not None
    assert report.away.lineup.formation == "4-3-3"


def test_plan_error_is_a_quiet_note_and_blocks_retries(tmp_path: Path) -> None:
    router = Router(overrides={"/fixtures": _sample("error_plan.json")})
    service, _store = _service(tmp_path, router)
    report = service.report_for(_match())
    assert report is not None
    assert not report.has_data()
    assert any("Тариф" in note for note in report.notes)
    calls = len(router.calls)
    again = service.report_for(_match())
    assert again is not None and any("сезону 2026" in note for note in again.notes)
    assert len(router.calls) == calls


def test_low_budget_skips_optional_endpoints(tmp_path: Path) -> None:
    router = Router()
    service, _store = _service(tmp_path, router, budget_limit=15)
    report = service.report_for(_match())
    assert report is not None
    assert "/transfers" not in router.calls
    assert "/fixtures/players" not in router.calls
    assert any("пропущены" in note for note in report.notes)
    assert report.home.absences  # injuries still fetched


def test_unknown_match_and_league(tmp_path: Path) -> None:
    router = Router()
    service, _store = _service(tmp_path, router)
    moved = Match(**{**_match().__dict__, "utc_date": KICKOFF + timedelta(days=10)})
    report = service.report_for(moved)
    assert report is not None and any("не найден" in n for n in report.notes)
    other = Match(**{**_match().__dict__, "competition_code": "XYZ"})
    calls = len(router.calls)
    report = service.report_for(other)
    assert report is not None and any("не сопоставлена" in n for n in report.notes)
    assert len(router.calls) == calls


@pytest.mark.parametrize("path", ["/injuries", "/fixtures/events"])
def test_mid_report_error_keeps_partial_data(tmp_path: Path, path: str) -> None:
    router = Router(overrides={path: {"errors": {"rateLimit": "Too many requests"}}})
    service, _store = _service(tmp_path, router)
    report = service.report_for(_match())
    assert report is not None
    assert report.af_fixture_id == 1300001
    assert any("лимит" in note for note in report.notes)
