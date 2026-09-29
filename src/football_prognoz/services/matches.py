from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime

from football_prognoz.ai.explainer import Explainer
from football_prognoz.ai.ollama import LLMError
from football_prognoz.data import FREE_COMPETITIONS
from football_prognoz.data.football_data_org import FootballDataError, FootballDataOrgClient
from football_prognoz.data.store import (
    TTL_FINISHED_HOURS,
    TTL_SCHEDULED_HOURS,
    SQLiteStore,
)
from football_prognoz.domain.match import Match, MatchLineup
from football_prognoz.domain.prediction import MatchForecast
from football_prognoz.domain.team import Competition, StandingRow, Team, TeamRoster
from football_prognoz.models.predictor import Predictor
from football_prognoz.services.facts import SRC_FOOTBALL_DATA, SRC_MODEL, FactsService
from football_prognoz.services.features import FeatureService
from football_prognoz.services.news import NewsService
from football_prognoz.services.player_status import PlayerStatusService

log = logging.getLogger(__name__)

BASE_SOURCES = (SRC_FOOTBALL_DATA, SRC_MODEL)


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
        player_status: PlayerStatusService | None = None,
        news: NewsService | None = None,
    ) -> None:
        self._client = client
        self._store = store
        self._features = features
        self._predictor = predictor
        self._explainer = explainer
        self._player_status = player_status
        self._news = news
        self._facts = FactsService(store)

    @property
    def llm_enabled(self) -> bool:
        return self._explainer.enabled

    @property
    def llm_model(self) -> str:
        return self._explainer.model_name

    @property
    def player_status_enabled(self) -> bool:
        return self._player_status is not None and self._player_status.enabled

    def close(self) -> None:
        """Close HTTP clients owned by this service (called when settings change)."""
        for closer in (
            getattr(self._client, "close", None),
            self._explainer.close,
            getattr(self._player_status, "close", None),
            getattr(self._news, "close", None),
        ):
            if not callable(closer):
                continue
            try:
                closer()
            except Exception as exc:  # noqa: BLE001 — closing must not break a settings save
                log.warning("Closing a client failed: %s", exc)

    def ping(self) -> list[Competition]:
        return self._client.ping()

    def clear_cache(self) -> None:
        """Drop SQLite rows. The next read uses cache-first fallbacks."""
        self._store.clear_all()
        self._features = FeatureService(self._store)
        self._facts = FactsService(self._store)

    def cached_competitions(self) -> list[Competition]:
        """Return stored competitions or the free-tier list. Never hits HTTP."""
        cached = self._store.list_competitions()
        return cached if cached else list(FREE_COMPETITIONS)

    def bootstrap(
        self,
        progress: Callable[[str, int, int], None] | None = None,
    ) -> list[Competition]:
        """Load the competition list (cache/TTL). Do not prefetch every league."""
        items = self.list_competitions()
        if progress is not None:
            progress("Лиги", 1, 1)
        return items

    def prefetch_competition(self, code: str, *, force: bool = False) -> list[Match]:
        """Refresh one competition; on API errors return whatever is already cached."""
        try:
            return self.refresh_competition(code, force=force)
        except FootballDataError:
            return self._store.list_matches(code)

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

    def competition_matches(self, code: str, *, force: bool = False) -> list[Match]:
        """Refresh one league and return every stored match (any status)."""
        return self.refresh_competition(code, force=force)

    def upcoming(self, code: str, *, force: bool = False) -> list[Match]:
        now = datetime.now(UTC)
        matches = self.refresh_competition(code, force=force)
        upcoming = [m for m in matches if m.status.is_upcoming() and m.utc_date >= now]
        if upcoming:
            return upcoming
        return [m for m in matches if m.status.is_upcoming()]

    def standings(self, code: str) -> list[StandingRow]:
        return self._store.list_standings(code)

    def cached_teams(self) -> list[Team]:
        """Teams already in SQLite. Settings combobox must not hit the API."""
        return self._store.list_cached_teams()

    def get_match(self, match_id: int) -> Match | None:
        return self._store.get_match(match_id)

    def _roster_for(
        self,
        team_id: int,
        *,
        fallback_name: str,
        fallback_crest: str | None,
    ) -> TeamRoster | None:
        if team_id <= 0:
            return None
        cache_key = f"team:{team_id}"
        cached = self._store.get_roster(team_id)
        if cached and self._store.is_fresh(cache_key, TTL_FINISHED_HOURS):
            return cached
        get_team = getattr(self._client, "get_team", None)
        if not callable(get_team):
            return cached
        try:
            roster = get_team(team_id)
        except FootballDataError as exc:
            if cached is not None:
                return cached
            if exc.status_code == 403:
                empty = TeamRoster(team_id, fallback_name, fallback_crest, None, ())
                self._store.upsert_roster(empty)
                return empty
            return None
        self._store.upsert_roster(roster)
        return roster

    def _lineup_for(self, match: Match) -> MatchLineup | None:
        cache_key = f"match:{match.id}"
        cached = self._store.get_lineup(match.id)
        if cached and self._store.is_fresh(cache_key, TTL_SCHEDULED_HOURS):
            return cached
        get_match = getattr(self._client, "get_match", None)
        if not callable(get_match):
            return cached
        try:
            detailed, lineup = get_match(match.id)
        except FootballDataError:
            return cached
        if detailed.venue and not match.venue:
            self._store.upsert_matches([replace(match, venue=detailed.venue)])
        self._store.upsert_lineup(match.id, lineup)
        return lineup

    def forecast(self, match: Match, *, explain: bool = True) -> MatchForecast:
        features = self._features.build(match)
        probabilities = self._predictor.predict(match, features)
        scoreline = self._predictor.preliminary_score(features)
        home_roster = self._roster_for(
            match.home_id, fallback_name=match.home_name, fallback_crest=match.home_crest
        )
        away_roster = self._roster_for(
            match.away_id, fallback_name=match.away_name, fallback_crest=match.away_crest
        )
        lineup = self._lineup_for(match)
        stored = self._store.get_match(match.id) or match
        result = MatchForecast(
            match=stored,
            probabilities=probabilities,
            features=features,
            explanation=None,
            scoreline=scoreline,
            home_roster=home_roster,
            away_roster=away_roster,
            lineup=lineup,
            sources=BASE_SOURCES,
        )
        if explain:
            return self.enrich(result, explain=True)
        return result

    def attach_player_status(self, forecast: MatchForecast) -> MatchForecast:
        """Add API-Football facts. Zero HTTP calls when API_FOOTBALL_KEY is not set."""
        if self._player_status is None or not self._player_status.enabled:
            return forecast
        report = self._player_status.report_for(forecast.match)
        if report is None:
            return forecast
        sources = tuple(dict.fromkeys(forecast.sources + report.sources))
        return replace(forecast, player_status=report, sources=sources)

    @property
    def news_enabled(self) -> bool:
        return self._news is not None and self._news.enabled

    def attach_news(self, forecast: MatchForecast) -> MatchForecast:
        """Add recent team headlines (GNews or RSS). Never raises, never touches 1X2."""
        if not self.news_enabled:
            return forecast
        assert self._news is not None
        try:
            report = self._news.report_for(forecast.match)
        except Exception as exc:  # noqa: BLE001 — news is optional context
            log.warning("News lookup failed: %s", exc)
            return forecast
        if report is None:
            return forecast
        sources = forecast.sources + (report.sources if report.has_data() else ())
        return replace(forecast, news=report, sources=tuple(dict.fromkeys(sources)))

    def explain_forecast(self, forecast: MatchForecast) -> MatchForecast:
        """Ask the LLM for a structured analysis; LLM failures land in explanation_error."""
        if not self._explainer.enabled:
            return replace(forecast, explanation=None, explanation_error=None)
        facts = self._facts.build(
            forecast.match,
            forecast.features,
            forecast.probabilities,
            forecast.scoreline,
            forecast.player_status,
            forecast.news,
        )
        try:
            explanation = self._explainer.explain(
                forecast.match,
                forecast.features,
                forecast.probabilities,
                forecast.scoreline,
                facts,
            )
        except LLMError as exc:
            log.warning("LLM explanation failed: %s", exc)
            return replace(forecast, explanation=None, explanation_error=str(exc))
        sources = facts.sources
        if explanation is not None:
            sources = sources + (f"Ollama: {explanation.model}",)
        return replace(
            forecast,
            explanation=explanation,
            explanation_error=None,
            sources=tuple(dict.fromkeys(forecast.sources + sources)),
        )

    def enrich(self, forecast: MatchForecast, *, explain: bool = True) -> MatchForecast:
        """Background step after the numbers are shown: player status, then LLM."""
        enriched = self.attach_player_status(forecast)
        enriched = self.attach_news(enriched)
        if explain and self._explainer.enabled:
            enriched = self.explain_forecast(enriched)
        return enriched
