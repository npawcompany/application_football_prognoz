"""API-Football v3 client (https://v3.football.api-sports.io).

Documented in docs/DATA_SOURCES.md. Responses are NOT verified live yet (no key);
field names follow the official OpenAPI spec v3.9.3. The client never runs without
a key, counts every request against a daily budget, respects a per-minute limiter and
backs off on 429.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

import httpx

from football_prognoz.data.football_data_org import RateLimiter, parse_utc
from football_prognoz.domain.player_status import (
    Absence,
    CardEvent,
    FixtureLineup,
    LineupPlayer,
    PlayerRating,
    Transfer,
)

log = logging.getLogger(__name__)

API_FOOTBALL_BASE = "https://v3.football.api-sports.io"
PROVIDER = "api_football"
FREE_DAILY_LIMIT = 100
DEFAULT_DAILY_BUDGET = 90  # headroom under the free 100/day
DEFAULT_PER_MINUTE = 10  # per-minute limit is not in the spec; stay conservative
MAX_429_RETRIES = 2

# football-data.org competition code -> API-Football league id.
# PL 39, CL 2, FL1 61 appear in the official spec examples; the rest are well-known ids
# that still need a one-time check via GET /leagues?id= once a key exists.
FD_TO_AF_LEAGUE: dict[str, int] = {
    "PL": 39,
    "PD": 140,
    "SA": 135,
    "BL1": 78,
    "FL1": 61,
    "DED": 88,
    "PPL": 94,
    "ELC": 40,
    "BSA": 71,
    "CL": 2,
    "WC": 1,
    "EC": 4,
}

# Competitions whose season is a calendar year rather than autumn–spring.
_CALENDAR_YEAR_CODES = frozenset({"BSA", "WC", "EC"})

FINISHED_STATUSES = frozenset({"FT", "AET", "PEN", "AWD", "WO"})


def af_season(competition_code: str, when: datetime) -> int:
    """API-Football `season` = start year; calendar-year tournaments use the match year."""
    if competition_code.upper() in _CALENDAR_YEAR_CODES:
        return when.year
    return when.year if when.month >= 7 else when.year - 1


class ApiFootballError(Exception):
    """kind: auth | plan | quota | rate_limit | http | network | payload | no_key."""

    def __init__(self, message: str, *, kind: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.kind = kind
        self.status_code = status_code


class DailyBudget(Protocol):
    def try_consume(self) -> bool: ...

    def mark_exhausted(self) -> None: ...


class StoreBudget:
    """Daily budget persisted in SQLite (`api_usage`), shared by every client instance."""

    def __init__(self, store: Any, limit: int = DEFAULT_DAILY_BUDGET) -> None:
        self._store = store
        self.limit = limit

    def try_consume(self) -> bool:
        return bool(self._store.consume_api_call(PROVIDER, self.limit))

    def mark_exhausted(self) -> None:
        self._store.mark_api_exhausted(PROVIDER)

    def remaining(self) -> int:
        used, exhausted = self._store.api_calls_today(PROVIDER)
        return 0 if exhausted else max(0, self.limit - used)


@dataclass(frozen=True)
class AfFixture:
    """Subset of `GET /fixtures` response items used for matching and history."""

    fixture_id: int
    date: datetime
    status_short: str
    league_id: int
    season: int
    home_id: int
    home_name: str
    away_id: int
    away_name: str
    home_goals: int | None = None
    away_goals: int | None = None

    @property
    def is_finished(self) -> bool:
        return self.status_short in FINISHED_STATUSES


def _classify_errors(errors: Any) -> tuple[str, str] | None:
    """`errors` is [] when fine, otherwise a dict (or a non-empty list)."""
    if not errors:
        return None
    if isinstance(errors, dict):
        keys = {str(k).lower() for k in errors}
        text = "; ".join(str(v) for v in errors.values())[:300]
    else:
        keys = set()
        text = "; ".join(str(v) for v in errors)[:300]
    lowered = text.lower()
    if "token" in keys or "application key" in lowered or "api key" in lowered:
        return "auth", "API-Football отклонил ключ. Проверьте API_FOOTBALL_KEY."
    if "plan" in keys or "free plan" in lowered or "do not have access" in lowered:
        return "plan", "Тариф API-Football не даёт доступа к этому сезону."
    if "requests" in keys or "request limit" in lowered:
        return "quota", "Суточный лимит API-Football исчерпан."
    if "ratelimit" in keys or "too many requests" in lowered:
        return "rate_limit", "Превышен минутный лимит API-Football."
    return "payload", f"API-Football вернул ошибку: {text}"


def _int(value: object) -> int | None:
    try:
        return int(value) if value is not None and value != "" else None
    except (TypeError, ValueError):
        return None


class ApiFootballClient:
    def __init__(
        self,
        api_key: str,
        *,
        client: httpx.Client | None = None,
        limiter: RateLimiter | None = None,
        budget: DailyBudget | None = None,
        sleep: Callable[[float], None] = time.sleep,
        timeout: float = 20.0,
    ) -> None:
        self._api_key = api_key.strip()
        self._owns_client = client is None
        self._client = client or httpx.Client(base_url=API_FOOTBALL_BASE, timeout=timeout)
        self._limiter = limiter or RateLimiter(DEFAULT_PER_MINUTE)
        self._budget = budget
        self._sleep = sleep
        self.daily_remaining: int | None = None
        self.minute_remaining: int | None = None

    @property
    def enabled(self) -> bool:
        return bool(self._api_key)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    # --- transport -------------------------------------------------------------

    def _read_headers(self, response: httpx.Response) -> None:
        daily = _int(response.headers.get("x-ratelimit-requests-remaining"))
        minute = _int(response.headers.get("x-ratelimit-remaining"))
        if daily is not None:
            self.daily_remaining = daily
            if daily <= 0 and self._budget is not None:
                self._budget.mark_exhausted()
        if minute is not None:
            self.minute_remaining = minute

    def get(
        self, path: str, params: dict[str, Any] | None = None, *, count: bool = True
    ) -> list[Any]:
        """GET an endpoint and return the `response` list/object. Raises ApiFootballError.

        `count=False` only for /status, which the provider does not bill.
        """
        if not self._api_key:
            raise ApiFootballError("Не задан API_FOOTBALL_KEY.", kind="no_key")
        attempt = 0
        while True:
            if count and self._budget is not None and not self._budget.try_consume():
                raise ApiFootballError(
                    "Суточный бюджет запросов API-Football исчерпан.", kind="quota"
                )
            self._limiter.wait()
            try:
                response = self._client.get(
                    path, params=params, headers={"x-apisports-key": self._api_key}
                )
            except httpx.HTTPError as exc:
                raise ApiFootballError("Нет соединения с API-Football.", kind="network") from exc
            self._read_headers(response)
            if response.status_code == 429:
                if attempt >= MAX_429_RETRIES:
                    raise ApiFootballError(
                        "API-Football: слишком много запросов (429).",
                        kind="rate_limit",
                        status_code=429,
                    )
                retry_after = _int(response.headers.get("retry-after"))
                delay = float(retry_after) if retry_after else 2.0 * (2**attempt)
                log.warning("API-Football 429; backing off %.1fs", delay)
                self._sleep(min(delay, 60.0))
                attempt += 1
                continue
            break
        if response.status_code in {401, 403}:
            raise ApiFootballError(
                "API-Football отклонил ключ. Проверьте API_FOOTBALL_KEY.",
                kind="auth",
                status_code=response.status_code,
            )
        if response.status_code == 204:
            return []
        if response.status_code >= 400:
            raise ApiFootballError(
                f"Ошибка API-Football: HTTP {response.status_code}.",
                kind="http",
                status_code=response.status_code,
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise ApiFootballError("API-Football вернул не-JSON.", kind="payload") from exc
        if not isinstance(body, dict):
            raise ApiFootballError("Неожиданный ответ API-Football.", kind="payload")
        problem = _classify_errors(body.get("errors"))
        if problem is not None:
            kind, message = problem
            if kind == "quota" and self._budget is not None:
                self._budget.mark_exhausted()
            raise ApiFootballError(message, kind=kind)
        payload = body.get("response")
        if payload is None:
            return []
        return payload if isinstance(payload, list) else [payload]

    # --- endpoints -------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        """GET /status — does not count against the provider's daily quota."""
        items = self.get("/status", count=False)
        return items[0] if items and isinstance(items[0], dict) else {}

    def season_fixtures(self, league_id: int, season: int) -> list[dict[str, Any]]:
        return [x for x in self.get("/fixtures", {"league": league_id, "season": season}) if x]

    def injuries(self, fixture_id: int) -> list[dict[str, Any]]:
        return self.get("/injuries", {"fixture": fixture_id})

    def sidelined(self, player_ids: list[int]) -> list[dict[str, Any]]:
        ids = "-".join(str(pid) for pid in player_ids[:20])
        return self.get("/sidelined", {"players": ids})

    def fixture_events(self, fixture_id: int) -> list[dict[str, Any]]:
        return self.get("/fixtures/events", {"fixture": fixture_id})

    def transfers(self, team_id: int) -> list[dict[str, Any]]:
        return self.get("/transfers", {"team": team_id})

    def lineups(self, fixture_id: int) -> list[dict[str, Any]]:
        return self.get("/fixtures/lineups", {"fixture": fixture_id})

    def fixture_players(self, fixture_id: int) -> list[dict[str, Any]]:
        return self.get("/fixtures/players", {"fixture": fixture_id})


# --- parsers (pure; operate on the `response` list) ------------------------------


def parse_fixtures(items: list[Any]) -> list[AfFixture]:
    out: list[AfFixture] = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        fixture = raw.get("fixture") or {}
        league = raw.get("league") or {}
        teams = raw.get("teams") or {}
        home = teams.get("home") or {}
        away = teams.get("away") or {}
        goals = raw.get("goals") or {}
        fixture_id = _int(fixture.get("id"))
        if not fixture_id or not fixture.get("date"):
            continue
        out.append(
            AfFixture(
                fixture_id=fixture_id,
                date=parse_utc(str(fixture["date"])),
                status_short=str((fixture.get("status") or {}).get("short") or ""),
                league_id=_int(league.get("id")) or 0,
                season=_int(league.get("season")) or 0,
                home_id=_int(home.get("id")) or 0,
                home_name=str(home.get("name") or ""),
                away_id=_int(away.get("id")) or 0,
                away_name=str(away.get("name") or ""),
                home_goals=_int(goals.get("home")),
                away_goals=_int(goals.get("away")),
            )
        )
    out.sort(key=lambda item: item.date)
    return out


def parse_injuries(items: list[Any]) -> dict[int, list[Absence]]:
    """Group `GET /injuries` items by API-Football team id."""
    grouped: dict[int, list[Absence]] = {}
    for raw in items:
        if not isinstance(raw, dict):
            continue
        player = raw.get("player") or {}
        team = raw.get("team") or {}
        team_id = _int(team.get("id"))
        player_id = _int(player.get("id")) or 0
        name = str(player.get("name") or "").strip()
        if not team_id or not name:
            continue
        grouped.setdefault(team_id, []).append(
            Absence(
                player_id=player_id,
                player_name=name,
                kind=str(player.get("type") or "Missing Fixture"),
                reason=str(player.get("reason") or "—"),
            )
        )
    return grouped


def parse_sidelined(items: list[Any]) -> dict[int, list[tuple[str, str | None, str | None]]]:
    """`GET /sidelined?players=` -> {player_id: [(type, start, end), ...]}."""
    out: dict[int, list[tuple[str, str | None, str | None]]] = {}
    for raw in items:
        if not isinstance(raw, dict):
            continue
        player_id = _int(raw.get("id"))
        if not player_id:
            continue
        periods = []
        for entry in raw.get("sidelined") or []:
            if isinstance(entry, dict):
                periods.append((str(entry.get("type") or ""), entry.get("start"), entry.get("end")))
        out[player_id] = periods
    return out


def parse_cards(items: list[Any], fixture_id: int, fixture_date: str) -> dict[int, list[CardEvent]]:
    """Cards from `GET /fixtures/events`, grouped by team id."""
    grouped: dict[int, list[CardEvent]] = {}
    for raw in items:
        if not isinstance(raw, dict) or str(raw.get("type") or "").lower() != "card":
            continue
        team_id = _int((raw.get("team") or {}).get("id"))
        player = raw.get("player") or {}
        if not team_id:
            continue
        grouped.setdefault(team_id, []).append(
            CardEvent(
                fixture_id=fixture_id,
                fixture_date=fixture_date,
                minute=_int((raw.get("time") or {}).get("elapsed")),
                player_id=_int(player.get("id")) or 0,
                player_name=str(player.get("name") or "—"),
                detail=str(raw.get("detail") or ""),
            )
        )
    return grouped


def parse_transfers(items: list[Any], team_id: int, *, since: str) -> list[Transfer]:
    """Transfers into/out of `team_id` on or after ISO date `since`, newest first."""
    out: list[Transfer] = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        player = raw.get("player") or {}
        for entry in raw.get("transfers") or []:
            if not isinstance(entry, dict):
                continue
            date = str(entry.get("date") or "")
            if not date or date < since:
                continue
            teams = entry.get("teams") or {}
            team_in = teams.get("in") or {}
            team_out = teams.get("out") or {}
            if _int(team_in.get("id")) == team_id and _int(team_out.get("id")) != team_id:
                direction, other = "in", str(team_out.get("name") or "—")
            elif _int(team_out.get("id")) == team_id and _int(team_in.get("id")) != team_id:
                direction, other = "out", str(team_in.get("name") or "—")
            else:
                continue
            kind = entry.get("type")
            out.append(
                Transfer(
                    player_id=_int(player.get("id")) or 0,
                    player_name=str(player.get("name") or "—"),
                    date=date,
                    kind=str(kind) if kind not in (None, "", "N/A") else None,
                    direction=direction,
                    other_team=other,
                )
            )
    out.sort(key=lambda item: item.date, reverse=True)
    return out


def _lineup_players(raw: Any) -> tuple[LineupPlayer, ...]:
    players: list[LineupPlayer] = []
    for entry in raw or []:
        player = (entry or {}).get("player") if isinstance(entry, dict) else None
        if not isinstance(player, dict) or not player.get("name"):
            continue
        players.append(
            LineupPlayer(
                player_id=_int(player.get("id")) or 0,
                name=str(player["name"]),
                number=_int(player.get("number")),
                pos=str(player["pos"]) if player.get("pos") else None,
            )
        )
    return tuple(players)


def parse_lineups(items: list[Any]) -> dict[int, FixtureLineup]:
    out: dict[int, FixtureLineup] = {}
    for raw in items:
        if not isinstance(raw, dict):
            continue
        team_id = _int((raw.get("team") or {}).get("id"))
        if not team_id:
            continue
        coach = raw.get("coach") or {}
        out[team_id] = FixtureLineup(
            formation=str(raw["formation"]) if raw.get("formation") else None,
            start_xi=_lineup_players(raw.get("startXI")),
            substitutes=_lineup_players(raw.get("substitutes")),
            coach=str(coach["name"]) if isinstance(coach, dict) and coach.get("name") else None,
        )
    return out


def parse_ratings(items: list[Any]) -> dict[int, list[PlayerRating]]:
    """`GET /fixtures/players` -> {team_id: ratings sorted high to low}."""
    out: dict[int, list[PlayerRating]] = {}
    for raw in items:
        if not isinstance(raw, dict):
            continue
        team_id = _int((raw.get("team") or {}).get("id"))
        if not team_id:
            continue
        ratings: list[PlayerRating] = []
        for entry in raw.get("players") or []:
            if not isinstance(entry, dict):
                continue
            player = entry.get("player") or {}
            stats = entry.get("statistics") or [{}]
            games = (stats[0] or {}).get("games") or {} if stats else {}
            try:
                rating = float(games.get("rating"))
            except (TypeError, ValueError):
                continue
            ratings.append(
                PlayerRating(
                    player_id=_int(player.get("id")) or 0,
                    player_name=str(player.get("name") or "—"),
                    rating=rating,
                    minutes=_int(games.get("minutes")),
                    position=str(games["position"]) if games.get("position") else None,
                )
            )
        ratings.sort(key=lambda item: item.rating, reverse=True)
        out[team_id] = ratings
    return out
