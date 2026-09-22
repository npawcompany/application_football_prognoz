from __future__ import annotations

import re
import threading
import time
from datetime import UTC, datetime
from typing import Any

import httpx

from football_prognoz.data import FREE_CODES
from football_prognoz.domain.country import flag_code
from football_prognoz.domain.match import Match, MatchLineup, MatchStatus, Score
from football_prognoz.domain.team import Competition, Person, StandingRow, Team, TeamRoster

API_BASE = "https://api.football-data.org/v4"


class FootballDataError(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class RateLimiter:
    """At most `max_per_minute` calls in any rolling 60-second window."""

    def __init__(self, max_per_minute: int = 10) -> None:
        self.max_per_minute = max_per_minute
        self._times: list[float] = []
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            self._times = [t for t in self._times if now - t < 60.0]
            if len(self._times) >= self.max_per_minute:
                sleep_for = 60.0 - (now - self._times[0]) + 0.05
                if sleep_for > 0:
                    time.sleep(sleep_for)
            self._times.append(time.monotonic())


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
        _person_from_api(coach_raw, default_role="COACH")
        if isinstance(coach_raw, dict)
        else None
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

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self._api_key.strip():
            raise FootballDataError(
                "Не задан ключ football-data.org. Откройте Настройки.",
                status_code=401,
            )
        self._limiter.wait()
        headers = {"X-Auth-Token": self._api_key}
        response = self._client.get(path, params=params, headers=headers)
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
        data = response.json()
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
            items.append(
                Competition(
                    id=int(raw.get("id") or 0),
                    code=code,
                    name=str(raw.get("name") or code),
                    emblem=raw.get("emblem"),
                )
            )
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
        matches = [
            match_from_api(raw, competition_code) for raw in payload.get("matches") or []
        ]
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

    def get_team(self, team_id: int) -> TeamRoster:
        payload = self._get(f"/teams/{team_id}")
        return roster_from_api(payload)

    def get_match(self, match_id: int) -> tuple[Match, MatchLineup]:
        payload = self._get(f"/matches/{match_id}")
        competition = payload.get("competition") or {}
        code = str(competition.get("code") or "")
        return match_from_api(payload, code), lineup_from_api(payload)

    def list_standings(self, competition_code: str) -> list[StandingRow]:
        payload = self._get(f"/competitions/{competition_code}/standings")
        rows: list[StandingRow] = []
        for table in payload.get("standings") or []:
            if table.get("type") and table.get("type") != "TOTAL":
                continue
            for raw in table.get("table") or []:
                team = raw.get("team") or {}
                rows.append(
                    StandingRow(
                        team_id=int(team.get("id") or 0),
                        team_name=str(team.get("name") or "Unknown"),
                        position=int(raw.get("position") or 0),
                        played=int(raw.get("playedGames") or 0),
                        won=int(raw.get("won") or 0),
                        draw=int(raw.get("draw") or 0),
                        lost=int(raw.get("lost") or 0),
                        points=int(raw.get("points") or 0),
                        goals_for=int(raw.get("goalsFor") or 0),
                        goals_against=int(raw.get("goalsAgainst") or 0),
                    )
                )
            break
        return rows
