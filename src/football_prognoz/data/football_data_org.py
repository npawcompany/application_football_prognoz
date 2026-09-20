from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from football_prognoz.data import FREE_CODES
from football_prognoz.domain.match import Match, MatchStatus, Score
from football_prognoz.domain.team import Competition, StandingRow

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
        return datetime.now(timezone.utc)
    text = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
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
