from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from football_prognoz.ai.explainer import Explainer
from football_prognoz.ai.ollama import LLMError, LLMReply
from football_prognoz.data.football_data_org import match_from_api
from football_prognoz.data.store import SQLiteStore
from football_prognoz.domain.player_status import Absence, PlayerStatusReport, TeamStatus
from football_prognoz.models.predictor import Predictor
from football_prognoz.services.facts import SRC_FOOTBALL_DATA, FactsService
from football_prognoz.services.features import FeatureService
from football_prognoz.services.matches import MatchService


def _store(tmp_path: Path, matches_payload: dict) -> SQLiteStore:
    store = SQLiteStore(tmp_path / "f.db")
    store.upsert_matches([match_from_api(raw, "PL") for raw in matches_payload["matches"]])
    return store


def test_facts_package_has_indirect_factors(tmp_path: Path, matches_payload: dict) -> None:
    store = _store(tmp_path, matches_payload)
    match = store.get_match(201)
    assert match is not None
    features = FeatureService(store).build(match)
    probs = Predictor().predict(match, features)
    facts = FactsService(store).build(match, features, probs)
    data = facts.data
    assert data["elo"]["gap_with_home_advantage"] == round(
        features.home_elo + 80 - features.away_elo, 1
    )
    assert data["form"]["home"] == features.home_form
    assert data["home_away"]["home_team_at_home"]["played"] >= 1
    assert data["rest_days"]["home"] is not None and data["rest_days"]["home"] >= 0
    assert data["goal_trends"]["home"]["attack_trend"]
    assert data["head_to_head"]["summary"] == features.h2h_summary
    assert data["player_status"] is None
    assert facts.sources[0] == SRC_FOOTBALL_DATA
    json.dumps(data, ensure_ascii=False)  # serializable for the prompt


def test_facts_include_player_status_and_its_sources(tmp_path: Path, matches_payload: dict) -> None:
    store = _store(tmp_path, matches_payload)
    match = store.get_match(201)
    assert match is not None
    features = FeatureService(store).build(match)
    report = PlayerStatusReport(
        home=TeamStatus(
            "Arsenal FC",
            42,
            absences=(Absence(1460, "B. Saka", "Missing Fixture", "Hamstring", None, True),),
        ),
        away=TeamStatus("Manchester City FC", 50),
        sources=("API-Football: травмы и дисквалификации",),
    )
    facts = FactsService(store).build(
        match, features, Predictor().predict(match, features), player_status=report
    )
    absence = facts.data["player_status"]["home"]["absences"][0]
    assert absence == {
        "player": "B. Saka",
        "status": "не сыграет",
        "reason": "Hamstring",
        "suspension": False,
        "key_player": True,
        "expected_return": None,
    }
    assert "API-Football: травмы и дисквалификации" in facts.sources


class _LLM:
    def __init__(self, answer: str | None = None, error: LLMError | None = None) -> None:
        self.answer = answer
        self.error = error

    def chat(self, system: str, user: str, **_kwargs) -> LLMReply:
        if self.error:
            raise self.error
        return LLMReply(self.answer or "", "deepseek-v4.1-flash")


def _service(tmp_path: Path, matches_payload: dict, llm) -> MatchService:
    store = _store(tmp_path, matches_payload)
    return MatchService(
        client=object(),  # type: ignore[arg-type]
        store=store,
        features=FeatureService(store),
        predictor=Predictor(),
        explainer=Explainer(llm, "deepseek-v4.1-flash"),
    )


def test_explain_forecast_llm_error_is_reported_not_swallowed(
    tmp_path: Path, matches_payload: dict
) -> None:
    service = _service(tmp_path, matches_payload, _LLM(error=LLMError("Лимит (429).", 429)))
    match = service.get_match(201)
    assert match is not None
    forecast = service.forecast(match, explain=False)
    result = service.explain_forecast(forecast)
    assert result.explanation is None
    assert result.explanation_error == "Лимит (429)."
    assert result.probabilities == forecast.probabilities


def test_explain_forecast_success_keeps_probabilities_and_adds_sources(
    tmp_path: Path, matches_payload: dict
) -> None:
    service = _service(tmp_path, matches_payload, None)
    match = service.get_match(201)
    assert match is not None
    forecast = service.forecast(match, explain=False)
    answer = json.dumps(
        {
            "summary": "Коротко по-русски.",
            "home_factors": [],
            "away_factors": [],
            "favorite": forecast.probabilities.favorite_label,
            "verdict": "Итог совпадает с расчётом.",
            "confidence": "low",
            "confidence_reason": "Мало матчей.",
        },
        ensure_ascii=False,
    )
    service = _service(tmp_path / "b", matches_payload, _LLM(answer))
    result = service.explain_forecast(forecast)
    assert result.explanation is not None
    assert result.explanation_error is None
    assert result.probabilities == forecast.probabilities
    assert "Ollama: deepseek-v4.1-flash" in result.sources
    assert SRC_FOOTBALL_DATA in result.sources


def test_attach_news_adds_report_sources_and_prompt_block(
    tmp_path: Path, matches_payload: dict
) -> None:
    from datetime import UTC, datetime

    from football_prognoz.domain.news import NewsItem, NewsReport, TeamNews

    report = NewsReport(
        home=TeamNews(
            "Arsenal",
            (
                NewsItem(
                    "Saka doubt",
                    "BBC Sport",
                    "https://x",
                    datetime(2026, 9, 24, tzinfo=UTC),
                    "injury",
                ),
            ),
        ),
        away=TeamNews("Man City"),
        provider="rss",
        sources=("RSS спортивных изданий: BBC Sport",),
    )

    class _News:
        enabled = True

        def report_for(self, _match):
            return report

        def close(self) -> None:
            pass

    store = _store(tmp_path, matches_payload)
    captured: dict = {}

    class _CaptureLLM:
        def chat(self, system: str, user: str, **_kwargs) -> LLMReply:
            captured["user"] = json.loads(user)
            raise LLMError("stop", 500)

    service = MatchService(
        client=object(),  # type: ignore[arg-type]
        store=store,
        features=FeatureService(store),
        predictor=Predictor(),
        explainer=Explainer(_CaptureLLM(), "m"),
        news=_News(),  # type: ignore[arg-type]
    )
    assert service.news_enabled is True
    match = service.get_match(201)
    assert match is not None
    forecast = service.forecast(match, explain=False)
    enriched = service.enrich(forecast)
    assert enriched.news is report
    assert "RSS спортивных изданий: BBC Sport" in enriched.sources
    assert enriched.probabilities == forecast.probabilities
    news_block = captured["user"]["news"]
    assert news_block["home"][0]["topic"] == "травма"
    assert "news" not in captured["user"]["context"]


def test_attach_news_failure_keeps_forecast(tmp_path: Path, matches_payload: dict) -> None:
    class _Broken:
        enabled = True

        def report_for(self, _match):
            raise RuntimeError("boom")

    store = _store(tmp_path, matches_payload)
    service = MatchService(
        client=object(),  # type: ignore[arg-type]
        store=store,
        features=FeatureService(store),
        predictor=Predictor(),
        explainer=Explainer(None, "m"),
        news=_Broken(),  # type: ignore[arg-type]
    )
    match = service.get_match(201)
    assert match is not None
    forecast = service.forecast(match, explain=False)
    assert service.attach_news(forecast) == forecast


def test_match_service_collect_training_data_uses_league_refresh(
    tmp_path: Path, matches_payload: dict
) -> None:
    store = _store(tmp_path, matches_payload)

    class _Client:
        def __init__(self) -> None:
            self.calls = 0

        def list_matches(self, code, season=None):
            self.calls += 1
            return store.list_matches(code)

        def list_standings(self, code):
            return []

    client = _Client()
    service = MatchService(
        client=client,  # type: ignore[arg-type]
        store=store,
        features=FeatureService(store),
        predictor=Predictor(),
        explainer=Explainer(None, "m"),
    )
    result = service.collect_training_data(["PL"])
    assert client.calls == 1
    assert result.cancelled is False
    assert result.errors == ()


def _seed_history(store, n: int, hit_every: int) -> None:
    from datetime import UTC, datetime, timedelta

    from football_prognoz.domain.history import ForecastRecord

    base = datetime(2025, 1, 1, 15, tzinfo=UTC)
    for i in range(n):
        actual = "1" if i % hit_every == 0 else "2"
        store.insert_forecast_record(
            ForecastRecord(
                match_id=90_000 + i,
                model_version="elo-poisson-v1",
                competition_code="PL",
                kickoff_utc=base + timedelta(days=i),
                home_id=1,
                home_name="A",
                away_id=2,
                away_name="B",
                p_home=0.45,
                p_draw=0.3,
                p_away=0.25,
                predicted_outcome="1",
                predicted_score="1:0",
                score_probability=0.1,
                expected_home=1.4,
                expected_away=1.0,
                likely_outcomes=(),
                facts={},
                sources=(),
                sample_matches=20,
                forecast_at=base + timedelta(days=i) - timedelta(hours=3),
                made_after_kickoff=False,
                status="finished",
                actual_home=1 if actual == "1" else 0,
                actual_away=0 if actual == "1" else 1,
                actual_outcome=actual,
                is_correct=actual == "1",
            )
        )


def test_forecast_gets_history_hint_and_llm_gets_summary(
    tmp_path: Path, matches_payload: dict
) -> None:
    store = _store(tmp_path, matches_payload)
    captured: dict = {}

    class _CaptureLLM:
        def chat(self, system: str, user: str, **_kwargs) -> LLMReply:
            captured["user"] = json.loads(user)
            raise LLMError("stop", 500)

    service = MatchService(
        client=object(),  # type: ignore[arg-type]
        store=store,
        features=FeatureService(store),
        predictor=Predictor(),
        explainer=Explainer(_CaptureLLM(), "m"),
    )
    match = service.get_match(201)
    assert match is not None
    plain = service.forecast(match, explain=False)
    assert plain.history_hint is None  # no history yet -> hidden
    fav = plain.probabilities.favorite_label
    p = {"1": plain.probabilities.home, "X": plain.probabilities.draw}.get(
        fav, plain.probabilities.away
    )
    # Seed 40 evaluated forecasts in the same 10%-bucket as this forecast's favorite.
    _seed_history(store, 40, 4)
    with sqlite3.connect(store.path) as conn:
        conn.execute("UPDATE forecast_history SET p_home = ?", (p,))
    service = MatchService(
        client=object(),  # type: ignore[arg-type]
        store=store,
        features=FeatureService(store),
        predictor=Predictor(),
        explainer=Explainer(_CaptureLLM(), "m"),
    )
    forecast = service.forecast(match, explain=False)
    assert forecast.probabilities == plain.probabilities  # history never changes numbers
    assert forecast.history_hint is not None
    assert forecast.history_hint.sample >= 40
    service.explain_forecast(forecast)
    block = captured["user"]["historical_accuracy"]
    assert block["evaluated_prematch_forecasts"] == 40
    assert block["hit_rate"] == 0.25
    assert "historical_accuracy" not in captured["user"]["context"]
    report = service.calibration_report()
    assert report is service.calibration_report()  # cached until the table changes


def test_export_history_writes_two_csv_files(tmp_path: Path, matches_payload: dict) -> None:
    store = _store(tmp_path, matches_payload)
    _seed_history(store, 5, 2)
    service = MatchService(
        client=object(),  # type: ignore[arg-type]
        store=store,
        features=FeatureService(store),
        predictor=Predictor(),
        explainer=Explainer(None, "m"),
    )
    records_path, summary_path, rows = service.export_history(tmp_path / "exports")
    assert rows == 5
    assert records_path.exists() and summary_path.exists()
    assert records_path.read_text(encoding="utf-8").startswith("match_id,model_version")
