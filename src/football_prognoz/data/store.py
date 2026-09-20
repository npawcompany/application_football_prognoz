from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from football_prognoz.domain.match import Match, MatchStatus, Score
from football_prognoz.domain.team import Competition, StandingRow

TTL_SCHEDULED_HOURS = 6
TTL_FINISHED_HOURS = 24


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(value: str | None) -> datetime:
    if not value:
        return datetime.fromtimestamp(0, tz=timezone.utc)
    return datetime.fromisoformat(value)


class SQLiteStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS meta (
                    cache_key TEXT PRIMARY KEY,
                    fetched_at TEXT NOT NULL,
                    etag TEXT
                );
                CREATE TABLE IF NOT EXISTS competitions (
                    code TEXT PRIMARY KEY,
                    id INTEGER,
                    name TEXT NOT NULL,
                    emblem TEXT,
                    fetched_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS matches (
                    id INTEGER PRIMARY KEY,
                    competition_code TEXT NOT NULL,
                    utc_date TEXT NOT NULL,
                    status TEXT NOT NULL,
                    matchday INTEGER,
                    home_id INTEGER,
                    home_name TEXT NOT NULL,
                    away_id INTEGER,
                    away_name TEXT NOT NULL,
                    home_goals INTEGER,
                    away_goals INTEGER,
                    winner TEXT,
                    home_crest TEXT,
                    away_crest TEXT,
                    fetched_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_matches_comp_date
                    ON matches (competition_code, utc_date);
                CREATE TABLE IF NOT EXISTS standings (
                    competition_code TEXT NOT NULL,
                    team_id INTEGER NOT NULL,
                    team_name TEXT NOT NULL,
                    position INTEGER,
                    played INTEGER,
                    won INTEGER,
                    draw INTEGER,
                    lost INTEGER,
                    points INTEGER,
                    goals_for INTEGER,
                    goals_against INTEGER,
                    fetched_at TEXT NOT NULL,
                    PRIMARY KEY (competition_code, team_id)
                );
                """
            )

    def is_fresh(self, cache_key: str, ttl_hours: float) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT fetched_at FROM meta WHERE cache_key = ?",
                (cache_key,),
            ).fetchone()
        if row is None:
            return False
        fetched = _parse_dt(row["fetched_at"])
        return _utcnow() - fetched < timedelta(hours=ttl_hours)

    def mark_fetched(self, cache_key: str, etag: str | None = None) -> None:
        now = _utcnow().isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO meta (cache_key, fetched_at, etag)
                VALUES (?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    fetched_at = excluded.fetched_at,
                    etag = excluded.etag
                """,
                (cache_key, now, etag),
            )

    def upsert_competitions(self, items: list[Competition]) -> None:
        now = _utcnow().isoformat()
        with self._connect() as conn:
            for item in items:
                conn.execute(
                    """
                    INSERT INTO competitions (code, id, name, emblem, fetched_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(code) DO UPDATE SET
                        id = excluded.id,
                        name = excluded.name,
                        emblem = excluded.emblem,
                        fetched_at = excluded.fetched_at
                    """,
                    (item.code, item.id, item.name, item.emblem, now),
                )
        self.mark_fetched("competitions")

    def list_competitions(self) -> list[Competition]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, code, name, emblem FROM competitions ORDER BY name"
            ).fetchall()
        return [
            Competition(id=row["id"], code=row["code"], name=row["name"], emblem=row["emblem"])
            for row in rows
        ]

    def upsert_matches(self, matches: list[Match]) -> None:
        now = _utcnow().isoformat()
        with self._connect() as conn:
            for match in matches:
                conn.execute(
                    """
                    INSERT INTO matches (
                        id, competition_code, utc_date, status, matchday,
                        home_id, home_name, away_id, away_name,
                        home_goals, away_goals, winner, home_crest, away_crest, fetched_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        competition_code = excluded.competition_code,
                        utc_date = excluded.utc_date,
                        status = excluded.status,
                        matchday = excluded.matchday,
                        home_id = excluded.home_id,
                        home_name = excluded.home_name,
                        away_id = excluded.away_id,
                        away_name = excluded.away_name,
                        home_goals = excluded.home_goals,
                        away_goals = excluded.away_goals,
                        winner = excluded.winner,
                        home_crest = excluded.home_crest,
                        away_crest = excluded.away_crest,
                        fetched_at = excluded.fetched_at
                    """,
                    (
                        match.id,
                        match.competition_code,
                        match.utc_date.isoformat(),
                        match.status.value,
                        match.matchday,
                        match.home_id,
                        match.home_name,
                        match.away_id,
                        match.away_name,
                        match.score.home,
                        match.score.away,
                        match.score.winner,
                        match.home_crest,
                        match.away_crest,
                        now,
                    ),
                )

    def list_matches(self, competition_code: str | None = None) -> list[Match]:
        query = """
            SELECT id, competition_code, utc_date, status, matchday,
                   home_id, home_name, away_id, away_name,
                   home_goals, away_goals, winner, home_crest, away_crest
            FROM matches
        """
        params: tuple[object, ...] = ()
        if competition_code:
            query += " WHERE competition_code = ?"
            params = (competition_code,)
        query += " ORDER BY utc_date"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._match_from_row(row) for row in rows]

    def get_match(self, match_id: int) -> Match | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, competition_code, utc_date, status, matchday,
                       home_id, home_name, away_id, away_name,
                       home_goals, away_goals, winner, home_crest, away_crest
                FROM matches WHERE id = ?
                """,
                (match_id,),
            ).fetchone()
        return self._match_from_row(row) if row else None

    def upsert_standings(self, competition_code: str, rows: list[StandingRow]) -> None:
        now = _utcnow().isoformat()
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM standings WHERE competition_code = ?",
                (competition_code,),
            )
            for row in rows:
                conn.execute(
                    """
                    INSERT INTO standings (
                        competition_code, team_id, team_name, position, played,
                        won, draw, lost, points, goals_for, goals_against, fetched_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        competition_code,
                        row.team_id,
                        row.team_name,
                        row.position,
                        row.played,
                        row.won,
                        row.draw,
                        row.lost,
                        row.points,
                        row.goals_for,
                        row.goals_against,
                        now,
                    ),
                )
        self.mark_fetched(f"standings:{competition_code}")

    def list_standings(self, competition_code: str) -> list[StandingRow]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT team_id, team_name, position, played, won, draw, lost,
                       points, goals_for, goals_against
                FROM standings
                WHERE competition_code = ?
                ORDER BY position
                """,
                (competition_code,),
            ).fetchall()
        return [
            StandingRow(
                team_id=row["team_id"],
                team_name=row["team_name"],
                position=row["position"],
                played=row["played"],
                won=row["won"],
                draw=row["draw"],
                lost=row["lost"],
                points=row["points"],
                goals_for=row["goals_for"],
                goals_against=row["goals_against"],
            )
            for row in rows
        ]

    def dump_json(self, cache_key: str, payload: object) -> None:
        """Optional debug helper; not used by the UI."""
        _ = json.dumps(payload)
        self.mark_fetched(cache_key)

    @staticmethod
    def _match_from_row(row: sqlite3.Row) -> Match:
        return Match(
            id=row["id"],
            competition_code=row["competition_code"],
            utc_date=_parse_dt(row["utc_date"]),
            status=MatchStatus.from_api(row["status"]),
            matchday=row["matchday"],
            home_id=row["home_id"],
            home_name=row["home_name"],
            away_id=row["away_id"],
            away_name=row["away_name"],
            score=Score(
                home=row["home_goals"],
                away=row["away_goals"],
                winner=row["winner"],
            ),
            home_crest=row["home_crest"],
            away_crest=row["away_crest"],
        )


def ttl_hours_for_status(status: MatchStatus) -> float:
    if status.is_upcoming():
        return TTL_SCHEDULED_HOURS
    return TTL_FINISHED_HOURS
