"""LLM caching policy: finished → no call, 12 h throttle, stale refresh, failures keep."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from football_prognoz.ai.explainer import Explainer
from football_prognoz.ai.news_summary import NewsSummarizer
from football_prognoz.ai.ollama import LLMError, LLMReply
from football_prognoz.data.football_data_org import match_from_api
from football_prognoz.data.store import SQLiteStore
from football_prognoz.domain.match import MatchStatus, Score
from football_prognoz.domain.news import NewsItem, NewsReport, TeamNews
from football_prognoz.models.predictor import Predictor
from football_prognoz.services.features import FeatureService
from football_prognoz.services.llm_policy import (
    FINISHED_NONE_TEXT,
    PLAN_FINISHED_NONE,
    PLAN_GENERATE,
    PLAN_REFRESH,
    PLAN_USE_SAVED,
    SavedAnalysis,
    generated_caption,
    plan_for,
)
from football_prognoz.services.matches import NEWS_NO_LLM_TEXT, MatchService

KICKOFF = datetime(2026, 10, 3, 14, 0, tzinfo=UTC)


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


class ScriptedLLM:
    """Answers with a valid analysis (markets from the real table) or a news summary."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.fail: LLMError | None = None
        self.verdict = "Первый разбор."

    def chat(self, system: str, user: str, **_kwargs) -> LLMReply:
        self.calls.append("news" if "headlines" in user else "match")
        if self.fail is not None:
            raise self.fail
        if "headlines" in user:
            body = {
                "summary": "По данным СМИ, у хозяев травма. Это важно для матча.",
                "home": {
                    "points": [{"text": "Сака под вопросом", "headline": "h1"}],
                    "relevance": "Касается матча.",
                },
                "away": {"points": [], "relevance": "Новостей мало."},
                "stale_note": "",
            }
            return LLMReply(json.dumps(body, ensure_ascii=False), "gpt-oss:120b")
        payload = json.loads(user)
        ids = [m["id"] for m in payload["markets"]][:3]
        body = {
            "summary": "Коротко.",
            "home_factors": [],
            "away_factors": [],
            "favorite": payload["favorite"],
            "verdict": self.verdict,
            "confidence": "low",
            "confidence_reason": "Мало матчей.",
            "market_comments": [{"market": ids[0], "comment": "Основной исход."}],
            "top_markets": [{"market": i, "reason": "Факты."} for i in ids],
            "risks": ["Мала выборка."],
        }
        return LLMReply(json.dumps(body, ensure_ascii=False), "gpt-oss:120b")


def _news() -> NewsReport:
    item = NewsItem(
        "Saka doubt for weekend", "BBC Sport", "https://x", KICKOFF - timedelta(days=1), "injury"
    )
    return NewsReport(TeamNews("Arsenal", (item,)), TeamNews("City"), provider="rss")


def _setup(tmp_path: Path, payload: dict, *, status=MatchStatus.TIMED, score=Score(None, None)):
    store = SQLiteStore(tmp_path / "p.db")
    store.upsert_matches([match_from_api(raw, "PL") for raw in payload["matches"]])
    match = replace(store.get_match(201), utc_date=KICKOFF, status=status, score=score)
    store.upsert_matches([match])
    llm = ScriptedLLM()
    clock = Clock(KICKOFF - timedelta(days=2))
    service = MatchService(
        client=object(),  # type: ignore[arg-type]
        store=store,
        features=FeatureService(store),
        predictor=Predictor(),
        explainer=Explainer(llm, "gpt-oss:120b"),
        news_summarizer=NewsSummarizer(llm),
        now=clock,
    )
    return service, store, llm, clock, match


def _run(service: MatchService, match) -> object:
    forecast = service.forecast(match, explain=False, details=False)
    forecast = replace(forecast, news=_news())
    forecast = service.explain_forecast(forecast)
    return service.summarize_news(forecast)


def test_plan_rules() -> None:
    from football_prognoz.domain.match import Match

    m = Match(1, "PL", KICKOFF, MatchStatus.TIMED, 1, 1, "A", 2, "B", Score(None, None))
    before = KICKOFF - timedelta(days=1)
    fresh = SavedAnalysis("match", {}, "m", before - timedelta(hours=11))
    stale = SavedAnalysis("match", {}, "m", before - timedelta(hours=13))
    assert plan_for(None, m, before) == PLAN_GENERATE
    assert plan_for(fresh, m, before) == PLAN_USE_SAVED
    assert plan_for(stale, m, before) == PLAN_REFRESH
    finished = replace(m, status=MatchStatus.FINISHED, score=Score(2, 1))
    assert plan_for(stale, finished, KICKOFF + timedelta(days=1)) == PLAN_USE_SAVED
    assert plan_for(None, finished, KICKOFF + timedelta(days=1)) == PLAN_FINISHED_NONE
    late = SavedAnalysis("match", {}, "m", KICKOFF + timedelta(minutes=30))
    assert plan_for(late, finished, KICKOFF + timedelta(days=1)) == PLAN_FINISHED_NONE
    live = replace(m, status=MatchStatus.IN_PLAY)
    assert plan_for(stale, live, KICKOFF + timedelta(hours=1)) == PLAN_USE_SAVED  # frozen
    caption = generated_caption(datetime(2026, 9, 29, 18, 40, tzinfo=UTC), "gpt-oss:120b", UTC)
    assert caption == "Сгенерировано 29.09.2026 18:40, модель gpt-oss:120b"


def test_finished_match_never_calls_the_llm(tmp_path: Path, matches_payload: dict) -> None:
    service, _store, llm, clock, match = _setup(
        tmp_path, matches_payload, status=MatchStatus.FINISHED, score=Score(2, 1)
    )
    clock.now = KICKOFF + timedelta(days=1)
    result = _run(service, match)
    assert llm.calls == []
    assert result.explanation is None and result.explanation_error is None
    assert result.analysis_note == FINISHED_NONE_TEXT
    assert result.news_summary is None and "матч уже сыгран" in result.news_note


def test_saved_pre_kickoff_analysis_is_shown_for_a_finished_match(
    tmp_path: Path, matches_payload: dict
) -> None:
    service, store, llm, clock, match = _setup(tmp_path, matches_payload)
    _run(service, match)  # generated two days before kick-off
    assert llm.calls == ["match", "news"]
    finished = replace(match, status=MatchStatus.FINISHED, score=Score(2, 1))
    store.upsert_matches([finished])
    clock.now = KICKOFF + timedelta(days=3)
    result = _run(service, finished)
    assert llm.calls == ["match", "news"]  # no new call
    assert result.explanation is not None and result.explanation.verdict == "Первый разбор."
    assert result.explanation.generated_at == KICKOFF - timedelta(days=2)
    assert result.news_summary is not None and result.news_summary.cited == {
        "h1": "Saka doubt for weekend"
    }


def test_results_are_saved_durably_and_throttled_for_12_hours(
    tmp_path: Path, matches_payload: dict
) -> None:
    service, store, llm, clock, match = _setup(tmp_path, matches_payload)
    first = _run(service, match)
    saved = store.get_llm_analysis(201, "match")
    assert saved is not None and saved["model"] == "gpt-oss:120b"
    assert saved["generated_at"] == KICKOFF - timedelta(days=2)
    assert store.get_llm_analysis(201, "news") is not None
    store.clear_all()  # «Очистить кэш» keeps saved analyses
    assert store.get_llm_analysis(201, "match") is not None
    store.upsert_matches([match])
    clock.now += timedelta(hours=11)
    llm.verdict = "Второй разбор."
    again = _run(service, match)
    assert llm.calls == ["match", "news"]
    assert again.explanation.verdict == first.explanation.verdict == "Первый разбор."


def test_stale_result_is_shown_then_refreshed_and_swapped(
    tmp_path: Path, matches_payload: dict
) -> None:
    service, store, llm, clock, match = _setup(tmp_path, matches_payload)
    _run(service, match)
    clock.now += timedelta(hours=13)
    llm.verdict = "Второй разбор."
    shown = service.forecast(match, explain=False, details=False)
    assert shown.analysis_plan == PLAN_REFRESH
    assert shown.explanation is not None and shown.explanation.verdict == "Первый разбор."
    refreshed = service.explain_forecast(shown)
    assert refreshed.explanation.verdict == "Второй разбор."
    assert refreshed.explanation.generated_at == clock.now
    assert store.get_llm_analysis(201, "match")["payload"]["verdict"] == "Второй разбор."


def test_failed_generation_keeps_the_saved_result(tmp_path: Path, matches_payload: dict) -> None:
    service, store, llm, clock, match = _setup(tmp_path, matches_payload)
    _run(service, match)
    clock.now += timedelta(hours=13)
    llm.fail = LLMError("Ollama не ответил вовремя.")
    result = _run(service, match)
    assert result.explanation is not None and result.explanation.verdict == "Первый разбор."
    assert result.explanation_error is None
    assert "не ответил" in result.analysis_refresh_error
    assert result.news_summary is not None and "Обновить не удалось" in result.news_summary_error
    saved = store.get_llm_analysis(201, "match")
    assert saved["payload"]["verdict"] == "Первый разбор."
    assert saved["generated_at"] == KICKOFF - timedelta(days=2)


def test_without_llm_news_block_says_no_key(tmp_path: Path, matches_payload: dict) -> None:
    store = SQLiteStore(tmp_path / "n.db")
    store.upsert_matches([match_from_api(raw, "PL") for raw in matches_payload["matches"]])
    match = replace(store.get_match(201), utc_date=KICKOFF, status=MatchStatus.TIMED)
    store.upsert_matches([match])
    service = MatchService(
        client=object(),  # type: ignore[arg-type]
        store=store,
        features=FeatureService(store),
        predictor=Predictor(),
        explainer=Explainer(None, "gpt-oss:120b"),
        now=Clock(KICKOFF - timedelta(days=1)),
    )
    forecast = service.forecast(match, explain=False, details=False)
    assert forecast.news_note == NEWS_NO_LLM_TEXT
    assert service.summarize_news(replace(forecast, news=_news())).news_note == NEWS_NO_LLM_TEXT


@pytest.mark.parametrize("hours", [0, 11.9])
def test_throttle_boundary(hours: float) -> None:
    from football_prognoz.domain.match import Match

    m = Match(1, "PL", KICKOFF, MatchStatus.TIMED, 1, 1, "A", 2, "B", Score(None, None))
    now = KICKOFF - timedelta(days=1)
    saved = SavedAnalysis("match", {}, "m", now - timedelta(hours=hours))
    assert plan_for(saved, m, now) == PLAN_USE_SAVED
