from __future__ import annotations

from pathlib import Path

from football_prognoz.data.csv_loader import load_csv
from football_prognoz.data.football_data_org import match_from_api
from football_prognoz.data.store import SQLiteStore
from football_prognoz.domain.match import MatchStatus
from football_prognoz.domain.team import StandingRow
from football_prognoz.services.features import FeatureService


def _store_with_history(tmp_path: Path, matches_payload: dict, standings_payload: dict) -> SQLiteStore:
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


def test_features_from_cached_history(tmp_path: Path, matches_payload: dict, standings_payload: dict) -> None:
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
