from __future__ import annotations

from datetime import UTC, datetime

import flet as ft

from football_prognoz.domain.match import Match, MatchStatus, Score
from football_prognoz.domain.prediction import (
    MatchFeatures,
    MatchForecast,
    Probabilities,
    Scoreline,
)
from football_prognoz.ui.theme import BG, scaled
from football_prognoz.ui.views.match_detail import match_detail_view


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
    for attr in ("value", "text"):
        value = getattr(control, attr, None)
        if isinstance(value, str):
            found.append(value)
    content = getattr(control, "content", None)
    if content is not None:
        found.extend(_texts(content))
    controls = getattr(control, "controls", None)
    if controls:
        for child in controls:
            found.extend(_texts(child))
    return found


def test_match_detail_shows_preliminary_score() -> None:
    forecast = MatchForecast(
        match=Match(
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
        ),
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
    view = match_detail_view(forecast, loading=False, error=None, on_back=lambda: None)
    blob = " ".join(_texts(view))
    assert "Исход матча" in blob
    assert isinstance(view, ft.Container)
    assert view.bgcolor == BG
    assert isinstance(view.content, ft.ListView)
    assert "Фаворит" in blob
    assert "Предварительный счёт" in blob
    assert "1:1" in blob
    assert "Ожидаемые голы" in blob
    assert "1.50 : 1.50" in blob
    assert "Контекст матча" in blob
    assert "Состав и тренер" in blob
    assert "Arsenal" in blob
    assert "Man City" in blob
    assert "UTC" not in blob
    assert not any(
        isinstance(node, ft.Text) and node.value == forecast.match.label for node in _walk(view)
    )
    home = next(
        node for node in _walk(view) if isinstance(node, ft.Text) and node.value == "Arsenal"
    )
    assert home.max_lines == 1
    assert home.overflow == ft.TextOverflow.ELLIPSIS
    assert home.expand is False
    fact_rows = [
        node
        for node in _walk(view)
        if isinstance(node, ft.Row)
        and node.controls
        and all(getattr(child, "expand", None) is True for child in node.controls)
        and len(node.controls) in {2, 4}
    ]
    assert any(len(node.controls) == 2 for node in fact_rows)
    split = match_detail_view(
        forecast, loading=False, error=None, on_back=lambda: None, embedded=True
    )
    split_rows = [
        node
        for node in _walk(split)
        if isinstance(node, ft.Row)
        and node.controls
        and all(getattr(child, "expand", None) is True for child in node.controls)
        and len(node.controls) in {2, 4}
    ]
    assert any(len(node.controls) == 2 for node in split_rows)
    tile_h = max(120, scaled(128, 1440))
    assert sum(1 for node in _walk(view) if getattr(node, "height", None) == tile_h) == 2
    assert "кэше" not in blob
    assert "Нет очных встреч" in blob
    assert "VS" in blob
