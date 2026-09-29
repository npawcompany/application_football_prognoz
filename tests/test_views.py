from __future__ import annotations

from datetime import UTC, date, datetime

import flet as ft
import ui_check

from football_prognoz.config import Settings
from football_prognoz.domain.match import Match, MatchStatus, Score
from football_prognoz.domain.prediction import (
    MatchFeatures,
    MatchForecast,
    Probabilities,
    Scoreline,
)
from football_prognoz.domain.team import Competition
from football_prognoz.services.calendar import GroupMode
from football_prognoz.services.leagues import LeagueGrouping, LeagueInfo, LeagueType, league_infos
from football_prognoz.ui.views.calendar import CalendarPanel
from football_prognoz.ui.views.leagues import LeaguesPanel
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


def _infos(today: date = date(2026, 9, 29)) -> list[LeagueInfo]:
    comps = [
        Competition(2021, "PL", "Premier League", type="LEAGUE", area_name="England"),
        Competition(2002, "BL1", "Bundesliga", type="LEAGUE", area_name="Germany"),
        Competition(2001, "CL", "UEFA Champions League", type="CUP", area_name="Europe"),
        Competition(2018, "EC", "European Championship", type="CUP", area_name="Europe"),
    ]
    return league_infos(
        comps, {"PL": 12, "BL1": 9, "CL": 4}, ["PL", "BL1", "CL", "EC"], today=today
    )


def _league_panel(**kwargs: object) -> LeaguesPanel:
    selected: list[Competition] = []
    panel = LeaguesPanel(on_select=selected.append, on_refresh=lambda: None)
    panel.set_data(_infos(), **kwargs)  # type: ignore[arg-type]
    panel.selected = selected  # type: ignore[attr-defined]
    return panel


def test_leagues_panel_filters_by_text_area_type_and_activity() -> None:
    panel = _league_panel()
    blob = _blob(panel.control)
    assert "Показано 4 из 4" in blob
    assert "нет матчей в ближайшие 6 месяцев" in blob  # EC greyed with a note
    panel.update_filter(query="bundes")
    assert "Показано 1 из 4" in _blob(panel.control)
    panel.update_filter(query="", area="Europe")
    assert [i.code for _t, items in panel.visible_groups() for i in items] == ["CL", "EC"]
    panel.update_filter(area="", league_type=LeagueType.CUP, active_only=True)
    assert [i.code for _t, items in panel.visible_groups() for i in items] == ["CL"]
    panel.update_filter(league_type=LeagueType.ALL, active_only=False, query="zzz")
    assert "Под фильтр не подходит ни одна лига." in _blob(panel.control)


def test_leagues_panel_groups_by_area_and_type_and_greys_idle_leagues() -> None:
    panel = _league_panel(favorite_codes=["BL1"])
    panel.set_grouping(LeagueGrouping.TYPE)
    blob = _blob(panel.control)
    assert "Кубок · 2" in blob and "Лига · 2" in blob
    panel.set_grouping(LeagueGrouping.AREA)
    titles = [title for title, _items in panel.visible_groups()]
    assert titles == ["England", "Europe", "Germany"]
    dimmed = [
        node
        for node in _walk(panel.control)
        if isinstance(node, ft.Container) and getattr(node, "opacity", 1.0) < 1.0
    ]
    assert len(dimmed) == 1  # only EC
    assert "★ Любимые" in _blob(panel.control)
    assert ui_check.layout_problems(panel.control) == []


def test_leagues_panel_area_dropdown_lists_known_areas() -> None:
    panel = _league_panel()
    keys = [option.key for option in panel._area.options]
    assert keys[1:] == ["England", "Europe", "Germany"]


def _day_match(mid: int, code: str, hour: int, home: str, away: str, home_id: int) -> Match:
    return Match(
        id=mid,
        competition_code=code,
        utc_date=datetime(2026, 10, 3, hour, 0, tzinfo=UTC),
        status=MatchStatus.SCHEDULED,
        matchday=7,
        home_id=home_id,
        home_name=home,
        away_id=home_id + 1000,
        away_name=away,
        score=Score(None, None),
    )


def _calendar(**callbacks: object) -> CalendarPanel:
    params: dict[str, object] = {
        "on_day": lambda _d: None,
        "on_open": lambda _m: None,
        "on_refresh": lambda: None,
        "on_clear_league": lambda: None,
        "on_jump": lambda _s: None,
        "today": lambda: date(2026, 10, 3),
    }
    params.update(callbacks)
    return CalendarPanel(**params)  # type: ignore[arg-type]


def test_calendar_panel_groups_day_by_league_and_team() -> None:
    panel = _calendar()
    panel.competitions = {
        "PL": Competition(2021, "PL", "Premier League"),
        "CL": Competition(2001, "CL", "UEFA Champions League"),
    }
    panel.favorite_team_ids = (57,)
    panel.set_data(
        [
            _day_match(1, "PL", 12, "Arsenal", "Chelsea", 57),
            _day_match(2, "CL", 19, "Real Madrid", "Inter", 86),
        ]
    )
    blob = _blob(panel.control)
    assert "Сегодня, 3 октября" in blob
    assert "Любимые команды" in blob
    assert "Premier League" in blob and "UEFA Champions League" in blob
    panel.set_mode(GroupMode.TEAM)
    assert "Real Madrid" in [g.title for g in panel.groups()]
    panel.set_team_query("inter")
    assert [m.id for g in panel.groups() for m in g.matches] == [2]
    assert ui_check.layout_problems(panel.control) == []


def test_calendar_panel_day_paging_and_league_jumps() -> None:
    days: list[date] = []
    jumps: list[int] = []
    cleared: list[bool] = []
    panel = _calendar(
        on_day=days.append, on_jump=jumps.append, on_clear_league=lambda: cleared.append(True)
    )
    panel.shift_day(1)
    panel.go_to(date(2026, 10, 1))
    assert days == [date(2026, 10, 4), date(2026, 10, 1)]
    assert "В этот день матчей нет." in _blob(panel.control)
    panel.set_league(
        Competition(2021, "PL", "Premier League"), [date(2026, 9, 27), date(2026, 10, 5)]
    )
    blob = _blob(panel.control)
    assert "След. игровой день →" in blob and "← Пред. игровой день" in blob
    buttons = {
        node.content: node
        for node in _walk(panel.control)
        if isinstance(node, ft.TextButton) and isinstance(node.content, str)
    }
    buttons["След. игровой день →"].on_click(None)
    assert jumps == [1]


def test_calendar_panel_shows_loading_and_error_inline() -> None:
    panel = _calendar()
    panel.set_data([], loading=True)
    assert panel._spinner_box.visible is True
    assert "Загружаем матчи дня…" in _blob(panel.control)
    panel.set_data([], loading=False, error="Нет связи с football-data.org")
    assert panel._spinner_box.visible is False
    assert "Нет связи с football-data.org" in _blob(panel.control)


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
    assert "Идёт анализ…" in blob
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


def test_settings_favourite_leagues_combobox_greys_idle_leagues_and_groups_teams() -> None:
    from football_prognoz.domain.team import Team
    from football_prognoz.ui.views.settings import HEADER_PREFIX

    infos = _infos()
    pl, cl = infos[0].competition, infos[2].competition
    form = SettingsForm.from_settings(
        Settings(football_data_api_key="k", favorite_leagues="PL", favorite_teams="57"),
        league_infos=infos,
        teams_by_league=[
            (pl, [Team(57, "Arsenal"), Team(61, "Chelsea")]),
            (cl, [Team(57, "Arsenal"), Team(86, "Real Madrid")]),
        ],
    )
    saved: list[dict] = []
    view = settings_view(
        form,
        on_save=saved.append,
        on_test=lambda: None,
        on_clear_cache=lambda: None,
        on_refresh_counts=lambda: None,
    )
    dropdowns = [node for node in _walk(view) if isinstance(node, ft.Dropdown)]
    leagues, teams = dropdowns[0], dropdowns[1]
    by_key = {option.key: option for option in leagues.options}
    assert set(by_key) == {"PL", "BL1", "CL", "EC"}
    assert by_key["EC"].disabled is True and by_key["PL"].disabled is False
    team_keys = [option.key for option in teams.options]
    assert team_keys == [f"{HEADER_PREFIX}PL", "57", "61"]  # only the chosen league
    assert teams.options[0].disabled is True  # league header
    assert "Обновить счётчики матчей" in _blob(view)
    leagues.value = "EC"
    leagues.on_select(None)  # idle league cannot be added
    leagues.value = "CL"
    leagues.on_select(None)
    team_keys = [option.key for option in teams.options]
    assert f"{HEADER_PREFIX}CL" in team_keys and "86" in team_keys
    assert team_keys.count("57") == 1  # a club in two leagues is listed once
    save = next(node for node in _walk(view) if isinstance(node, ft.FilledButton))
    save.on_click(None)
    assert saved[0]["favorite_leagues"] == "PL,CL"
    assert saved[0]["favorite_teams"] == "57"


def test_settings_view_shows_gate_notice() -> None:
    form = SettingsForm.from_settings(Settings(), gate_notice="Чтобы начать, укажите ключ")
    view = settings_view(
        form, on_save=lambda _p: None, on_test=lambda: None, on_clear_cache=lambda: None
    )
    assert "Чтобы начать, укажите ключ" in _blob(view)
