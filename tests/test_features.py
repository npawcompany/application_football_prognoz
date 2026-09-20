from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from football_prognoz.ai.explainer import Explainer
from football_prognoz.data import FREE_COMPETITIONS
from football_prognoz.data.csv_loader import load_csv
from football_prognoz.data.football_data_org import FootballDataError, match_from_api
from football_prognoz.data.store import SQLiteStore
from football_prognoz.domain.match import MatchStatus
from football_prognoz.domain.prediction import Explanation
from football_prognoz.domain.team import Competition, StandingRow
from football_prognoz.models.predictor import Predictor
from football_prognoz.services.features import FeatureService
from football_prognoz.services.matches import MatchService


def _store_with_history(
    tmp_path: Path, matches_payload: dict, standings_payload: dict
) -> SQLiteStore:
    store = SQLiteStore(tmp_path / "test.db")
    matches = [match_from_api(raw, "PL") for raw in matches_payload["matches"]]
    store.upsert_matches(matches)
    rows = []
    for table in standings_payload["standings"]:
        for raw in table["table"]:
            team = raw["team"]
            rows.append(
                StandingRow(
                    team_id=team["id"],
                    team_name=team["name"],
                    position=raw["position"],
                    played=raw["playedGames"],
                    won=raw["won"],
                    draw=raw["draw"],
                    lost=raw["lost"],
                    points=raw["points"],
                    goals_for=raw["goalsFor"],
                    goals_against=raw["goalsAgainst"],
                )
            )
    store.upsert_standings("PL", rows)
    return store


def test_features_from_cached_history(
    tmp_path: Path, matches_payload: dict, standings_payload: dict
) -> None:
    store = _store_with_history(tmp_path, matches_payload, standings_payload)
    upcoming = store.get_match(201)
    assert upcoming is not None
    features = FeatureService(store).build(upcoming)
    assert features.sample_matches >= 4
    assert "W" in features.home_form or "D" in features.home_form
    assert features.home_position == 2
    assert features.away_position == 1
    assert "очных" in features.h2h_summary or "Последние" in features.h2h_summary


def test_csv_import_into_store(tmp_path: Path, sample_csv: Path) -> None:
    store = SQLiteStore(tmp_path / "csv.db")
    store.upsert_matches(load_csv(sample_csv))
    rows = store.list_matches("PL")
    assert len(rows) == 6
    assert all(row.status is MatchStatus.FINISHED for row in rows)


def test_cache_ttl(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "ttl.db")
    assert store.is_fresh("competitions", 24) is False
    store.mark_fetched("competitions")
    assert store.is_fresh("competitions", 24) is True
    assert store.is_fresh("competitions", ttl_hours=0.0000001) is False
    assert store.fetched_at("competitions") is not None


def test_clear_all_keeps_schema_and_empty_list(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "clear.db")
    store.upsert_competitions([Competition(2021, "PL", "Premier League")])
    store.mark_fetched("matches:PL:2025")
    store.clear_all()
    assert store.list_competitions() == []
    assert store.list_matches() == []
    assert store.fetched_at("competitions") is None
    store.upsert_competitions([Competition(2014, "PD", "La Liga")])
    assert [row.code for row in store.list_competitions()] == ["PD"]


def test_elo_reused_when_history_fingerprint_unchanged(
    tmp_path: Path, matches_payload: dict, standings_payload: dict, monkeypatch
) -> None:
    store = _store_with_history(tmp_path, matches_payload, standings_payload)
    service = FeatureService(store)
    upcoming = store.get_match(201)
    assert upcoming is not None
    calls = {"n": 0}
    import football_prognoz.services.features as features_mod

    original = features_mod.build_elo

    def wrapped(history):
        calls["n"] += 1
        return original(history)

    monkeypatch.setattr(features_mod, "build_elo", wrapped)
    first = service.build(upcoming)
    second = service.build(upcoming)
    assert calls["n"] == 1
    assert first.home_elo == second.home_elo


def test_elo_recomputed_when_history_changes(
    tmp_path: Path, matches_payload: dict, standings_payload: dict, monkeypatch
) -> None:
    store = _store_with_history(tmp_path, matches_payload, standings_payload)
    service = FeatureService(store)
    upcoming = store.get_match(201)
    assert upcoming is not None
    import football_prognoz.services.features as features_mod

    calls = {"n": 0}
    original = features_mod.build_elo

    def wrapped(history):
        calls["n"] += 1
        return original(history)

    monkeypatch.setattr(features_mod, "build_elo", wrapped)
    service.build(upcoming)
    extra = store.get_match(105)
    assert extra is not None
    store.upsert_matches([replace(extra, id=999)])
    service.build(upcoming)
    assert calls["n"] == 2


class _FakeClient:
    def __init__(self) -> None:
        self.comp_calls = 0
        self.match_calls: list[str] = []

    def list_competitions(self):
        self.comp_calls += 1
        return [Competition(2021, "PL", "Premier League")]

    def list_matches(self, code, season=None):
        self.match_calls.append(code)
        return []

    def list_standings(self, code):
        return []


class _BoomClient(_FakeClient):
    def list_matches(self, code, season=None):
        self.match_calls.append(code)
        raise FootballDataError("offline")


class _TrackingExplainer:
    def __init__(self) -> None:
        self.calls = 0

    def explain(self, *args, **kwargs):
        self.calls += 1
        return Explanation("Хозяева чуть сильнее по форме.", "test-model")


def _service(tmp_path: Path, client, explainer=None) -> MatchService:
    store = SQLiteStore(tmp_path / "svc.db")
    return MatchService(
        client=client,
        store=store,
        features=FeatureService(store),
        predictor=Predictor(),
        explainer=explainer or Explainer(None, "test-model"),
    )


def test_cached_competitions_no_http(tmp_path: Path) -> None:
    client = _FakeClient()
    service = _service(tmp_path, client)
    items = service.cached_competitions()
    assert client.comp_calls == 0
    assert {item.code for item in items} == {item.code for item in FREE_COMPETITIONS}


def test_bootstrap_does_not_prefetch_leagues(tmp_path: Path) -> None:
    client = _FakeClient()
    service = _service(tmp_path, client)
    progress: list[tuple[str, int, int]] = []
    items = service.bootstrap(lambda label, done, total: progress.append((label, done, total)))
    assert [item.code for item in items] == ["PL"]
    assert progress == [("Лиги", 1, 1)]
    assert client.match_calls == []
    assert client.comp_calls == 1


def test_prefetch_competition_returns_cache_on_error(tmp_path: Path, matches_payload: dict) -> None:
    store = SQLiteStore(tmp_path / "svc.db")
    matches = [match_from_api(raw, "PL") for raw in matches_payload["matches"]]
    store.upsert_matches(matches)
    service = MatchService(
        client=_BoomClient(),
        store=store,
        features=FeatureService(store),
        predictor=Predictor(),
        explainer=Explainer(None, "test-model"),
    )
    cached = service.prefetch_competition("PL")
    assert [row.id for row in cached] == [row.id for row in matches]


def test_clear_cache_empties_store_and_resets_elo(tmp_path: Path) -> None:
    client = _FakeClient()
    service = _service(tmp_path, client)
    service.bootstrap()
    assert service.cached_competitions()[0].code == "PL"
    service.clear_cache()
    codes = {item.code for item in service.cached_competitions()}
    assert codes == {item.code for item in FREE_COMPETITIONS}


def test_forecast_explain_false_skips_llm(
    tmp_path: Path, matches_payload: dict, standings_payload: dict
) -> None:
    store = _store_with_history(tmp_path, matches_payload, standings_payload)
    explainer = _TrackingExplainer()
    service = MatchService(
        client=_FakeClient(),
        store=store,
        features=FeatureService(store),
        predictor=Predictor(),
        explainer=explainer,  # type: ignore[arg-type]
    )
    upcoming = store.get_match(201)
    assert upcoming is not None
    forecast = service.forecast(upcoming, explain=False)
    assert explainer.calls == 0
    assert forecast.explanation is None
    probs = forecast.probabilities
    assert probs.home + probs.draw + probs.away > 0.99
    filled = service.explain_forecast(forecast)
    assert explainer.calls == 1
    assert filled.explanation is not None
    assert filled.probabilities == forecast.probabilities
