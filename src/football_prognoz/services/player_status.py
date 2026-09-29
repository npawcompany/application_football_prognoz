"""Player availability from API-Football, cached in SQLite and gated behind a key.

Without API_FOOTBALL_KEY this service is disabled and performs zero HTTP calls.
It never raises for API problems: gaps are reported in `PlayerStatusReport.notes`
(and logged) so the forecast keeps working exactly as before.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from football_prognoz.data.api_football import (
    FD_TO_AF_LEAGUE,
    AfFixture,
    ApiFootballClient,
    ApiFootballError,
    StoreBudget,
    af_season,
    parse_cards,
    parse_fixtures,
    parse_injuries,
    parse_lineups,
    parse_ratings,
    parse_sidelined,
    parse_transfers,
)
from football_prognoz.data.store import SQLiteStore
from football_prognoz.domain.match import Match
from football_prognoz.domain.player_status import (
    Absence,
    CardEvent,
    FixtureLineup,
    PlayerRating,
    PlayerStatusReport,
    TeamStatus,
    Transfer,
)
from football_prognoz.services.team_matching import find_fixture

log = logging.getLogger(__name__)

TTL_FIXTURES_H = 12
TTL_INJURIES_H = 4
TTL_SIDELINED_H = 24
TTL_FINISHED_H = 24 * 30  # events / ratings / lineups of finished matches do not change
TTL_TRANSFERS_H = 24 * 7
TTL_LINEUPS_LIVE_H = 0.25
TTL_PLAN_BLOCK_H = 24
LOW_BUDGET = 20  # below this many requests left today, skip optional endpoints
RECENT_MATCHES = 2
TRANSFER_WINDOW_DAYS = 90
KEY_PLAYER_TOP_N = 5
KEY_PLAYER_MIN_MINUTES = 45

SRC_FIXTURES = "API-Football: календарь (сопоставление матча)"
SRC_INJURIES = "API-Football: травмы и дисквалификации"
SRC_CARDS = "API-Football: карточки последних матчей"
SRC_LINEUPS = "API-Football: стартовые составы"
SRC_RATINGS = "API-Football: рейтинги игроков за последний матч"
SRC_SIDELINED = "API-Football: сроки отсутствия (sidelined)"
SRC_TRANSFERS = "API-Football: трансферы за 90 дней"


class _Stop(Exception):
    """A fatal API problem (auth/plan/quota/network): stop further requests."""


class PlayerStatusService:
    def __init__(
        self,
        client: ApiFootballClient | None,
        store: SQLiteStore,
        *,
        budget: StoreBudget | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._client = client
        self._store = store
        self._budget = budget
        self._now = now or (lambda: datetime.now(UTC))

    @property
    def enabled(self) -> bool:
        return self._client is not None and self._client.enabled

    def close(self) -> None:
        if self._client is not None:
            self._client.close()

    # --- cache helpers ---------------------------------------------------------

    def _cached(self, key: str, ttl_hours: float, fetch: Callable[[], Any]) -> Any:
        cached = self._store.get_api_payload(key, ttl_hours)
        if cached is not None:
            return cached
        assert self._client is not None
        try:
            payload = fetch()
        except ApiFootballError as exc:
            log.warning("API-Football %s failed: %s (%s)", key, exc, exc.kind)
            raise _Stop(str(exc)) from exc
        self._store.put_api_payload(key, payload)
        return payload

    def _budget_left(self) -> int:
        return self._budget.remaining() if self._budget is not None else 10**6

    # --- mapping ---------------------------------------------------------------

    def _map_fixture(
        self, match: Match, fixtures: list[AfFixture], league: int, season: int
    ) -> AfFixture | None:
        by_id = {item.fixture_id: item for item in fixtures}
        known = self._store.get_af_fixture(match.id)
        if known and known in by_id:
            return by_id[known]
        found = find_fixture(
            match,
            fixtures,
            known_home=self._store.get_af_team(match.home_id),
            known_away=self._store.get_af_team(match.away_id),
        )
        if found is None:
            return None
        self._store.upsert_af_fixture(
            match.id, found.fixture_id, af_league_id=league, season=season
        )
        for fd_id, fd_name, af_id, af_name in (
            (match.home_id, match.home_name, found.home_id, found.home_name),
            (match.away_id, match.away_name, found.away_id, found.away_name),
        ):
            if fd_id > 0 and af_id > 0:
                self._store.upsert_af_team(
                    fd_id, af_id, fd_name=fd_name, af_name=af_name, method="fixture_name_date"
                )
        return found

    # --- main entry ------------------------------------------------------------

    def report_for(self, match: Match) -> PlayerStatusReport | None:
        """None when disabled (no key). Otherwise a report; never raises for API errors."""
        if not self.enabled or self._client is None:
            return None
        client = self._client
        home = TeamStatus(team_name=match.home_name)
        away = TeamStatus(team_name=match.away_name)
        league = FD_TO_AF_LEAGUE.get(match.competition_code.upper())
        if league is None:
            return PlayerStatusReport(home, away, notes=("Лига не сопоставлена с API-Football.",))
        season = af_season(match.competition_code, match.utc_date)
        block_key = f"af:plan_block:{league}:{season}"
        if self._store.is_fresh(block_key, TTL_PLAN_BLOCK_H):
            return PlayerStatusReport(
                home,
                away,
                notes=(f"Тариф API-Football не даёт доступа к сезону {season}.",),
            )
        sources: list[str] = []
        notes: list[str] = []
        try:
            raw = self._cached(
                f"af:fixtures:{league}:{season}",
                TTL_FIXTURES_H,
                lambda: client.season_fixtures(league, season),
            )
        except _Stop as exc:
            self._remember_plan_block(exc, block_key)
            return PlayerStatusReport(home, away, notes=(str(exc),))
        fixtures = parse_fixtures(raw)
        fixture = self._map_fixture(match, fixtures, league, season)
        if fixture is None:
            return PlayerStatusReport(
                home, away, notes=("Матч не найден в календаре API-Football.",)
            )
        sources.append(SRC_FIXTURES)
        home_af, away_af = fixture.home_id, fixture.away_id
        home = TeamStatus(team_name=match.home_name, af_team_id=home_af)
        away = TeamStatus(team_name=match.away_name, af_team_id=away_af)
        parts: dict[str, dict[int, Any]] = {}
        try:
            parts["absences"] = self._absences(fixture.fixture_id)
            sources.append(SRC_INJURIES)
            parts["cards"] = self._recent_cards(fixtures, fixture, (home_af, away_af))
            sources.append(SRC_CARDS)
            lineups = self._lineups(match, fixture.fixture_id)
            if lineups is not None:
                parts["lineups"] = lineups
                if lineups:
                    sources.append(SRC_LINEUPS)
            if self._budget_left() >= LOW_BUDGET:
                parts["ratings"] = self._ratings(fixtures, fixture, (home_af, away_af))
                sources.append(SRC_RATINGS)
                parts["returns"] = self._returns(parts["absences"], match.utc_date)
                if parts["returns"]:
                    sources.append(SRC_SIDELINED)
                parts["transfers"] = self._transfers((home_af, away_af), match.utc_date)
                sources.append(SRC_TRANSFERS)
            else:
                notes.append(
                    "Мало запросов API-Football на сегодня: рейтинги и трансферы пропущены."
                )
        except _Stop as exc:
            self._remember_plan_block(exc, block_key)
            notes.append(str(exc))
        home = self._team_status(home, home_af, parts)
        away = self._team_status(away, away_af, parts)
        return PlayerStatusReport(
            home=home,
            away=away,
            af_fixture_id=fixture.fixture_id,
            sources=tuple(dict.fromkeys(sources)),
            notes=tuple(notes),
        )

    def _remember_plan_block(self, exc: _Stop, block_key: str) -> None:
        cause = exc.__cause__
        if isinstance(cause, ApiFootballError) and cause.kind == "plan":
            self._store.mark_fetched(block_key)

    # --- steps -----------------------------------------------------------------

    def _absences(self, fixture_id: int) -> dict[int, list[Absence]]:
        assert self._client is not None
        client = self._client
        raw = self._cached(
            f"af:injuries:{fixture_id}", TTL_INJURIES_H, lambda: client.injuries(fixture_id)
        )
        return parse_injuries(raw)

    def _recent_cards(
        self, fixtures: list[AfFixture], target: AfFixture, team_ids: tuple[int, int]
    ) -> dict[int, list[CardEvent]]:
        assert self._client is not None
        client = self._client
        out: dict[int, list[CardEvent]] = {}
        for team_id in team_ids:
            recent = _recent_finished(fixtures, target, team_id)[-RECENT_MATCHES:]
            for item in recent:
                raw = self._cached(
                    f"af:events:{item.fixture_id}",
                    TTL_FINISHED_H,
                    lambda fid=item.fixture_id: client.fixture_events(fid),
                )
                cards = parse_cards(raw, item.fixture_id, item.date.date().isoformat())
                reds = [card for card in cards.get(team_id, []) if card.is_red]
                out.setdefault(team_id, []).extend(reds)
        return out

    def _lineups(self, match: Match, fixture_id: int) -> dict[int, FixtureLineup] | None:
        """Only near kick-off (T-60 min … T+3 h) or for finished matches; else no call."""
        assert self._client is not None
        client = self._client
        now = self._now()
        finished = match.status.is_finished()
        window = (
            match.utc_date - timedelta(minutes=60) <= now <= match.utc_date + timedelta(hours=3)
        )
        if not (finished or window):
            return None
        ttl = TTL_FINISHED_H if finished else TTL_LINEUPS_LIVE_H
        raw = self._cached(f"af:lineups:{fixture_id}", ttl, lambda: client.lineups(fixture_id))
        return parse_lineups(raw)

    def _ratings(
        self, fixtures: list[AfFixture], target: AfFixture, team_ids: tuple[int, int]
    ) -> dict[int, list[PlayerRating]]:
        assert self._client is not None
        client = self._client
        out: dict[int, list[PlayerRating]] = {}
        for team_id in team_ids:
            recent = _recent_finished(fixtures, target, team_id)
            if not recent:
                continue
            last = recent[-1]
            raw = self._cached(
                f"af:players:{last.fixture_id}",
                TTL_FINISHED_H,
                lambda fid=last.fixture_id: client.fixture_players(fid),
            )
            out[team_id] = parse_ratings(raw).get(team_id, [])
        return out

    def _returns(
        self, absences: dict[int, list[Absence]], match_date: datetime
    ) -> dict[int, str | None]:
        assert self._client is not None
        client = self._client
        ids = sorted({a.player_id for items in absences.values() for a in items if a.player_id})
        if not ids:
            return {}
        ids = ids[:20]
        key = "af:sidelined:" + "-".join(str(pid) for pid in ids)
        raw = self._cached(key, TTL_SIDELINED_H, lambda: client.sidelined(ids))
        periods = parse_sidelined(raw)
        day = match_date.date().isoformat()
        returns: dict[int, str | None] = {}
        for player_id, items in periods.items():
            for _kind, start, end in items:
                if start and str(start) <= day and (not end or str(end) >= day):
                    returns[player_id] = str(end) if end else None
                    break
        return returns

    def _transfers(self, team_ids: tuple[int, int], match_date: datetime) -> dict[int, list[Any]]:
        assert self._client is not None
        client = self._client
        since = (match_date - timedelta(days=TRANSFER_WINDOW_DAYS)).date().isoformat()
        out: dict[int, list[Transfer]] = {}
        for team_id in team_ids:
            raw = self._cached(
                f"af:transfers:{team_id}",
                TTL_TRANSFERS_H,
                lambda tid=team_id: client.transfers(tid),
            )
            out[team_id] = parse_transfers(raw, team_id, since=since)[:6]
        return out

    @staticmethod
    def _team_status(
        base: TeamStatus, team_id: int, parts: dict[str, dict[int, Any]]
    ) -> TeamStatus:
        ratings: list[PlayerRating] = list(parts.get("ratings", {}).get(team_id, []))
        key_ids = {
            r.player_id
            for r in ratings[:KEY_PLAYER_TOP_N]
            if r.player_id and (r.minutes or 0) >= KEY_PLAYER_MIN_MINUTES
        }
        returns: dict[int, str | None] = parts.get("returns", {})
        absences = tuple(
            Absence(
                player_id=a.player_id,
                player_name=a.player_name,
                kind=a.kind,
                reason=a.reason,
                expected_return=returns.get(a.player_id),
                key_player=a.player_id in key_ids,
            )
            for a in parts.get("absences", {}).get(team_id, [])
        )
        return TeamStatus(
            team_name=base.team_name,
            af_team_id=team_id,
            absences=absences,
            red_cards=tuple(parts.get("cards", {}).get(team_id, [])),
            transfers=tuple(parts.get("transfers", {}).get(team_id, [])),
            lineup=parts.get("lineups", {}).get(team_id),
            top_ratings=tuple(ratings[:3]),
        )


def _recent_finished(fixtures: list[AfFixture], target: AfFixture, team_id: int) -> list[AfFixture]:
    return [
        item
        for item in fixtures
        if item.is_finished
        and item.date < target.date
        and team_id in {item.home_id, item.away_id}
        and item.fixture_id != target.fixture_id
    ]
