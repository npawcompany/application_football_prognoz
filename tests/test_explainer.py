from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from football_prognoz.ai.explainer import (
    SYSTEM_PROMPT,
    Explainer,
    ExplanationError,
    confidence_cap,
    parse_analysis,
)
from football_prognoz.ai.ollama import LLMError, LLMReply
from football_prognoz.domain.match import Match, MatchStatus, Score
from football_prognoz.domain.prediction import (
    FactsPackage,
    MatchFeatures,
    Probabilities,
    Scoreline,
)


def _answer(**overrides: object) -> str:
    data: dict[str, object] = {
        "summary": "Хозяева чуть предпочтительнее по форме, но оценка не гарантирует исход.",
        "home_factors": [
            {"factor": "Форма WWDLW", "effect": "Поддерживает хозяев", "direction": "up"}
        ],
        "away_factors": [
            {"factor": "Elo выше на 30", "effect": "Сдерживает перевес хозяев", "direction": "+"}
        ],
        "favorite": "1",
        "verdict": "Небольшое преимущество хозяев, ничья вполне возможна.",
        "confidence": "high",
        "confidence_reason": "Вероятности близки.",
    }
    data.update(overrides)
    return json.dumps(data, ensure_ascii=False)


class FakeLLM:
    def __init__(self, *answers: str, model: str = "deepseek-v4.1-flash") -> None:
        self.answers = list(answers)
        self.calls: list[dict[str, object]] = []
        self.model = model

    def chat(
        self, system: str, user: str, *, temperature: float = 0.2, json_mode: bool = True
    ) -> LLMReply:
        self.calls.append(
            {"system": system, "user": user, "temperature": temperature, "json": json_mode}
        )
        return LLMReply(self.answers.pop(0), self.model)


class FailingLLM:
    def chat(self, system: str, user: str, **_kwargs: object) -> LLMReply:
        raise LLMError("Ollama отклонил запрос (401): проверьте OLLAMA_API_KEY.", 401)


class MemoryCache:
    def __init__(self) -> None:
        self.data: dict[str, dict] = {}

    def get(self, key: str) -> dict | None:
        return self.data.get(key)

    def put(self, key: str, value: dict) -> None:
        self.data[key] = value


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


def _features(sample: int = 20) -> MatchFeatures:
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
        sample_matches=sample,
    )


PROBS = Probabilities(0.41, 0.27, 0.32)


def test_explainer_disabled_without_llm() -> None:
    explainer = Explainer(None, "deepseek-v4.1-flash")
    assert explainer.enabled is False
    assert explainer.explain(_match(), _features(), Probabilities(0.4, 0.3, 0.3)) is None


def test_explainer_prompt_contains_facts_and_structured_result() -> None:
    llm = FakeLLM(_answer())
    explainer = Explainer(llm, "deepseek-v4.1-flash")
    score = Scoreline(1, 1, 0.14, 1.5, 1.5)
    facts = FactsPackage(
        data={
            "elo": {"gap": -30.0},
            "rest_days": {"home": 6, "away": 3},
            "player_status": {"home": {"absences": [{"player": "B. Saka"}]}},
        },
        sources=("football-data.org", "API-Football: травмы и дисквалификации"),
    )
    result = explainer.explain(_match(), _features(), PROBS, score, facts)
    assert result is not None
    assert "хозяева" in result.text.lower()
    assert result.home_factors[0].direction == "up"
    assert result.away_factors[0].direction == "up"  # "+" alias
    assert result.verdict.startswith("Небольшое")
    assert result.sources == facts.sources
    payload = json.loads(llm.calls[0]["user"])
    assert payload["match"]["home"] == "Arsenal FC"
    assert payload["facts"]["home_form"] == "WWDLW"
    assert payload["facts"]["home_recent_goals_for"] == 1.8
    assert payload["probabilities"]["home"] == 0.41
    assert payload["favorite"] == "1"
    assert payload["preliminary_score"]["label"] == "1:1"
    assert payload["context"]["rest_days"] == {"home": 6, "away": 3}
    assert payload["player_status"]["home"]["absences"][0]["player"] == "B. Saka"
    assert "injuries" not in payload["facts"]
    assert "угадай" not in SYSTEM_PROMPT.lower()
    assert "Do not invent" in SYSTEM_PROMPT
    assert llm.calls[0]["json"] is True


def test_prompt_has_null_player_status_without_api_football() -> None:
    llm = FakeLLM(_answer())
    Explainer(llm, "m").explain(_match(), _features(), PROBS)
    payload = json.loads(llm.calls[0]["user"])
    assert payload["player_status"] is None
    assert payload["data_sources"] == []


def test_confidence_is_capped_by_close_probabilities() -> None:
    llm = FakeLLM(_answer(confidence="high"))
    result = Explainer(llm, "m").explain(_match(), _features(), PROBS)
    assert result is not None
    assert result.confidence == "medium"  # top 0.41 < 0.55 -> at most medium
    assert "снижен" in result.confidence_reason
    assert result.confidence_label == "средняя"


def test_confidence_cap_rules() -> None:
    assert confidence_cap(Probabilities(0.7, 0.2, 0.1), _features(3)) == "low"
    assert confidence_cap(Probabilities(0.5, 0.3, 0.2), _features(20)) == "medium"
    assert confidence_cap(Probabilities(0.7, 0.2, 0.1), _features(8)) == "medium"
    assert confidence_cap(Probabilities(0.7, 0.2, 0.1), _features(20)) == "high"


def test_invalid_json_is_retried_once_with_zero_temperature() -> None:
    llm = FakeLLM("Хозяева сильнее, вот и всё.", "```json\n" + _answer() + "\n```")
    result = Explainer(llm, "m").explain(_match(), _features(), PROBS)
    assert result is not None
    assert len(llm.calls) == 2
    assert llm.calls[1]["temperature"] == 0.0
    assert "rejected" in str(llm.calls[1]["user"])


def test_invalid_twice_raises_explanation_error() -> None:
    llm = FakeLLM("not json", "{still not json")
    with pytest.raises(ExplanationError, match="дважды"):
        Explainer(llm, "m").explain(_match(), _features(), PROBS)
    assert len(llm.calls) == 2


def test_favorite_contradicting_probabilities_is_rejected() -> None:
    llm = FakeLLM(_answer(favorite="2"), _answer(favorite="2"))
    with pytest.raises(ExplanationError, match="противоречит"):
        Explainer(llm, "m").explain(_match(), _features(), PROBS)


@pytest.mark.parametrize(
    "verdict",
    ["Хозяева гарантированно победят.", "Арсенал точно выиграет.", "Без сомнения победа"],
)
def test_guaranteed_outcome_wording_is_rejected(verdict: str) -> None:
    with pytest.raises(ValueError, match="гарант"):
        parse_analysis(_answer(verdict=verdict), PROBS, _features())


def test_negated_guarantee_is_allowed() -> None:
    parsed = parse_analysis(
        _answer(verdict="Перевес хозяев не гарантирует победу."), PROBS, _features()
    )
    assert parsed["verdict"].startswith("Перевес")


def test_llm_error_propagates() -> None:
    with pytest.raises(LLMError, match="401"):
        Explainer(FailingLLM(), "m").explain(_match(), _features(), PROBS)


def test_cache_hit_skips_llm() -> None:
    cache = MemoryCache()
    first = FakeLLM(_answer())
    Explainer(first, "m", cache=cache).explain(_match(), _features(), PROBS)
    second = FakeLLM()
    result = Explainer(second, "m", cache=cache).explain(_match(), _features(), PROBS)
    assert result is not None
    assert second.calls == []
    assert result.model == "deepseek-v4.1-flash"
