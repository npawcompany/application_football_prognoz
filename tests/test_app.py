from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
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
from football_prognoz.services.leagues import league_infos
from football_prognoz.services.matches import Cancelled, KeyCheck
from football_prognoz.services.startup import GateState
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
        self.check_calls = 0
        self.check_result = KeyCheck(ok=True, rejected=False, message="", leagues=3)
        self.key_rejected = False
        self.day_calls: list[tuple[date, object]] = []
        self.day_result: list[Match] = []
        self.cached_day: list[Match] = []
        self.forecast_details: list[bool] = []
        self.enrich_cancels: list = []
        self.enrich_explain: list[bool] = []

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

    def forecast(self, match: Match, *, explain: bool = True, details: bool = True):
        self.forecast_calls += 1
        self.forecast_explain.append(explain)
        self.forecast_details.append(details)
        return _forecast_for(match)

    def league_infos(self):
        return league_infos(self.competitions, {}, (), today=date.today())

    def day_matches(self, day, *, codes=None, tz=None, force=False, now=None):
        self.day_calls.append((day, codes))
        return list(self.day_result)

    def cached_day_matches(self, day, *, codes=None, tz=None):
        return list(self.cached_day)

    def cached_league_matches(self, code):
        return []

    def teams_by_league(self):
        return {"PL": [Team(id=57, name="Arsenal")]}

    def check_key(self):
        self.check_calls += 1
        return self.check_result

    def refresh_league_counts(self, codes, *, cancel=None, progress=None):
        return self.league_infos()

    llm_enabled = False
    player_status_enabled = False
    closed = False
    enrich_result: MatchForecast | None = None
    enrich_error: Exception | None = None

    def explain_forecast(self, forecast: MatchForecast) -> MatchForecast:
        self.explain_calls += 1
        return forecast

    def enrich(self, forecast, *, explain=True, cancel=None, on_step=None):
        self.explain_calls += 1
        self.enrich_cancels.append(cancel)
        self.enrich_explain.append(explain)
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        if on_step is not None:
            on_step(forecast)
        if self.enrich_error is not None:
            raise self.enrich_error
        return self.enrich_result or forecast

    def close(self) -> None:
        self.closed = True

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
    splash: float = 0.0,
    clock=None,
) -> tuple[FootballApp, FakePage, FakeMatchService]:
    page = FakePage()
    settings = settings or _settings()
    service = service or FakeMatchService()
    extra = {"clock": clock} if clock is not None else {}
    app = FootballApp(page, service, settings, splash_min_seconds=splash, **extra)  # type: ignore[arg-type]
    return app, page, service


def _booted(**kwargs):
    """App after the splash: boot task drained (splash minimum 0 in tests)."""
    app, page, service = _app(**kwargs)
    _drain_first(page)
    return app, page, service


def _drain_first(page: FakePage) -> None:
    fn, args, kwargs, _handle = page.scheduled[0]
    asyncio.run(fn(*args, **kwargs))


def _drain_named(page: FakePage, index: int) -> None:
    fn, args, kwargs, _handle = page.scheduled[index]
    asyncio.run(fn(*args, **kwargs))


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


def test_clear_cache_drains_to_status() -> None:
    app, page, service = _app()
    app.booting = False
    app.section = "settings"
    app._clear_cache()
    _drain_last(page)
    assert service.clear_calls == 1
    assert app.status == "Кэш очищен."


def test_open_match_forecasts_with_explain_false() -> None:
    app, page, service = _booted()
    match = _match()
    app._open_match(match)
    assert service.forecast_calls == 0
    _drain_last(page)
    assert service.forecast_calls == 1
    assert service.forecast_explain == [False]
    assert service.forecast_details == [False]  # no HTTP on the click path
    assert page.overlay == [] or page.overlay[0].visible is False  # no blocking preloader
    assert app.forecast is not None
    assert app.forecast.match.id == match.id


def test_nav_falls_back_to_selected_index() -> None:
    app, _page, _service = _app()
    app.booting = False
    app._on_nav(SimpleNamespace(data=None, control=SimpleNamespace(selected_index=3)))
    assert app.section == "settings"


def _walk(control: object):
    yield control
    content = getattr(control, "content", None)
    if content is not None:
        yield from _walk(content)
    controls = getattr(control, "controls", None)
    if controls:
        for child in controls:
            yield from _walk(child)


def _open_and_forecast(app, page, match=None):
    app.booting = False
    app.league = Competition(id=2021, code="PL", name="Premier League")
    app._open_match(match or _match())
    _drain_last(page)


def test_ai_loading_then_ready_state() -> None:
    from football_prognoz.domain.prediction import Explanation

    service = FakeMatchService()
    service.llm_enabled = True
    app, page, _ = _app(service=service)
    before = len(page.scheduled)
    _open_and_forecast(app, page)
    assert app.ai_state == "loading"
    assert len(page.scheduled) == before + 2  # forecast + enrichment
    service.enrich_result = replace(
        _forecast_for(_match()), explanation=Explanation("Разбор.", "deepseek-v4.1-flash")
    )
    _drain_last(page)
    assert app.ai_state == "ready"
    assert app.forecast.explanation is not None


def test_ai_error_state_when_llm_fails() -> None:
    service = FakeMatchService()
    service.llm_enabled = True
    service.enrich_result = replace(
        _forecast_for(_match()), explanation_error="Ollama отклонил запрос (401)."
    )
    app, page, _ = _app(service=service)
    _open_and_forecast(app, page)
    _drain_last(page)
    assert app.ai_state == "error"
    assert "401" in (app.ai_error or "")


def test_ai_error_state_on_unexpected_exception() -> None:
    service = FakeMatchService()
    service.llm_enabled = True
    service.enrich_error = RuntimeError("boom")
    app, page, _ = _app(service=service)
    _open_and_forecast(app, page)
    _drain_last(page)
    assert app.ai_state == "error"
    assert app.ai_error == "boom"


def test_stale_enrichment_is_ignored() -> None:
    service = FakeMatchService()
    service.player_status_enabled = True
    app, page, _ = _app(service=service)
    _open_and_forecast(app, page)
    other = replace(_match(), id=99)
    app.selected_match_id = other.id
    app.forecast = _forecast_for(other)
    _drain_last(page)
    assert app.forecast.match.id == 99


class _TrainingService(FakeMatchService):
    def __init__(self) -> None:
        super().__init__()
        self.collect_calls: list[list[str]] = []
        self.cancel_seen = None

    def collect_training_data(self, codes, *, progress=None, cancel=None):
        from football_prognoz.domain.history import CollectionResult

        self.collect_calls.append(list(codes))
        self.cancel_seen = cancel
        if progress is not None:
            progress(1, 2, "Alpha — Beta")
            progress(2, 2, "Gamma — Delta")
        return CollectionResult(inserted=2, total=2, cancelled=bool(cancel and cancel.is_set()))

    def calibration_report(self):
        from football_prognoz.domain.history import CalibrationReport

        return CalibrationReport("elo-poisson-v1", 0, 0, None, None, None, {}, ())

    def export_history(self, directory=None, *, records_path=None):
        if records_path is not None:
            return records_path, records_path.with_name("c.csv"), 7
        return directory / "h.csv", directory / "c.csv", 7


def _settings_app(service, **settings_kwargs):
    app, page, _ = _app(service=service, settings=_settings(**settings_kwargs))
    app.booting = False
    app.section = "settings"
    return app, page


def test_training_requires_a_league() -> None:
    service = _TrainingService()
    app, page = _settings_app(service)
    app.league = None
    before = len(page.scheduled)
    app._start_training()
    assert "Выберите лигу" in (app.training.error or "")
    assert len(page.scheduled) == before
    assert service.collect_calls == []


def test_training_runs_in_background_with_progress_and_result() -> None:
    service = _TrainingService()
    app, page = _settings_app(service, favorite_leagues="PL,PD")
    before = len(page.scheduled)
    app._start_training()
    assert app.training.running is True
    assert app.training.codes == ("PL", "PD")
    assert len(page.scheduled) == before + 1  # detached job, UI not blocked
    job = page.scheduled[-1]
    asyncio.run(job[0](*job[1], **job[2]))
    assert service.collect_calls == [["PL", "PD"]]
    assert app.training.running is False
    assert "новых 2" in (app.training.result or "")
    # progress updates were posted to the UI loop after the job
    assert len(page.scheduled) >= before + 3


def test_training_second_click_is_ignored_while_running() -> None:
    service = _TrainingService()
    app, page = _settings_app(service, favorite_leagues="PL")
    app._start_training()
    count = len(page.scheduled)
    app._start_training()
    assert len(page.scheduled) == count


def test_training_cancel_sets_event() -> None:
    service = _TrainingService()
    app, page = _settings_app(service, favorite_leagues="PL")
    app._start_training()
    app._cancel_training()
    assert app.training.cancelling is True
    job = page.scheduled[-1]
    asyncio.run(job[0](*job[1], **job[2]))
    assert service.cancel_seen is not None and service.cancel_seen.is_set()
    assert "остановлен" in (app.training.result or "")


def test_training_failure_is_shown() -> None:
    class _Broken(_TrainingService):
        def collect_training_data(self, codes, *, progress=None, cancel=None):
            raise RuntimeError("disk full")

    app, page = _settings_app(_Broken(), favorite_leagues="PL")
    app._start_training()
    job = page.scheduled[-1]
    asyncio.run(job[0](*job[1], **job[2]))
    assert app.training.running is False
    assert "disk full" in (app.training.error or "")


def test_training_done_shows_quality_stats() -> None:
    service = _TrainingService()
    app, page = _settings_app(service, favorite_leagues="PL")
    app._start_training()
    job = page.scheduled[-1]
    asyncio.run(job[0](*job[1], **job[2]))
    assert any("пока нет завершённых матчей" in line for line in app.training.stats)


def test_export_history_writes_csv_in_background() -> None:
    service = _TrainingService()
    app, page = _settings_app(service)
    before = len(page.scheduled)
    app._export_history()
    assert len(page.scheduled) == before + 1
    job = page.scheduled[-1]
    asyncio.run(job[0](*job[1], **job[2]))
    assert "h.csv (7 строк)" in (app.training.export_path or "")
    assert "c.csv" in (app.training.export_path or "")


# --- splash timing --------------------------------------------------------------------


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


async def _no_sleep(_delay: float) -> None:
    return None


def test_splash_stays_three_seconds_when_loading_is_fast(monkeypatch) -> None:
    monkeypatch.setattr("football_prognoz.ui.app.asyncio.sleep", _no_sleep)
    clock = _Clock()
    app, page, service = _app(splash=3.0, clock=clock)
    assert app.booting is True and app._pane_kind == "splash"
    clock.now += 0.5  # loading took half a second
    _drain_first(page)
    assert service.bootstrap_calls == 1  # loading ran in the background task
    assert app.booting is True  # but the splash is kept
    assert abs(app.splash.remaining() - 2.5) < 1e-9
    delayed = page.scheduled[-1]
    asyncio.run(delayed[0](*delayed[1], **delayed[2]))
    assert app.booting is False
    assert app.section == "fixtures"


def test_splash_waits_for_slow_loading(monkeypatch) -> None:
    clock = _Clock()
    app, page, _service = _app(splash=3.0, clock=clock)
    clock.now += 7.0  # still loading after 7 s: splash is still up
    assert app.booting is True
    before = len(page.scheduled)
    _drain_first(page)
    assert app.booting is False  # hidden right when loading finished
    assert len(page.scheduled) > before  # the day calendar load started


def test_nav_is_ignored_while_splash_is_shown() -> None:
    app, _page, _service = _app()
    app._on_nav(SimpleNamespace(data="3", control=SimpleNamespace(selected_index=0)))
    assert app.booting is True
    assert app._pane_kind == "splash"


def test_prefetch_on_start_runs_inside_the_boot_task() -> None:
    app, page, service = _app(settings=_settings(prefetch_wait_on_start=True))
    assert service.prefetch_calls == []
    _drain_first(page)
    assert service.prefetch_calls == [item.code for item in service.competitions]
    assert app.booting is False


# --- required-keys gate ---------------------------------------------------------------


def test_missing_key_opens_settings_and_blocks_other_sections() -> None:
    app, page, service = _booted(settings=_settings(football_data_api_key=""))
    assert service.bootstrap_calls == 0  # no network without the key
    assert app.gate.state is GateState.MISSING
    assert app.section == "settings"
    blob = " ".join(str(getattr(n, "value", "") or "") for n in _walk(app._pane.content))
    assert "обязательный ключ" in blob
    for index in (0, 1, 2):
        app._on_nav(SimpleNamespace(data=str(index), control=None))
        assert app.section == "settings"
    assert service.day_calls == []


def test_rejected_key_also_locks_the_app() -> None:
    service = FakeMatchService()
    service.key_rejected = True
    app, _page, _ = _booted(service=service)
    assert app.gate.state is GateState.REJECTED
    assert app.section == "settings"
    app._goto("leagues")
    assert app.section == "settings"


def _save_key(monkeypatch, app, page, new_service, key="new"):
    monkeypatch.setattr("football_prognoz.ui.app.write_env_value", lambda *a, **k: None)
    monkeypatch.setattr(
        "football_prognoz.ui.app.load_settings", lambda: _settings(football_data_api_key=key)
    )
    monkeypatch.setattr("football_prognoz.ui.app.build_service", lambda _s: new_service)
    app._save_settings({"football_data_api_key": key})
    _drain_last(page)  # write .env + rebuild service


def test_saving_a_valid_key_unlocks_without_restart(monkeypatch) -> None:
    old_service = FakeMatchService()
    new_service = FakeMatchService()
    app, page, _ = _booted(service=old_service, settings=_settings(football_data_api_key=""))
    _save_key(monkeypatch, app, page, new_service)
    assert old_service.closed is True
    assert app.service is new_service
    assert app.gate.state is GateState.CHECKING and app.gate.locked
    app._goto("fixtures")
    assert app.section == "settings"  # still locked while the key is checked
    _drain_last(page)  # key check
    assert new_service.check_calls == 1
    assert app.gate.locked is False
    assert "Ключ принят" in (app.status or "")
    _drain_last(page)  # data the locked app skipped
    assert new_service.bootstrap_calls == 1
    app._goto("leagues")
    assert app.section == "leagues"


def test_saving_a_rejected_key_keeps_the_gate_closed(monkeypatch) -> None:
    new_service = FakeMatchService()
    new_service.check_result = KeyCheck(ok=False, rejected=True, message="Ключ не принят (401)")
    app, page, _ = _booted(settings=_settings(football_data_api_key=""))
    _save_key(monkeypatch, app, page, new_service, key="bad")
    _drain_last(page)
    assert app.gate.state is GateState.REJECTED
    assert "401" in app.gate.notice()
    app._goto("fixtures")
    assert app.section == "settings"


def test_key_check_without_network_does_not_lock_the_user_out(monkeypatch) -> None:
    new_service = FakeMatchService()
    new_service.check_result = KeyCheck(ok=False, rejected=False, message="Нет связи")
    app, page, _ = _booted(settings=_settings(football_data_api_key=""))
    _save_key(monkeypatch, app, page, new_service)
    _drain_last(page)
    assert app.gate.locked is False
    assert "проверить его сейчас нельзя" in (app.status or "")


def test_save_settings_writes_every_key(monkeypatch) -> None:
    written: dict[str, str] = {}
    monkeypatch.setattr(
        "football_prognoz.ui.app.write_env_value",
        lambda key, value, path=None: written.update({key: value}),
    )
    new_settings = _settings(football_data_api_key="test-key", favorite_leagues="PL,PD")
    monkeypatch.setattr("football_prognoz.ui.app.load_settings", lambda: new_settings)
    service = FakeMatchService()
    monkeypatch.setattr("football_prognoz.ui.app.build_service", lambda _settings: service)
    app, page, _ = _booted(service=service)
    app._goto("settings")
    app._save_settings(
        {
            "football_data_api_key": "test-key",
            "ollama_api_key": "ol-key",
            "ollama_host": "https://ollama.com",
            "ollama_model": "deepseek-v4.1-flash",
            "ollama_fallback_model": "gpt-oss:120b",
            "api_football_key": "",
            "gnews_api_key": "gn-key",
            "news_rss_enabled": False,
            "favorite_leagues": "PL,PD",
            "favorite_teams": "57,64",
            "prefetch_wait_on_start": False,
            "show_ai_block": True,
            "compact_fixtures": True,
            "system_notifications": True,
        }
    )
    _drain_last(page)
    assert written["FOOTBALL_DATA_API_KEY"] == "test-key"
    assert written["OLLAMA_API_KEY"] == "ol-key"
    assert written["GNEWS_API_KEY"] == "gn-key"
    assert written["NEWS_RSS_ENABLED"] == "false"
    assert written["FAVORITE_LEAGUES"] == "PL,PD"
    assert written["FAVORITE_TEAMS"] == "57,64"
    assert written["COMPACT_FIXTURES"] == "true"
    assert written["SYSTEM_NOTIFICATIONS"] == "true"
    assert not any(key.startswith("OPENAI") for key in written)
    assert app.settings is new_settings
    assert app.status == "Настройки сохранены и применены."  # same key: no re-check
    assert service.check_calls == 0


# --- calendar -------------------------------------------------------------------------


def _day_match(match_id: int, when: datetime) -> Match:
    return replace(_match(), id=match_id, utc_date=when)


def test_calendar_paints_cache_first_then_refreshes_in_background() -> None:
    service = FakeMatchService()
    now = datetime.now(UTC)
    service.cached_day = [_day_match(1, now)]
    service.day_result = [_day_match(1, now), _day_match(2, now)]
    app, page, _ = _booted(service=service)
    assert [m.id for m in app.matches] == [1]  # instant, from SQLite
    assert app.calendar.loading is True
    _drain_last(page)
    assert [m.id for m in app.matches] == [1, 2]
    assert app.calendar.loading is False
    assert service.day_calls[-1][1] is None  # all leagues


def test_calendar_ignores_a_stale_day_result() -> None:
    service = FakeMatchService()
    app, page, _ = _booted(service=service)
    service.day_result = [_day_match(5, datetime.now(UTC))]
    app.calendar.shift_day(1)
    first = len(page.scheduled) - 1
    service.day_result = [_day_match(6, datetime.now(UTC))]
    app.calendar.shift_day(1)
    _drain_last(page)
    _drain_named(page, first)  # the older request finishes last
    assert [m.id for m in app.matches] == [6]


def test_selecting_a_league_filters_the_calendar() -> None:
    service = FakeMatchService()
    app, page, _ = _booted(service=service)
    app._goto("leagues")
    app._select_league(service.competitions[0])
    assert app.league.code == "PL"
    assert app.calendar.league is not None
    assert app.section == "leagues"  # wide window: calendar opens on the right
    _drain_named(page, len(page.scheduled) - 2)  # day refresh (the last job is the season)
    assert service.day_calls[-1][1] == ["PL"]
    _drain_last(page)
    assert service.fixture_calls == 1  # season calendar for the match-day jumps
    app._clear_league()
    assert app.calendar.league is None
    _drain_last(page)
    assert service.day_calls[-1][1] is None  # back to every league


# --- background AI --------------------------------------------------------------------


def test_switching_match_cancels_the_running_analysis() -> None:
    service = FakeMatchService()
    service.llm_enabled = True
    app, page, _ = _booted(service=service)
    first = _match()
    app._open_match(first)
    _drain_last(page)  # forecast A -> enrichment A scheduled
    enrich_a = page.scheduled[-1]
    job_a_cancel = app._ai_job.cancel
    assert app.ai_state == "loading"
    second = replace(_match(), id=77, home_name="Chelsea")
    app._open_match(second)
    assert job_a_cancel is not None and job_a_cancel.is_set()
    asyncio.run(enrich_a[0](*enrich_a[1], **enrich_a[2]))
    assert app.forecast is None  # A's late result did not replace B's screen
    _drain_last(page)  # forecast B
    assert app.forecast.match.id == 77


def test_leaving_the_forecast_screen_stops_analysis_and_resumes_it() -> None:
    service = FakeMatchService()
    service.llm_enabled = True
    app, page, _ = _booted(service=service)
    app._open_match(_match())
    _drain_last(page)
    cancel = app._ai_job.cancel
    app._goto("leagues")
    assert cancel is not None and cancel.is_set()
    assert app.ai_state is None
    before = len(page.scheduled)
    app._goto("fixtures")
    assert app.ai_state == "loading"
    assert len(page.scheduled) > before  # analysis restarted


def test_enrichment_runs_for_details_even_without_llm() -> None:
    service = FakeMatchService()
    app, page, _ = _booted(service=service)
    app._open_match(_match())
    _drain_last(page)
    assert app.ai_state == "not_configured"
    _drain_last(page)
    assert service.enrich_explain == [False]


class _FakePicker:
    def __init__(self, answer):
        self.answer = answer
        self.calls: list[dict] = []

    async def save_file(self, **kwargs):
        self.calls.append(kwargs)
        return self.answer


def test_export_asks_where_to_save_and_writes_there(tmp_path, monkeypatch) -> None:
    service = _TrainingService()
    app, page = _settings_app(service)
    picker = _FakePicker(str(tmp_path / "mine.csv"))
    monkeypatch.setattr(app, "_file_picker", lambda: picker)
    app._export_history()
    _drain_last(page)  # the dialog
    assert picker.calls[0]["allowed_extensions"] == ["csv"]
    assert picker.calls[0]["initial_directory"].endswith("exports")
    _drain_last(page)  # the export job
    assert str(tmp_path / "mine.csv") in (app.training.export_path or "")


def test_export_cancelled_in_the_dialog_writes_nothing(monkeypatch) -> None:
    service = _TrainingService()
    app, page = _settings_app(service)
    monkeypatch.setattr(app, "_file_picker", lambda: _FakePicker(None))
    app._export_history()
    before = len(page.scheduled)
    _drain_last(page)
    assert len(page.scheduled) == before  # no export job
    assert app.training.result == "Экспорт отменён."
    assert app.training.export_path is None
