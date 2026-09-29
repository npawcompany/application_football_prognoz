from __future__ import annotations

from datetime import UTC, datetime

import flet as ft

from football_prognoz.config import Settings
from football_prognoz.domain.match import Match, MatchStatus, Score
from football_prognoz.domain.prediction import (
    MatchFeatures,
    MatchForecast,
    Probabilities,
    Scoreline,
)
from football_prognoz.domain.team import Competition
from football_prognoz.services.filters import FixtureQuery, MatchStatusFilter, PageResult
from football_prognoz.ui.views.fixtures import fixtures_view
from football_prognoz.ui.views.leagues import leagues_view
from football_prognoz.ui.views.match_detail import match_detail_view
from football_prognoz.ui.views.settings import SettingsForm, settings_view


def _walk(control: object):
    yield control
    content = getattr(control, "content", None)
    if content is not None:
        yield from _walk(content)
    controls = getattr(control, "controls", None)
    if controls:
        for child in controls:
            yield from _walk(child)


def _texts(control: object) -> list[str]:
    found: list[str] = []
    for node in _walk(control):
        if isinstance(node, str):
            found.append(node)
            continue
        for attr in ("value", "text", "label", "hint_text", "content"):
            value = getattr(node, attr, None)
            if isinstance(value, str):
                found.append(value)
    return found


def _blob(control: object) -> str:
    return " ".join(_texts(control))


def _competition(code: str = "PL", name: str = "Premier League") -> Competition:
    return Competition(2021, code, name)


def _match() -> Match:
    return Match(
        id=1,
        competition_code="PL",
        utc_date=datetime(2026, 9, 26, 14, 0, tzinfo=UTC),
        status=MatchStatus.SCHEDULED,
        matchday=6,
        home_id=57,
        home_name="Arsenal",
        away_id=65,
        away_name="Man City",
        score=Score(None, None),
    )


def _forecast() -> MatchForecast:
    return MatchForecast(
        match=_match(),
        probabilities=Probabilities(0.41, 0.27, 0.32),
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


def _leagues(
    competitions: list[Competition] | None = None,
    **kwargs: object,
) -> ft.Control:
    params: dict[str, object] = {
        "loading": False,
        "error": None,
        "on_select": lambda _item: None,
        "on_refresh": lambda: None,
    }
    params.update(kwargs)
    return leagues_view(competitions or [_competition()], **params)  # type: ignore[arg-type]


def _fixtures(matches: list[Match] | None = None, **kwargs: object) -> ft.Control:
    params: dict[str, object] = {
        "loading": False,
        "error": None,
        "on_open": lambda _item: None,
        "on_back": lambda: None,
        "on_refresh": lambda: None,
    }
    params.update(kwargs)
    return fixtures_view("Premier League", matches or [_match()], **params)  # type: ignore[arg-type]


def test_leagues_view_shows_filter_bar_when_on_query() -> None:
    view = _leagues(on_query=lambda _q: None)
    fields = [node for node in _walk(view) if isinstance(node, ft.TextField)]
    assert fields
    assert fields[0].label == "Поиск лиги"
    assert "Поиск лиги" in _blob(view)


def test_leagues_view_hides_filter_bar_without_on_query() -> None:
    view = _leagues()
    fields = [node for node in _walk(view) if isinstance(node, ft.TextField)]
    assert fields == []
    assert "Поиск лиги" not in _blob(view)


def test_leagues_view_favorite_chips_only_when_has_favorites() -> None:
    without = _leagues(on_query=lambda _q: None, has_favorites=False)
    assert "Все лиги" not in _blob(without)
    assert "Любимые" not in _blob(without)

    clicks: list[bool] = []
    with_fav = _leagues(
        on_query=lambda _q: None,
        has_favorites=True,
        favorites_only=True,
        on_favorites_only=clicks.append,
    )
    blob = _blob(with_fav)
    assert "Все лиги" in blob
    assert "Любимые" in blob

    chips = [
        node
        for node in _walk(with_fav)
        if isinstance(node, ft.Container) and isinstance(node.content, ft.Text)
    ]
    all_chip = next(chip for chip in chips if chip.content.value == "Все лиги")
    fav_chip = next(chip for chip in chips if chip.content.value == "Любимые")
    all_chip.on_click(None)
    assert clicks == [False]
    fav_chip.on_click(None)
    assert clicks == [False, True]


def test_leagues_view_renders_given_list_without_filtering() -> None:
    competitions = [
        _competition("PL", "Premier League"),
        _competition("BL1", "Bundesliga"),
    ]
    view = _leagues(
        competitions,
        query="xyz-does-not-match",
        on_query=lambda _q: None,
    )
    blob = _blob(view)
    assert "Premier League" in blob
    assert "Bundesliga" in blob


def test_fixtures_view_shows_filter_panel_when_on_query() -> None:
    view = _fixtures(query=FixtureQuery(), on_query=lambda _q: None)
    fields = [node for node in _walk(view) if isinstance(node, ft.TextField)]
    labels = {field.label for field in fields}
    assert "Команда" in labels
    blob = _blob(view)
    assert "Предстоящие" in blob
    assert "Живые" in blob
    assert "Сбросить" in blob


def test_fixtures_view_hides_filter_panel_without_on_query() -> None:
    view = _fixtures()
    fields = [node for node in _walk(view) if isinstance(node, ft.TextField)]
    assert fields == []
    assert "Команда" not in _blob(view)


def test_fixtures_view_status_chips_call_on_query() -> None:
    updates: list[FixtureQuery] = []
    view = _fixtures(
        query=FixtureQuery(),
        on_query=updates.append,
    )
    chips = [
        node
        for node in _walk(view)
        if isinstance(node, ft.Container) and isinstance(node.content, ft.Text)
    ]
    live = next(chip for chip in chips if chip.content.value == "Живые")
    live.on_click(None)
    assert updates
    assert updates[0].status is MatchStatusFilter.LIVE
    assert updates[0].page == 0


def test_fixtures_view_renders_page_slice_and_pager() -> None:
    matches = [_match(), _match()]
    page = PageResult(items=matches[:1], total=40, page=0, page_size=25)
    view = _fixtures(
        matches,
        query=FixtureQuery(),
        page_result=page,
        on_query=lambda _q: None,
    )
    blob = _blob(view)
    assert "1–25 из 40" in blob or "1–1 из 40" in blob
    assert "Назад" in blob
    assert "Вперёд" in blob


def test_match_detail_hides_ai_block_when_disabled() -> None:
    hidden = match_detail_view(
        _forecast(),
        loading=False,
        error=None,
        on_back=lambda: None,
        show_ai_block=False,
    )
    blob = _blob(hidden)
    assert "AI-разбор" not in blob
    assert "AI не настроен" not in blob
    assert "Контекст матча" in blob
    assert "Исход матча" in blob


def test_match_detail_keeps_ai_copy_when_enabled() -> None:
    shown = match_detail_view(
        _forecast(),
        loading=False,
        error=None,
        on_back=lambda: None,
        show_ai_block=True,
    )
    blob = _blob(shown)
    assert "AI-разбор факторов" in blob
    assert "AI не настроен. Добавьте OLLAMA_API_KEY в Настройках" in blob


def test_settings_view_builds_from_settings_form() -> None:
    form = SettingsForm.from_settings(
        Settings(football_data_api_key="test-key", favorite_leagues="PL,PD")
    )
    view = settings_view(
        form,
        on_save=lambda _payload: None,
        on_test=lambda: None,
        on_clear_cache=lambda: None,
    )
    blob = _blob(view)
    assert "Любимые лиги" in blob
    assert "Любимые команды" in blob
    assert "Очистить кэш" in blob


def _detail(forecast: MatchForecast, **kwargs: object) -> str:
    return _blob(
        match_detail_view(forecast, loading=False, error=None, on_back=lambda: None, **kwargs)
    )


def test_match_detail_ai_loading_state_has_no_not_configured_banner() -> None:
    blob = _detail(_forecast(), ai_state="loading")
    assert "Готовим AI-разбор" in blob
    assert "AI не настроен" not in blob


def test_match_detail_ai_error_state_shows_message() -> None:
    from dataclasses import replace

    forecast = replace(_forecast(), explanation_error="Ollama отклонил запрос (401).")
    blob = _detail(forecast, ai_state="error")
    assert "Не удалось получить AI-разбор" in blob
    assert "401" in blob
    assert "AI не настроен" not in blob


def test_match_detail_renders_structured_analysis_and_sources() -> None:
    from dataclasses import replace

    from football_prognoz.domain.prediction import Explanation, Factor

    explanation = Explanation(
        text="Хозяева чуть сильнее.",
        model="deepseek-v4.1-flash",
        home_factors=(Factor("Форма WWDLW", "Поддерживает хозяев", "up"),),
        away_factors=(Factor("Elo ниже", "Минус для гостей", "down"),),
        verdict="Небольшой перевес хозяев.",
        confidence="medium",
        confidence_reason="Вероятности близки.",
    )
    forecast = replace(
        _forecast(), explanation=explanation, sources=("football-data.org", "API-Football")
    )
    blob = _detail(forecast, ai_state="ready")
    assert "Форма WWDLW" in blob
    assert "Небольшой перевес хозяев." in blob
    assert "Уверенность: средняя" in blob
    assert "Расчёт модели: 1 — 41%" in blob
    assert "Источники: football-data.org; API-Football" in blob
    assert "deepseek-v4.1-flash" in blob


def test_match_detail_player_status_card() -> None:
    from dataclasses import replace

    from football_prognoz.domain.player_status import (
        Absence,
        CardEvent,
        PlayerStatusReport,
        TeamStatus,
    )

    report = PlayerStatusReport(
        home=TeamStatus(
            "Arsenal",
            42,
            absences=(Absence(1, "B. Saka", "Missing Fixture", "Hamstring", "2026-10-10", True),),
            red_cards=(CardEvent(9, "2026-09-19", 81, 2, "W. Saliba", "Red Card"),),
        ),
        away=TeamStatus("Man City", 50),
        notes=("Тестовая заметка",),
    )
    blob = _detail(replace(_forecast(), player_status=report))
    assert "Состав и доступность" in blob
    assert "B. Saka (Hamstring, не сыграет, ключевой, до 2026-10-10)" in blob
    assert "W. Saliba" in blob
    assert "Тестовая заметка" in blob


def test_match_detail_without_player_status_has_no_card() -> None:
    assert "Состав и доступность" not in _detail(_forecast())


def test_settings_view_has_ollama_and_api_football_fields() -> None:
    form = SettingsForm.from_settings(Settings(football_data_api_key="k"))
    view = settings_view(
        form, on_save=lambda _p: None, on_test=lambda: None, on_clear_cache=lambda: None
    )
    blob = _blob(view)
    for label in ("OLLAMA_API_KEY", "OLLAMA_HOST", "OLLAMA_MODEL", "API_FOOTBALL_KEY"):
        assert label in blob
    assert "OPENAI" not in blob


def test_match_detail_news_card() -> None:
    from dataclasses import replace
    from datetime import UTC, datetime

    from football_prognoz.domain.news import NewsItem, NewsReport, TeamNews

    report = NewsReport(
        home=TeamNews(
            "Arsenal",
            (
                NewsItem(
                    "Saka doubt for City clash",
                    "BBC Sport",
                    "https://x",
                    datetime(2026, 9, 24, tzinfo=UTC),
                    "injury",
                ),
            ),
        ),
        away=TeamNews("Man City"),
        provider="rss",
    )
    blob = _detail(replace(_forecast(), news=report))
    assert "Новости команд" in blob
    assert "24.09 · травма · Saka doubt for City clash (BBC Sport)" in blob
    assert "свежих заголовков нет" in blob
    assert "не влияют на вероятности 1X2" in blob


def test_training_panel_idle_and_running() -> None:
    from football_prognoz.ui.components.training_panel import TrainingState, training_panel

    idle = _blob(
        training_panel(
            TrainingState(result="Сбор завершён: новых 3."),
            on_collect=lambda: None,
            on_cancel=lambda: None,
        )
    )
    assert "Собрать данные для обучения" in idle
    assert "Отменить" not in idle
    assert "Сбор завершён: новых 3." in idle
    running = _blob(
        training_panel(
            TrainingState(running=True, done=3, total=10, message="Alpha — Beta", codes=("PL",)),
            on_collect=lambda: None,
            on_cancel=lambda: None,
        )
    )
    assert "Отменить" in running
    assert "3 / 10 · Alpha — Beta" in running
    assert "Лиги: PL" in running
    assert TrainingState(running=True, done=3, total=10).fraction == 0.3


def test_settings_view_embeds_training_panel() -> None:
    import flet as ft

    form = SettingsForm.from_settings(Settings(football_data_api_key="k"))
    view = settings_view(
        form,
        on_save=lambda _p: None,
        on_test=lambda: None,
        on_clear_cache=lambda: None,
        training=ft.Text("TRAINING-PANEL"),
    )
    assert "TRAINING-PANEL" in _blob(view)


def test_match_detail_history_hint_shown_only_when_present() -> None:
    from dataclasses import replace

    from football_prognoz.domain.history import HistoricalHint

    assert "Исторически такой исход" not in _detail(_forecast())
    hint = HistoricalHint("1", 0.41, "40–50%", 0.47, 58)
    blob = _detail(replace(_forecast(), history_hint=hint))
    assert "Исторически такой исход сбывался в 47% случаев" in blob
    assert "выборка: 58 прогнозов с вероятностью 40–50%" in blob


def test_calibration_lines_format() -> None:
    from football_prognoz.domain.history import CalibrationBucket, CalibrationReport
    from football_prognoz.ui.components.training_panel import calibration_lines

    report = CalibrationReport(
        "elo-poisson-v1",
        50,
        3,
        0.52,
        0.601,
        1.002,
        {"1": (30, 0.6), "X": (5, 0.2), "2": (15, 0.47)},
        (CalibrationBucket(0.4, 0.5, 60, 0.45, 0.43),),
    )
    lines = calibration_lines(report)
    assert lines[0].startswith("Оценено прогнозов до матча: 50")
    assert "Точность исхода: 52% · Brier: 0.601 · log-loss: 1.002" in lines[1]
    assert "победа хозяев — 60% из 30" in lines[2]
    assert "Вероятность 40–50%: в среднем 45%, сбылось 43% (n=60)" in lines[3]
