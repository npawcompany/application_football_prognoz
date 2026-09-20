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
            h2h_summary="Нет очных встреч в кэше",
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


def test_fixtures_view_shows_team_filter_when_on_team_query() -> None:
    view = _fixtures(on_team_query=lambda _q: None)
    fields = [node for node in _walk(view) if isinstance(node, ft.TextField)]
    assert fields
    assert fields[0].label == "Команда"
    blob = _blob(view)
    assert "Команда" in blob
    assert "Предстоящие" in blob
    assert "Все матчи" in blob


def test_fixtures_view_hides_filter_bar_without_on_team_query() -> None:
    view = _fixtures()
    fields = [node for node in _walk(view) if isinstance(node, ft.TextField)]
    assert fields == []
    assert "Команда" not in _blob(view)


def test_fixtures_view_upcoming_chips_call_callback() -> None:
    clicks: list[bool] = []
    view = _fixtures(
        on_team_query=lambda _q: None,
        upcoming_only=True,
        on_upcoming_only=clicks.append,
    )
    chips = [
        node
        for node in _walk(view)
        if isinstance(node, ft.Container) and isinstance(node.content, ft.Text)
    ]
    all_matches = next(chip for chip in chips if chip.content.value == "Все матчи")
    upcoming = next(chip for chip in chips if chip.content.value == "Предстоящие")
    all_matches.on_click(None)
    upcoming.on_click(None)
    assert clicks == [False, True]


def test_match_detail_hides_ai_block_when_disabled() -> None:
    hidden = match_detail_view(
        _forecast(),
        loading=False,
        error=None,
        on_back=lambda: None,
        show_ai_block=False,
    )
    blob = _blob(hidden)
    assert "AI-пояснение" not in blob
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
    assert "AI-пояснение" in blob
    assert "AI не настроен. Добавьте OPENAI_API_KEY в Настройках" in blob


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
    assert "Очистить кэш" in blob
