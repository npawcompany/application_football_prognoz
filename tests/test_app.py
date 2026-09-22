from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from football_prognoz.config import Settings
from football_prognoz.domain.match import Match, MatchStatus, Score
from football_prognoz.domain.prediction import (
    MatchFeatures,
    MatchForecast,
    Probabilities,
    Scoreline,
)
from football_prognoz.domain.team import Competition, Team
from football_prognoz.services.filters import FixtureQuery, MatchStatusFilter
from football_prognoz.ui.app import FootballApp


class _Handle:
    def __init__(self) -> None:
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True


class FakePage:
    """Minimal page: overlay list + run_task that only schedules."""

    def __init__(self) -> None:
        self.overlay: list = []
        self.dialogs: list = []
        self.controls: list = []
        self.updates = 0
        self.scheduled: list = []
        self.width = 1440
        self.title = ""
        self.appbar = None
        self.navigation_bar = None
        self.bgcolor = None
        self.theme_mode = None
        self.theme = None
        self.padding = 0
        self.window = SimpleNamespace(
            width=1440,
            height=900,
            min_width=800,
            min_height=640,
            bgcolor=None,
        )
        self.on_resize = None
        self.on_resized = None

    def add(self, *controls: object) -> None:
        self.controls.extend(controls)

    def clean(self) -> None:
        self.controls.clear()

    def update(self) -> None:
        self.updates += 1

    def show_dialog(self, dialog: object) -> None:
        self.dialogs.append(dialog)

    def pop_dialog(self) -> None:
        if self.dialogs:
            self.dialogs.pop()

    def run_task(self, fn, *args, **kwargs):
        handle = _Handle()
        self.scheduled.append((fn, args, kwargs, handle))
        return handle


class FakeMatchService:
    def __init__(self, competitions: list[Competition] | None = None) -> None:
        self.competitions = competitions or [
            Competition(id=2021, code="PL", name="Premier League"),
            Competition(id=2014, code="PD", name="La Liga"),
            Competition(id=2019, code="SA", name="Serie A"),
        ]
        self.cached_calls = 0
        self.bootstrap_calls = 0
        self.list_calls = 0
        self.upcoming_calls = 0
        self.fixture_calls = 0
        self.forecast_calls = 0
        self.forecast_explain: list[bool] = []
        self.explain_calls = 0
        self.clear_calls = 0
        self.prefetch_calls: list[str] = []
        self.ping_calls = 0

    def cached_teams(self) -> list[Team]:
        return [
            Team(id=64, name="Liverpool"),
            Team(id=57, name="Arsenal"),
            Team(id=5, name="Bayern"),
        ]

    def cached_competitions(self) -> list[Competition]:
        self.cached_calls += 1
        return list(self.competitions)

    def bootstrap(self, progress=None) -> list[Competition]:
        self.bootstrap_calls += 1
        if progress is not None:
            progress("Лиги", 1, 1)
        return list(self.competitions)

    def list_competitions(self, *, force: bool = False) -> list[Competition]:
        self.list_calls += 1
        return list(self.competitions)

    def upcoming(self, code: str, *, force: bool = False) -> list[Match]:
        self.upcoming_calls += 1
        return []

    def competition_matches(self, code: str, *, force: bool = False) -> list[Match]:
        self.fixture_calls += 1
        return [
            Match(
                id=7,
                competition_code=code,
                utc_date=datetime.now(UTC) - timedelta(days=2),
                status=MatchStatus.FINISHED,
                matchday=5,
                home_id=64,
                home_name="Liverpool",
                away_id=66,
                away_name="Man United",
                score=Score(2, 1),
            ),
            Match(
                id=42,
                competition_code=code,
                utc_date=datetime.now(UTC) + timedelta(days=1),
                status=MatchStatus.SCHEDULED,
                matchday=6,
                home_id=57,
                home_name="Arsenal",
                away_id=65,
                away_name="Man City",
                score=Score(None, None),
            ),
        ]

    def forecast(self, match: Match, *, explain: bool = True) -> MatchForecast:
        self.forecast_calls += 1
        self.forecast_explain.append(explain)
        return _forecast_for(match)

    def explain_forecast(self, forecast: MatchForecast) -> MatchForecast:
        self.explain_calls += 1
        return forecast

    def clear_cache(self) -> None:
        self.clear_calls += 1

    def prefetch_competition(self, code: str, *, force: bool = False) -> list[Match]:
        self.prefetch_calls.append(code)
        return []

    def ping(self) -> list[Competition]:
        self.ping_calls += 1
        return list(self.competitions)


def _forecast_for(match: Match) -> MatchForecast:
    return MatchForecast(
        match=match,
        probabilities=Probabilities(0.4, 0.3, 0.3),
        features=MatchFeatures(
            home_form="WWDLW",
            away_form="WDWWL",
            home_elo=1600.0,
            away_elo=1580.0,
            h2h_summary="Нет очных встреч",
            home_position=2,
            away_position=1,
            home_recent_goals_for=2.0,
            home_recent_goals_against=0.8,
            away_recent_goals_for=2.2,
            away_recent_goals_against=1.0,
            sample_matches=20,
        ),
        explanation=None,
        scoreline=Scoreline(1, 1, 0.14, 1.5, 1.5),
    )


def _match() -> Match:
    return Match(
        id=42,
        competition_code="PL",
        utc_date=datetime.now(UTC) + timedelta(days=1),
        status=MatchStatus.SCHEDULED,
        matchday=6,
        home_id=57,
        home_name="Arsenal",
        away_id=65,
        away_name="Man City",
        score=Score(None, None),
    )


def _settings(**kwargs: object) -> Settings:
    values: dict[str, object] = {"football_data_api_key": "test-key"}
    values.update(kwargs)
    return Settings(**values)  # type: ignore[arg-type]


def _app(
    *,
    service: FakeMatchService | None = None,
    settings: Settings | None = None,
) -> tuple[FootballApp, FakePage, FakeMatchService]:
    page = FakePage()
    settings = settings or _settings()
    service = service or FakeMatchService()
    app = FootballApp(page, service, settings)  # type: ignore[arg-type]
    return app, page, service


def _drain_last(page: FakePage) -> None:
    fn, args, kwargs, _handle = page.scheduled[-1]
    asyncio.run(fn(*args, **kwargs))


def test_init_with_key_reads_cache_not_network() -> None:
    app, page, service = _app()
    assert service.cached_calls == 1
    assert service.upcoming_calls == 0
    assert service.fixture_calls == 0
    assert service.forecast_calls == 0
    assert service.list_calls == 0
    assert service.bootstrap_calls == 0
    assert service.prefetch_calls == []
    assert app.booting is True
    assert app.competitions[0].code == "PL"
    assert len(page.scheduled) == 1
    assert page.overlay == [] or page.overlay[0].visible is False


def test_filtered_competitions_respects_query_and_favorites_only() -> None:
    settings = _settings(favorite_leagues="SA,PL")
    app, _page, _service = _app(settings=settings)
    app.competitions = [
        Competition(id=2021, code="PL", name="Premier League"),
        Competition(id=2014, code="PD", name="La Liga"),
        Competition(id=2019, code="SA", name="Serie A"),
    ]

    app.league_query = "liga"
    assert [item.code for item in app._filtered_competitions()] == ["PD"]

    app.league_query = ""
    app.favorites_only = True
    assert [item.code for item in app._filtered_competitions()] == ["PL", "SA"]

    app.favorites_only = False
    assert [item.code for item in app._filtered_competitions()] == ["PL", "SA", "PD"]


def test_save_settings_accepts_dict(monkeypatch) -> None:
    written: dict[str, str] = {}

    def fake_write(key: str, value: str, path=None) -> None:
        written[key] = value

    new_settings = _settings(
        football_data_api_key="abc",
        favorite_leagues="PL,PD",
        compact_fixtures=True,
    )
    service = FakeMatchService()
    monkeypatch.setattr("football_prognoz.ui.app.write_env_value", fake_write)
    monkeypatch.setattr("football_prognoz.ui.app.load_settings", lambda: new_settings)
    monkeypatch.setattr("football_prognoz.ui.app.build_service", lambda _settings: service)

    app, page, _service = _app(service=service)
    app.booting = False
    app.section = "settings"
    app._save_settings(
        {
            "football_data_api_key": "abc",
            "openai_api_key": "",
            "openai_model": "gpt-4o-mini",
            "openai_base_url": "https://api.openai.com/v1",
            "favorite_leagues": "PL,PD",
            "favorite_teams": "57,64",
            "prefetch_wait_on_start": False,
            "show_ai_block": True,
            "compact_fixtures": True,
            "system_notifications": True,
        }
    )
    _drain_last(page)
    assert written["FOOTBALL_DATA_API_KEY"] == "abc"
    assert written["OPENAI_API_KEY"] == ""
    assert written["OPENAI_MODEL"] == "gpt-4o-mini"
    assert written["OPENAI_BASE_URL"] == "https://api.openai.com/v1"
    assert written["FAVORITE_LEAGUES"] == "PL,PD"
    assert written["FAVORITE_TEAMS"] == "57,64"
    assert written["PREFETCH_WAIT_ON_START"] == "false"
    assert written["SHOW_AI_BLOCK"] == "true"
    assert written["COMPACT_FIXTURES"] == "true"
    assert written["SYSTEM_NOTIFICATIONS"] == "true"
    assert app.status == "Настройки сохранены."
    assert app.settings is new_settings


def test_boot_prefetch_wait_schedules_prefetch_not_upcoming() -> None:
    app, page, service = _app(settings=_settings(prefetch_wait_on_start=True))
    assert service.upcoming_calls == 0
    assert service.prefetch_calls == []
    assert len(page.scheduled) == 1
    _drain_last(page)
    assert service.upcoming_calls == 0
    assert service.prefetch_calls == []
    assert len(page.scheduled) >= 2
    assert app.booting is True
    _drain_last(page)
    assert service.prefetch_calls == [item.code for item in service.competitions]
    assert service.upcoming_calls == 0
    assert app.booting is False


def test_clear_cache_drains_to_status() -> None:
    app, page, service = _app()
    app.booting = False
    app.section = "settings"
    app._clear_cache()
    _drain_last(page)
    assert service.clear_calls == 1
    assert app.status == "Кэш очищен."


def test_filtered_matches_keeps_finished_when_upcoming_only_false() -> None:
    app, _page, _service = _app()
    finished = Match(
        id=7,
        competition_code="PL",
        utc_date=datetime.now(UTC) - timedelta(days=2),
        status=MatchStatus.FINISHED,
        matchday=5,
        home_id=64,
        home_name="Liverpool",
        away_id=66,
        away_name="Man United",
        score=Score(2, 1),
    )
    live = _match()
    app.matches = [finished, live]
    app.upcoming_only = False
    assert [item.id for item in app._filtered_matches()] == [7, live.id]
    app.upcoming_only = True
    assert [item.id for item in app._filtered_matches()] == [live.id]


def test_load_fixtures_keeps_finished_matches() -> None:
    app, page, service = _app()
    app.booting = False
    app.league = service.competitions[0]
    app._load_fixtures()
    _drain_last(page)
    assert service.fixture_calls == 1
    assert service.upcoming_calls == 0
    assert any(item.status is MatchStatus.FINISHED for item in app.matches)
    app.upcoming_only = False
    assert any(item.status is MatchStatus.FINISHED for item in app._filtered_matches())


def test_open_match_forecasts_with_explain_false() -> None:
    app, page, service = _app()
    app.booting = False
    app.league = service.competitions[0]
    match = _match()
    app._open_match(match)
    assert service.forecast_calls == 0
    _drain_last(page)
    assert service.forecast_calls == 1
    assert service.forecast_explain == [False]
    assert service.explain_calls == 0
    assert app.forecast is not None
    assert app.forecast.match.id == match.id


def test_nav_event_data_opens_settings_during_boot() -> None:
    app, _page, _service = _app()
    assert app.booting is True
    app._on_nav(SimpleNamespace(data="3", control=SimpleNamespace(selected_index=0)))
    assert app.section == "settings"
    blob = " ".join(
        str(getattr(node, "value", "") or getattr(node, "label", "") or "")
        for node in _walk(app._pane.content)
    )
    assert "Настройки" in blob
    assert "Любимые лиги" in blob


def test_nav_falls_back_to_selected_index() -> None:
    app, _page, _service = _app()
    app.booting = False
    app._on_nav(SimpleNamespace(data=None, control=SimpleNamespace(selected_index=3)))
    assert app.section == "settings"


def test_fixture_query_paginates_filtered_matches() -> None:
    app, _page, _service = _app()
    now = datetime.now(UTC)
    app.matches = [
        Match(
            id=index,
            competition_code="PL",
            utc_date=now + timedelta(days=index),
            status=MatchStatus.SCHEDULED,
            matchday=index,
            home_id=index,
            home_name=f"Home {index}",
            away_id=100 + index,
            away_name=f"Away {index}",
            score=Score(None, None),
        )
        for index in range(1, 31)
    ]
    app.fixture_query = FixtureQuery(status=MatchStatusFilter.ALL, page_size=10, page=1)
    page = app._fixture_page()
    assert page.total == 30
    assert page.page == 1
    assert [item.id for item in page.items] == list(range(11, 21))
    assert [item.id for item in app._filtered_matches()] == list(range(11, 21))


def _walk(control: object):
    yield control
    content = getattr(control, "content", None)
    if content is not None:
        yield from _walk(content)
    controls = getattr(control, "controls", None)
    if controls:
        for child in controls:
            yield from _walk(child)
