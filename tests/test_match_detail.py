from __future__ import annotations

from datetime import UTC, datetime

from football_prognoz.domain.match import Match, MatchStatus, Score
from football_prognoz.domain.prediction import (
    MatchFeatures,
    MatchForecast,
    Probabilities,
    Scoreline,
)
from football_prognoz.ui.views.match_detail import match_detail_view


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
    view = match_detail_view(forecast, loading=False, error=None, on_back=lambda: None)
    blob = " ".join(_texts(view))
    assert "Предварительный счёт" in blob
    assert "1:1" in blob
    assert "1.50 : 1.50" in blob
