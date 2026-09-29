"""Regression: the Forecast screen rendered as a grey screen.

Root cause: the preliminary-score card used Row(wrap=True) with expand=True children.
Flet maps a wrapping Row to a Flutter Wrap, which cannot host Expanded children, so the
release client painted a grey error box over the screen. These tests build the view the
way the app does and run it through Flet's own serializer and a layout check.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from ui_check import layout_problems, serialize, texts

from football_prognoz.domain.match import Match, MatchLineup, MatchStatus, Score
from football_prognoz.domain.prediction import (
    Explanation,
    Factor,
    MatchFeatures,
    MatchForecast,
    Probabilities,
    Scoreline,
)
from football_prognoz.domain.team import Person, StandingRow, TeamRoster
from football_prognoz.ui.components.ai_analysis import AI_ERROR, AI_LOADING, AI_READY
from football_prognoz.ui.views.match_detail import match_detail_view


def _match() -> Match:
    return Match(
        id=1,
        competition_code="PL",
        utc_date=datetime(2026, 10, 3, 14, 0, tzinfo=UTC),
        status=MatchStatus.TIMED,
        matchday=7,
        home_id=57,
        home_name="Arsenal FC",
        away_id=65,
        away_name="Manchester City FC",
        score=Score(None, None),
        home_crest="https://crests.football-data.org/57.png",
        away_crest=None,
        venue=None,
    )


def _forecast(**overrides) -> MatchForecast:
    features = MatchFeatures(
        home_form="WWDLW",
        away_form="",
        home_elo=1612.0,
        away_elo=1588.0,
        h2h_summary="",
        home_position=2,
        away_position=None,
        home_recent_goals_for=2.0,
        home_recent_goals_against=0.8,
        away_recent_goals_for=1.4,
        away_recent_goals_against=1.1,
        sample_matches=18,
        home_standing=StandingRow(57, "Arsenal FC", 2, 7, 5, 1, 1, 16, 12, 5),
        away_standing=None,
    )
    roster = TeamRoster(
        57,
        "Arsenal FC",
        None,
        Person(1, "Coach", role="COACH"),
        (Person(2, "Keeper", position="Goalkeeper"), Person(3, "Striker", position="Offence")),
        venue="Emirates Stadium",
        city="London",
        country="England",
    )
    values = dict(
        match=_match(),
        probabilities=Probabilities(0.47, 0.27, 0.26),
        features=features,
        explanation=None,
        scoreline=Scoreline(1, 0, 0.13, 1.6, 0.9),
        home_roster=roster,
        away_roster=None,
        lineup=MatchLineup(home_start=(2,), home_bench=(3,)),
        sources=("football-data.org", "Elo + Poisson"),
    )
    values.update(overrides)
    return MatchForecast(**values)


WIDTHS = (1440, 1100, 1000, 820)


@pytest.mark.parametrize("width", WIDTHS)
@pytest.mark.parametrize("embedded", [False, True])
def test_forecast_view_builds_serializes_and_has_no_grey_layout(width: int, embedded: bool):
    view = match_detail_view(
        _forecast(),
        loading=False,
        error=None,
        on_back=lambda: None,
        window_width=width,
        embedded=embedded,
        ai_state=AI_LOADING,
    )
    assert layout_problems(view) == []
    assert serialize(view)
    blob = " ".join(texts(view))
    assert "47%" in blob
    assert "Идёт анализ…" in blob


@pytest.mark.parametrize(
    ("state", "extra", "needle"),
    [
        (AI_READY, {"explanation": None}, "AI не настроен"),
        (AI_ERROR, {"explanation_error": "таймаут"}, "таймаут"),
        (
            AI_READY,
            {
                "explanation": Explanation(
                    "Хозяева чуть сильнее.",
                    "deepseek-v4.1-flash",
                    home_factors=(Factor("Форма", "4 победы из 5", "up"),),
                    verdict="Небольшое преимущество хозяев.",
                )
            },
            "Небольшое преимущество хозяев.",
        ),
    ],
)
def test_forecast_view_ai_states_render(state: str, extra: dict, needle: str) -> None:
    view = match_detail_view(
        _forecast(**extra),
        loading=False,
        error=None,
        on_back=lambda: None,
        window_width=1440,
        ai_state=state if extra.get("explanation") or state == AI_ERROR else None,
    )
    assert layout_problems(view) == []
    serialize(view)
    assert any(needle in text for text in texts(view))


def test_forecast_view_loading_and_empty_states_serialize() -> None:
    for forecast, loading in ((None, True), (None, False)):
        view = match_detail_view(forecast, loading=loading, error="x", on_back=lambda: None)
        assert layout_problems(view) == []
        serialize(view)
