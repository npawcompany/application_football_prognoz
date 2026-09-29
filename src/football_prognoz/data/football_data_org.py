from __future__ import annotations

import re
import threading
import time
from datetime import UTC, date, datetime
from typing import Any

import httpx

from football_prognoz.data import FREE_CODES
from football_prognoz.domain.country import flag_code
from football_prognoz.domain.match import Match, MatchLineup, MatchStatus, Score
from football_prognoz.domain.team import Competition, Person, StandingRow, Team, TeamRoster

API_BASE = "https://api.football-data.org/v4"
# Interactive detail calls (team card, match lineup, day window) give up after this many
# seconds of local rate-limit wait and let the service answer from the SQLite cache.
DETAIL_MAX_WAIT = 15.0


class FootballDataError(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class RateLimiter:
    """At most `max_per_minute` calls in any rolling 60-second window.

    A caller reserves the next free slot under the lock and sleeps *outside* it, so one
    thread waiting for the window does not freeze every other caller. `max_wait` lets
    interactive callers give up (and use the cache) instead of blocking for a minute.
    """

    def __init__(self, max_per_minute: int = 10) -> None:
        self.max_per_minute = max_per_minute
        self._times: list[float] = []
        self._lock = threading.Lock()

    def reserve(self, max_wait: float | None = None) -> float | None:
        """Book a slot; return seconds to sleep before using it, or None if too far."""
        with self._lock:
            now = time.monotonic()
            self._times = [t for t in self._times if t > now - 60.0]
            slot = now
            if len(self._times) >= self.max_per_minute:
                slot = max(now, self._times[-self.max_per_minute] + 60.0 + 0.05)
            delay = slot - now
            if max_wait is not None and delay > max_wait:
                return None
            self._times.append(slot)
            return delay

    def wait(self, max_wait: float | None = None) -> bool:
        delay = self.reserve(max_wait)
        if delay is None:
            return False
        if delay > 0:
            time.sleep(delay)
        return True


def parse_utc(value: str | None) -> datetime:
    if not value:
        return datetime.now(UTC)
    text = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def match_from_api(payload: dict[str, Any], competition_code: str) -> Match:
    home = payload.get("homeTeam") or {}
    away = payload.get("awayTeam") or {}
    score = payload.get("score") or {}
    full_time = score.get("fullTime") or {}
    return Match(
        id=int(payload["id"]),
        competition_code=competition_code,
        utc_date=parse_utc(payload.get("utcDate")),
        status=MatchStatus.from_api(payload.get("status")),
        matchday=payload.get("matchday"),
        home_id=int(home.get("id") or 0),
        home_name=str(home.get("name") or "Unknown"),
        away_id=int(away.get("id") or 0),
        away_name=str(away.get("name") or "Unknown"),
        score=Score(
            home=full_time.get("home"),
            away=full_time.get("away"),
            winner=score.get("winner"),
        ),
        home_crest=home.get("crest"),
        away_crest=away.get("crest"),
        venue=str(payload["venue"]).strip() if payload.get("venue") else None,
    )


def parse_city(address: str | None) -> str | None:
    """Best-effort city from Team.address. v4 has no dedicated city field."""
    if not address:
        return None
    text = re.sub(r"\b[A-Z]{1,2}\d[\dA-Z]?\s*\d[A-Z]{2}\b", " ", address)
    text = re.sub(r"\b\d{4,6}\b", " ", text)
    parts = [chunk.strip(" ,") for chunk in re.split(r"[,/]", text) if chunk.strip()]
    if not parts:
        return None
    if len(parts) >= 2:
        candidate = parts[-1]
    else:
        tokens = [token for token in parts[0].split() if token and not token.isdigit()]
        candidate = tokens[-1] if tokens else ""
    candidate = candidate.strip(" ,.")
    return candidate or None


def _person_ids(raw: object) -> tuple[int, ...]:
    ids: list[int] = []
    if not isinstance(raw, list):
        return ()
    for item in raw:
        if not isinstance(item, dict):
            continue
        person_id = int(item.get("id") or 0)
        if person_id > 0:
            ids.append(person_id)
    return tuple(ids)


def lineup_from_api(payload: dict[str, Any]) -> MatchLineup:
    home = payload.get("homeTeam") or {}
    away = payload.get("awayTeam") or {}
    return MatchLineup(
        home_start=_person_ids(home.get("lineup")),
        home_bench=_person_ids(home.get("bench")),
        away_start=_person_ids(away.get("lineup")),
        away_bench=_person_ids(away.get("bench")),
    )


def _int_or_none(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _person_from_api(payload: dict[str, Any], *, default_role: str) -> Person | None:
    person_id = int(payload.get("id") or 0)
    name = str(payload.get("name") or "").strip()
    if person_id <= 0 or not name:
        return None
    contract = payload.get("contract") or {}
    until = contract.get("until") if isinstance(contract, dict) else None
    role = str(payload.get("role") or default_role)
    return Person(
        id=person_id,
        name=name,
        position=str(payload["position"]) if payload.get("position") else None,
        nationality=str(payload["nationality"]) if payload.get("nationality") else None,
        date_of_birth=str(payload["dateOfBirth"]) if payload.get("dateOfBirth") else None,
        role=role,
        shirt_number=_int_or_none(payload.get("shirtNumber")),
        contract_until=str(until) if until else None,
    )


def roster_from_api(payload: dict[str, Any]) -> TeamRoster:
    team_id = int(payload.get("id") or 0)
    coach_raw = payload.get("coach")
    coach = (
        _person_from_api(coach_raw, default_role="COACH") if isinstance(coach_raw, dict) else None
    )
    players: list[Person] = []
    for raw in payload.get("squad") or []:
        if not isinstance(raw, dict):
            continue
        person = _person_from_api(raw, default_role="PLAYER")
        if person is None:
            continue
        if person.role.upper() == "COACH" and coach is None:
            coach = person
            continue
        players.append(person)
    area = payload.get("area") or {}
    country = str(area["name"]).strip() if isinstance(area, dict) and area.get("name") else None
    iso3 = str(area["code"]).strip() if isinstance(area, dict) and area.get("code") else None
    address = str(payload["address"]).strip() if payload.get("address") else None
    venue = str(payload["venue"]).strip() if payload.get("venue") else None
    return TeamRoster(
        team_id=team_id,
        team_name=str(payload.get("name") or "Unknown"),
        crest=payload.get("crest"),
        coach=coach,
        squad=tuple(players),
        venue=venue,
        city=parse_city(address),
        country=country,
        country_code=flag_code(country, iso3=iso3),
    )


def _date_or_none(value: object) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def competition_from_api(raw: dict[str, Any]) -> Competition:
    """Map a v4 Competition item: id, code, name, emblem, type, area, currentSeason."""
    code = str(raw.get("code") or "")
    area = raw.get("area") or {}
    season = raw.get("currentSeason") or {}
    if not isinstance(area, dict):
        area = {}
    if not isinstance(season, dict):
        season = {}
    return Competition(
        id=int(raw.get("id") or 0),
        code=code,
        name=str(raw.get("name") or code),
        emblem=raw.get("emblem"),
        type=str(raw.get("type") or "").upper() or None,
        area_name=str(area.get("name") or "").strip() or None,
        area_code=str(area.get("code") or "").strip() or None,
        area_flag=area.get("flag") or None,
        season_start=_date_or_none(season.get("startDate")),
        season_end=_date_or_none(season.get("endDate")),
    )


class FootballDataOrgClient:
    def __init__(
        self,
        api_key: str,
        *,
        client: httpx.Client | None = None,
        limiter: RateLimiter | None = None,
        timeout: float = 20.0,
    ) -> None:
        self._api_key = api_key
        self._owns_client = client is None
        self._client = client or httpx.Client(base_url=API_BASE, timeout=timeout)
        self._limiter = limiter or RateLimiter()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        max_wait: float | None = None,
    ) -> dict[str, Any]:
        if not self._api_key.strip():
            raise FootballDataError(
                "Не задан ключ football-data.org. Откройте Настройки.",
                status_code=401,
            )
        if not self._limiter.wait(max_wait):
            raise FootballDataError(
                "Лимит football-data.org (10 запросов в минуту) исчерпан, показан кэш.",
                status_code=429,
            )
        headers = {"X-Auth-Token": self._api_key}
        try:
            response = self._client.get(path, params=params, headers=headers)
        except httpx.HTTPError as exc:
            # Offline / DNS / timeout: callers fall back to the SQLite cache.
            raise FootballDataError(
                f"Нет связи с football-data.org ({type(exc).__name__})."
            ) from exc
        if response.status_code in (400, 401):
            raise FootballDataError(
                f"Ключ football-data.org не принят ({response.status_code}).",
                status_code=response.status_code,
            )
        if response.status_code == 403:
            raise FootballDataError(
                "Ключ отклонён или лига недоступна на текущем тарифе (403).",
                status_code=403,
            )
        if response.status_code == 429:
            raise FootballDataError(
                "Превышен лимит football-data.org (429). Подождите около минуты.",
                status_code=429,
            )
        if response.status_code >= 400:
            raise FootballDataError(
                f"Ошибка football-data.org: HTTP {response.status_code}.",
                status_code=response.status_code,
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise FootballDataError("Неожиданный ответ API (не JSON).") from exc
        if not isinstance(data, dict):
            raise FootballDataError("Неожиданный ответ API.")
        return data

    def ping(self) -> list[Competition]:
        return self.list_competitions()

    def list_competitions(self) -> list[Competition]:
        payload = self._get("/competitions")
        items: list[Competition] = []
        for raw in payload.get("competitions") or []:
            code = str(raw.get("code") or "")
            if code not in FREE_CODES:
                continue
            items.append(competition_from_api(raw))
        items.sort(key=lambda c: c.name)
        return items

    def list_matches(
        self,
        competition_code: str,
        *,
        season: int | None = None,
        status: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[Match]:
        params: dict[str, Any] = {}
        if season is not None:
            params["season"] = season
        if status:
            params["status"] = status
        if date_from:
            params["dateFrom"] = date_from
        if date_to:
            params["dateTo"] = date_to
        payload = self._get(f"/competitions/{competition_code}/matches", params=params)
        matches = [match_from_api(raw, competition_code) for raw in payload.get("matches") or []]
        matches.sort(key=lambda m: m.utc_date)
        return matches

    def list_matches_between(
        self,
        date_from: str,
        date_to: str,
        *,
        max_wait: float | None = DETAIL_MAX_WAIT,
    ) -> list[Match]:
        """GET /v4/matches?dateFrom&dateTo — every accessible competition in one call.

        The competition code comes from each item's `competition.code`. Items of
        competitions outside the free tier are skipped.
        """
        payload = self._get(
            "/matches",
            params={"dateFrom": date_from, "dateTo": date_to},
            max_wait=max_wait,
        )
        matches: list[Match] = []
        for raw in payload.get("matches") or []:
            competition = raw.get("competition") or {}
            code = str(competition.get("code") or "")
            if code not in FREE_CODES:
                continue
            matches.append(match_from_api(raw, code))
        matches.sort(key=lambda m: m.utc_date)
        return matches

    def list_teams(self, competition_code: str) -> list[Team]:
        payload = self._get(f"/competitions/{competition_code}/teams")
        teams: list[Team] = []
        for raw in payload.get("teams") or []:
            team_id = int(raw.get("id") or 0)
            if team_id <= 0:
                continue
            short_name = raw.get("shortName")
            tla = raw.get("tla")
            teams.append(
                Team(
                    id=team_id,
                    name=str(raw.get("name") or "Unknown"),
                    short_name=str(short_name) if short_name else None,
                    tla=str(tla) if tla else None,
                    crest=raw.get("crest"),
                )
            )
        teams.sort(key=lambda t: t.name)
        return teams

    def get_team(self, team_id: int, *, max_wait: float | None = DETAIL_MAX_WAIT) -> TeamRoster:
        payload = self._get(f"/teams/{team_id}", max_wait=max_wait)
        return roster_from_api(payload)

    def get_match(
        self, match_id: int, *, max_wait: float | None = DETAIL_MAX_WAIT
    ) -> tuple[Match, MatchLineup]:
        payload = self._get(f"/matches/{match_id}", max_wait=max_wait)
        competition = payload.get("competition") or {}
        code = str(competition.get("code") or "")
        return match_from_api(payload, code), lineup_from_api(payload)

    def list_standings(self, competition_code: str) -> list[StandingRow]:
        payload = self._get(f"/competitions/{competition_code}/standings")
        rows: list[StandingRow] = []
        seen: set[int] = set()
        # LEAGUE: one TOTAL table (+ HOME/AWAY). Tournaments (WC, EC, CL league phase):
        # one TOTAL table per group — keep every group, not only the first one.
        for table in payload.get("standings") or []:
            if table.get("type") and table.get("type") != "TOTAL":
                continue
            group = str(table.get("group") or "").strip() or None
            for raw in table.get("table") or []:
                team = raw.get("team") or {}
                team_id = int(team.get("id") or 0)
                if team_id in seen:
                    continue
                seen.add(team_id)
                rows.append(
                    StandingRow(
                        team_id=team_id,
                        team_name=str(team.get("name") or "Unknown"),
                        position=int(raw.get("position") or 0),
                        played=int(raw.get("playedGames") or 0),
                        won=int(raw.get("won") or 0),
                        draw=int(raw.get("draw") or 0),
                        lost=int(raw.get("lost") or 0),
                        points=int(raw.get("points") or 0),
                        goals_for=int(raw.get("goalsFor") or 0),
                        goals_against=int(raw.get("goalsAgainst") or 0),
                        group=group,
                    )
                )
        return rows
