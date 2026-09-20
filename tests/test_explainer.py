from __future__ import annotations

import json
from datetime import UTC, datetime

from football_prognoz.ai.explainer import Explainer
from football_prognoz.domain.match import Match, MatchStatus, Score
from football_prognoz.domain.prediction import MatchFeatures, Probabilities


class FakeLLM:
    def __init__(self) -> None:
        self.system = ""
        self.user = ""

    def complete(self, system: str, user: str) -> str:
        self.system = system
        self.user = user
        return "Хозяева чуть предпочтительнее по форме, но оценка не гарантирует исход."


def _match() -> Match:
    return Match(
        id=201,
        competition_code="PL",
        utc_date=datetime(2026, 9, 26, 14, 0, tzinfo=UTC),
        status=MatchStatus.SCHEDULED,
        matchday=6,
        home_id=57,
        home_name="Arsenal FC",
        away_id=65,
        away_name="Manchester City FC",
        score=Score(None, None),
    )


def _features() -> MatchFeatures:
    return MatchFeatures(
        home_form="WWDLW",
        away_form="WDWW",
        home_elo=1610.0,
        away_elo=1640.0,
        h2h_summary="Последние 2: Arsenal FC 0, ничьи 1, Manchester City FC 1",
        home_position=2,
        away_position=1,
        home_recent_goals_for=1.8,
        home_recent_goals_against=1.0,
        away_recent_goals_for=2.0,
        away_recent_goals_against=0.8,
        sample_matches=5,
    )


def test_explainer_disabled_without_llm() -> None:
    explainer = Explainer(None, "gpt-4o-mini")
    assert explainer.enabled is False
    assert explainer.explain(_match(), _features(), Probabilities(0.4, 0.3, 0.3)) is None


def test_explainer_prompt_contains_facts() -> None:
    llm = FakeLLM()
    explainer = Explainer(llm, "gpt-4o-mini")
    result = explainer.explain(_match(), _features(), Probabilities(0.41, 0.27, 0.32))
    assert result is not None
    assert "хозяева" in result.text.lower()
    payload = json.loads(llm.user)
    assert payload["match"]["home"] == "Arsenal FC"
    assert payload["match"]["away"] == "Manchester City FC"
    assert payload["facts"]["home_form"] == "WWDLW"
    assert payload["probabilities"]["home"] == 0.41
    assert "injuries" not in payload["facts"]
    assert "угадай" not in llm.system.lower()
    assert "Do not invent" in llm.system
