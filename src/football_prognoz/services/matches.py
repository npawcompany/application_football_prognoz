from __future__ import annotations

from datetime import UTC, datetime

from football_prognoz.ai.explainer import Explainer
from football_prognoz.data import FREE_COMPETITIONS
from football_prognoz.data.football_data_org import FootballDataError, FootballDataOrgClient
from football_prognoz.data.store import (
    TTL_FINISHED_HOURS,
    TTL_SCHEDULED_HOURS,
    SQLiteStore,
)
from football_prognoz.domain.match import Match
from football_prognoz.domain.prediction import MatchForecast
from football_prognoz.domain.team import Competition, StandingRow
from football_prognoz.models.predictor import Predictor
from football_prognoz.services.features import FeatureService


def current_season_year(now: datetime | None = None) -> int:
    moment = now or datetime.now(UTC)
    return moment.year if moment.month >= 7 else moment.year - 1


class MatchService:
    def __init__(
        self,
        client: FootballDataOrgClient,
        store: SQLiteStore,
        features: FeatureService,
        predictor: Predictor,
        explainer: Explainer,
    ) -> None:
        self._client = client
        self._store = store
        self._features = features
        self._predictor = predictor
        self._explainer = explainer

    def ping(self) -> list[Competition]:
        return self._client.ping()

    def list_competitions(self, *, force: bool = False) -> list[Competition]:
        if not force and self._store.is_fresh("competitions", TTL_FINISHED_HOURS):
            cached = self._store.list_competitions()
            if cached:
                return cached
        try:
            items = self._client.list_competitions()
        except FootballDataError:
            cached = self._store.list_competitions()
            if cached:
                return cached
            return list(FREE_COMPETITIONS)
        if items:
            self._store.upsert_competitions(items)
            return items
        return list(FREE_COMPETITIONS)

    def refresh_competition(self, code: str, *, force: bool = False) -> list[Match]:
        season = current_season_year()
        cache_key = f"matches:{code}:{season}"
        if not force and self._store.is_fresh(cache_key, TTL_SCHEDULED_HOURS):
            return self._store.list_matches(code)
        try:
            matches = self._client.list_matches(code, season=season)
            self._store.upsert_matches(matches)
            self._store.mark_fetched(cache_key)
        except FootballDataError:
            cached = self._store.list_matches(code)
            if cached:
                return cached
            raise
        standings_key = f"standings:{code}"
        if force or not self._store.is_fresh(standings_key, TTL_FINISHED_HOURS):
            try:
                rows = self._client.list_standings(code)
                self._store.upsert_standings(code, rows)
            except FootballDataError:
                pass
        return self._store.list_matches(code)

    def upcoming(self, code: str, *, force: bool = False) -> list[Match]:
        now = datetime.now(UTC)
        matches = self.refresh_competition(code, force=force)
        upcoming = [m for m in matches if m.status.is_upcoming() and m.utc_date >= now]
        if upcoming:
            return upcoming
        return [m for m in matches if m.status.is_upcoming()]

    def standings(self, code: str) -> list[StandingRow]:
        return self._store.list_standings(code)

    def get_match(self, match_id: int) -> Match | None:
        return self._store.get_match(match_id)

    def forecast(self, match: Match) -> MatchForecast:
        features = self._features.build(match)
        probabilities = self._predictor.predict(match, features)
        explanation = self._explainer.explain(match, features, probabilities)
        return MatchForecast(
            match=match,
            probabilities=probabilities,
            features=features,
            explanation=explanation,
        )
