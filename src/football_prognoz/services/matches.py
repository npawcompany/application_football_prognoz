from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta, tzinfo
from pathlib import Path
from typing import Any

from football_prognoz.ai.explainer import Explainer
from football_prognoz.ai.ollama import LLMError
from football_prognoz.data import FREE_COMPETITIONS
from football_prognoz.data.football_data_org import FootballDataError, FootballDataOrgClient
from football_prognoz.data.store import (
    TTL_FINISHED_HOURS,
    TTL_SCHEDULED_HOURS,
    SQLiteStore,
)
from football_prognoz.domain.history import CalibrationReport, CollectionResult, HistoricalHint
from football_prognoz.domain.match import Match, MatchLineup
from football_prognoz.domain.prediction import MatchForecast, Probabilities
from football_prognoz.domain.team import Competition, StandingRow, Team, TeamRoster
from football_prognoz.models.predictor import Predictor
from football_prognoz.services.calendar import (
    day_bounds,
    local_tz,
    match_days,
    request_range,
    week_window,
)
from football_prognoz.services.calibration import (
    calibration,
    export_calibration_csv,
    export_csv,
    historical_hint,
    llm_summary,
)
from football_prognoz.services.facts import SRC_FOOTBALL_DATA, SRC_MODEL, FactsService
from football_prognoz.services.features import FeatureService
from football_prognoz.services.history import ForecastHistoryService, Progress
from football_prognoz.services.leagues import LeagueInfo, league_infos
from football_prognoz.services.news import NewsService
from football_prognoz.services.player_status import PlayerStatusService

log = logging.getLogger(__name__)

BASE_SOURCES = (SRC_FOOTBALL_DATA, SRC_MODEL)


# Competitions whose season is a calendar year (Brasileirão runs April–December).
CALENDAR_YEAR_CODES = frozenset({"BSA"})
# Tournaments held every few years: the "season" is the edition (WC 2026, EC 2024/2028),
# so no year can be derived from today's date — ask the API for its current season.
TOURNAMENT_CODES = frozenset({"WC", "EC"})
KEY_REJECTED_STATUSES = frozenset({400, 401, 403})


def current_season_year(now: datetime | None = None, code: str | None = None) -> int | None:
    """Season start year football-data.org uses for `code` at `now`.

    European leagues: August–May, so the season flips in July. BSA: calendar year.
    WC / EC: None (the API default, `currentSeason`, is the only correct answer).
    """
    moment = now or datetime.now(UTC)
    upper = (code or "").upper()
    if upper in TOURNAMENT_CODES:
        return None
    if upper in CALENDAR_YEAR_CODES:
        return moment.year
    return moment.year if moment.month >= 7 else moment.year - 1


def matches_cache_key(code: str) -> str:
    """Cache key of a league's current-season calendar (fetched without ?season=)."""
    return f"matches:{code}:current"


def window_cache_key(day: date) -> str:
    start, _end = week_window(day)
    return f"window:{start.isoformat()}"


@dataclass(frozen=True)
class KeyCheck:
    ok: bool
    rejected: bool
    message: str
    leagues: int = 0


class Cancelled(Exception):
    """Background enrichment stopped because the user left the match."""


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
        self._history = self._make_history()
        self._calibration: tuple[tuple[int, str | None], CalibrationReport] | None = None
        self.key_rejected = False  # football-data.org answered 400/401/403 to /competitions

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

    def _make_history(self) -> ForecastHistoryService:
        return ForecastHistoryService(
            self._store,
            features=self._features,
            predictor=self._predictor,
            facts=self._facts,
            refresh=lambda code, force: self.prefetch_competition(code, force=force),
        )

    def collect_training_data(
        self,
        codes: list[str],
        *,
        progress: Progress | None = None,
        cancel: threading.Event | None = None,
    ) -> CollectionResult:
        """Store forecasts for upcoming / recent matches of `codes` and fill results."""
        return self._history.collect(codes, progress=progress, cancel=cancel)

    def calibration_report(self) -> CalibrationReport:
        """Quality of stored pre-match forecasts for the current model version (cached)."""
        version = self._history.model_version
        stamp = self._store.forecast_history_stamp(version)
        if self._calibration is None or self._calibration[0] != stamp:
            self._calibration = (stamp, calibration(self._history.records(), version))
        return self._calibration[1]

    def export_history(
        self,
        directory: Path | None = None,
        *,
        records_path: Path | None = None,
    ) -> tuple[Path, Path, int]:
        """Write forecast_history + calibration summary as CSV.

        `records_path` is the file the user picked in the save dialog; the calibration
        summary goes next to it. Without it both files get a timestamped name in
        `directory` (the app's data/exports folder).
        """
        if records_path is None:
            if directory is None:
                raise ValueError("directory or records_path is required")
            stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
            records_path = directory / f"forecast_history_{stamp}.csv"
            summary_path = directory / f"forecast_calibration_{stamp}.csv"
        else:
            if records_path.suffix.lower() != ".csv":
                records_path = records_path.with_name(records_path.name + ".csv")
            summary_path = records_path.with_name(f"{records_path.stem}_calibration.csv")
        rows = export_csv(self._store.list_forecast_records(), records_path)
        export_calibration_csv(self.calibration_report(), summary_path)
        return records_path, summary_path, rows

    def ping(self) -> list[Competition]:
        return self._client.ping()

    def clear_cache(self) -> None:
        """Drop SQLite rows. The next read uses cache-first fallbacks."""
        self._store.clear_all()
        self._features = FeatureService(self._store)
        self._facts = FactsService(self._store)
        self._history = self._make_history()  # forecast_history itself is kept

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
        except FootballDataError as exc:
            if exc.status_code in KEY_REJECTED_STATUSES:
                self.key_rejected = True
            cached = self._store.list_competitions()
            if cached:
                return cached
            return list(FREE_COMPETITIONS)
        self.key_rejected = False
        if items:
            self._store.upsert_competitions(items)
            return items
        return list(FREE_COMPETITIONS)

    def validate_key(self) -> list[Competition]:
        """Check the football-data.org key with one live request. Raises FootballDataError."""
        try:
            items = self._client.list_competitions()
        except FootballDataError as exc:
            if exc.status_code in KEY_REJECTED_STATUSES:
                self.key_rejected = True
            raise
        self.key_rejected = False
        if items:
            self._store.upsert_competitions(items)
        return items

    def check_key(self) -> KeyCheck:
        """validate_key for the UI: never raises, tells a rejected key from no network."""
        try:
            items = self.validate_key()
        except FootballDataError as exc:
            rejected = exc.status_code in KEY_REJECTED_STATUSES
            return KeyCheck(ok=False, rejected=rejected, message=str(exc))
        return KeyCheck(ok=True, rejected=False, message="", leagues=len(items))

    def cached_league_matches(self, code: str) -> list[Match]:
        """Season calendar of one league from SQLite (no HTTP)."""
        return self._store.list_matches(code)

    def refresh_competition(self, code: str, *, force: bool = False) -> list[Match]:
        # No ?season=: the API then serves its currentSeason, which is right for Jul–Jun
        # leagues, calendar-year BSA and WC/EC editions alike.
        cache_key = matches_cache_key(code)
        if not force and self._store.is_fresh(cache_key, TTL_SCHEDULED_HOURS):
            return self._store.list_matches(code)
        try:
            matches = self._client.list_matches(code)
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

    # --- calendar (date picker) ---------------------------------------------------

    def day_matches(
        self,
        day: date,
        *,
        codes: list[str] | tuple[str, ...] | None = None,
        tz: tzinfo | None = None,
        force: bool = False,
        now: datetime | None = None,
    ) -> list[Match]:
        """Matches of one local day across leagues (or `codes`), cache first.

        One GET /v4/matches?dateFrom&dateTo covers the whole week of `day`, so paging
        through days of the same week costs zero requests. On API errors the cached
        rows are returned; only an empty cache with a rejected key raises.
        """
        zone = tz or local_tz()
        moment = now or datetime.now(UTC)
        key = window_cache_key(day)
        _start, week_end = week_window(day)
        ttl = TTL_FINISHED_HOURS if week_end < moment.date() else TTL_SCHEDULED_HOURS
        if force or not self._store.is_fresh(key, ttl):
            date_from, date_to = request_range(day)
            try:
                fetched = self._client.list_matches_between(
                    date_from.isoformat(), date_to.isoformat()
                )
            except FootballDataError as exc:
                log.warning("Calendar window %s not refreshed: %s", key, exc)
                start, end = day_bounds(day, zone)
                cached = self._store.list_matches_between(start, end, codes)
                if not cached and exc.status_code in KEY_REJECTED_STATUSES:
                    raise
                return cached
            self._store.upsert_matches(fetched)
            self._store.mark_fetched(key)
        start, end = day_bounds(day, zone)
        return self._store.list_matches_between(start, end, codes)

    def cached_day_matches(
        self,
        day: date,
        *,
        codes: list[str] | tuple[str, ...] | None = None,
        tz: tzinfo | None = None,
    ) -> list[Match]:
        """SQLite only — lets the UI paint a day instantly while the refresh runs."""
        start, end = day_bounds(day, tz or local_tz())
        return self._store.list_matches_between(start, end, codes)

    def cached_match_days(
        self,
        first: date,
        last: date,
        *,
        codes: list[str] | tuple[str, ...] | None = None,
        tz: tzinfo | None = None,
    ) -> list[date]:
        """Local days between `first` and `last` that have cached matches (SQLite only)."""
        zone = tz or local_tz()
        start, _ = day_bounds(first, zone)
        _, end = day_bounds(last, zone)
        return match_days(self._store.list_matches_between(start, end, codes), zone)

    # --- leagues availability / favourite pickers ---------------------------------

    def league_infos(self, *, now: datetime | None = None) -> list[LeagueInfo]:
        """Every known league with its upcoming-match count for the next ~6 months."""
        moment = now or datetime.now(UTC)
        competitions = self.cached_competitions()
        counts = self._store.upcoming_counts(moment, moment + timedelta(days=183))
        complete = [
            item.code
            for item in competitions
            if self._store.fetched_at(matches_cache_key(item.code)) is not None
        ]
        return league_infos(competitions, counts, complete, today=moment.date())

    def refresh_league_counts(
        self,
        codes: list[str],
        *,
        cancel: threading.Event | None = None,
        progress: Callable[[int, int, str], None] | None = None,
    ) -> list[LeagueInfo]:
        """Load season calendars of `codes` (cached 6 h, rate-limited) to count matches."""
        total = len(codes)
        for index, code in enumerate(codes, start=1):
            if cancel is not None and cancel.is_set():
                break
            if progress is not None:
                progress(index - 1, total, code)
            self.prefetch_competition(code)
        if progress is not None:
            progress(total, total, "")
        return self.league_infos()

    def teams_by_league(self) -> dict[str, list[Team]]:
        return self._store.teams_by_competition()

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
        network: bool = True,
    ) -> TeamRoster | None:
        if team_id <= 0:
            return None
        cache_key = f"team:{team_id}"
        cached = self._store.get_roster(team_id)
        if not network or (cached and self._store.is_fresh(cache_key, TTL_FINISHED_HOURS)):
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

    def _lineup_for(self, match: Match, *, network: bool = True) -> MatchLineup | None:
        cache_key = f"match:{match.id}"
        cached = self._store.get_lineup(match.id)
        if not network or (cached and self._store.is_fresh(cache_key, TTL_SCHEDULED_HOURS)):
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

    def forecast(
        self,
        match: Match,
        *,
        explain: bool = True,
        details: bool = True,
    ) -> MatchForecast:
        """1X2 + preliminary score from local data (Elo + Poisson on cached matches).

        `details=False` is the UI path: no HTTP at all, rosters/lineup come from the
        cache only, so the numbers appear immediately. The background `enrich` step
        then loads club cards, lineup, player status, news and the LLM analysis.
        """
        features = self._features.build(match)
        probabilities = self._predictor.predict(match, features)
        scoreline = self._predictor.preliminary_score(features)
        home_roster = self._roster_for(
            match.home_id,
            fallback_name=match.home_name,
            fallback_crest=match.home_crest,
            network=details,
        )
        away_roster = self._roster_for(
            match.away_id,
            fallback_name=match.away_name,
            fallback_crest=match.away_crest,
            network=details,
        )
        lineup = self._lineup_for(match, network=details)
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
            history_hint=self._history_hint(probabilities),
        )
        if explain:
            return self.enrich(result, explain=True)
        return result

    def attach_details(self, forecast: MatchForecast) -> MatchForecast:
        """Club cards + lineup from football-data.org (cached; bounded rate-limit wait)."""
        match = forecast.match
        home = self._roster_for(
            match.home_id, fallback_name=match.home_name, fallback_crest=match.home_crest
        )
        away = self._roster_for(
            match.away_id, fallback_name=match.away_name, fallback_crest=match.away_crest
        )
        lineup = self._lineup_for(match)
        stored = self._store.get_match(match.id) or match
        return replace(
            forecast,
            match=stored,
            home_roster=home or forecast.home_roster,
            away_roster=away or forecast.away_roster,
            lineup=lineup or forecast.lineup,
        )

    def _history_hint(self, probabilities: Probabilities) -> HistoricalHint | None:
        try:
            return historical_hint(self.calibration_report(), probabilities)
        except Exception as exc:  # noqa: BLE001 — a stats problem must not break a forecast
            log.warning("Historical hint failed: %s", exc)
            return None

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
            self._history_summary(forecast),
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

    def _history_summary(self, forecast: MatchForecast) -> dict[str, Any] | None:
        try:
            return llm_summary(self.calibration_report(), forecast.history_hint)
        except Exception as exc:  # noqa: BLE001
            log.warning("History summary failed: %s", exc)
            return None

    def enrich(
        self,
        forecast: MatchForecast,
        *,
        explain: bool = True,
        cancel: threading.Event | None = None,
        on_step: Callable[[MatchForecast], None] | None = None,
    ) -> MatchForecast:
        """Background step after the numbers are shown: details, player status, news, LLM.

        The 1X2 probabilities are never touched. `cancel` is checked between steps
        (raises Cancelled); `on_step` receives the forecast before the slow LLM call so
        the UI can show squads and news while «Идёт анализ…» is still running.
        """

        def check() -> None:
            if cancel is not None and cancel.is_set():
                raise Cancelled()

        check()
        enriched = self.attach_details(forecast)
        check()
        enriched = self.attach_player_status(enriched)
        check()
        enriched = self.attach_news(enriched)
        check()
        if on_step is not None:
            on_step(enriched)
        if explain and self._explainer.enabled:
            enriched = self.explain_forecast(enriched)
            check()
        return enriched
