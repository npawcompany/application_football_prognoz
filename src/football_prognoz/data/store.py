from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from football_prognoz.domain.match import Match, MatchLineup, MatchStatus, Score
from football_prognoz.domain.team import Competition, Person, StandingRow, Team, TeamRoster

TTL_SCHEDULED_HOURS = 6
TTL_FINISHED_HOURS = 24
TTL_LLM_HOURS = 12


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _parse_dt(value: str | None) -> datetime:
    if not value:
        return datetime.fromtimestamp(0, tz=UTC)
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
                CREATE TABLE IF NOT EXISTS team_rosters (
                    team_id INTEGER PRIMARY KEY,
                    team_name TEXT NOT NULL,
                    crest TEXT,
                    coach_json TEXT,
                    squad_json TEXT NOT NULL,
                    fetched_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS match_lineups (
                    match_id INTEGER PRIMARY KEY,
                    home_start TEXT NOT NULL,
                    home_bench TEXT NOT NULL,
                    away_start TEXT NOT NULL,
                    away_bench TEXT NOT NULL,
                    fetched_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS api_cache (
                    cache_key TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    fetched_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS api_usage (
                    provider TEXT NOT NULL,
                    day TEXT NOT NULL,
                    count INTEGER NOT NULL DEFAULT 0,
                    exhausted INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (provider, day)
                );
                CREATE TABLE IF NOT EXISTS af_team_map (
                    fd_team_id INTEGER PRIMARY KEY,
                    af_team_id INTEGER NOT NULL,
                    fd_name TEXT,
                    af_name TEXT,
                    method TEXT,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS af_fixture_map (
                    fd_match_id INTEGER PRIMARY KEY,
                    af_fixture_id INTEGER NOT NULL,
                    af_league_id INTEGER,
                    season INTEGER,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS llm_cache (
                    cache_key TEXT PRIMARY KEY,
                    model TEXT,
                    payload TEXT NOT NULL,
                    fetched_at TEXT NOT NULL
                );
                """
            )
            self._migrate(conn)

    @staticmethod
    def _migrate(conn: sqlite3.Connection) -> None:
        match_cols = {row[1] for row in conn.execute("PRAGMA table_info(matches)")}
        if "venue" not in match_cols:
            conn.execute("ALTER TABLE matches ADD COLUMN venue TEXT")
        roster_cols = {row[1] for row in conn.execute("PRAGMA table_info(team_rosters)")}
        for column in ("venue", "city", "country", "country_code"):
            if column not in roster_cols:
                conn.execute(f"ALTER TABLE team_rosters ADD COLUMN {column} TEXT")

    def fetched_at(self, cache_key: str) -> datetime | None:
        """Return the cache timestamp even when older than any TTL."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT fetched_at FROM meta WHERE cache_key = ?",
                (cache_key,),
            ).fetchone()
        if row is None:
            return None
        return _parse_dt(row["fetched_at"])

    def is_fresh(self, cache_key: str, ttl_hours: float) -> bool:
        fetched = self.fetched_at(cache_key)
        if fetched is None:
            return False
        return _utcnow() - fetched < timedelta(hours=ttl_hours)

    def clear_all(self) -> None:
        """Delete cached rows; keep tables and indexes.

        API-Football id mappings and the daily request counter survive: the mapping is
        stable, and forgetting the counter would let the app overrun the daily quota.
        """
        with self._connect() as conn:
            conn.executescript(
                """
                DELETE FROM matches;
                DELETE FROM standings;
                DELETE FROM competitions;
                DELETE FROM team_rosters;
                DELETE FROM match_lineups;
                DELETE FROM meta;
                DELETE FROM api_cache;
                DELETE FROM llm_cache;
                """
            )

    # --- raw API payload cache (API-Football) -------------------------------------

    def get_api_payload(self, cache_key: str, ttl_hours: float) -> object | None:
        """Return a cached JSON payload if younger than `ttl_hours`, else None."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload, fetched_at FROM api_cache WHERE cache_key = ?",
                (cache_key,),
            ).fetchone()
        if row is None:
            return None
        if _utcnow() - _parse_dt(row["fetched_at"]) >= timedelta(hours=ttl_hours):
            return None
        return json.loads(row["payload"])

    def put_api_payload(self, cache_key: str, payload: object) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO api_cache (cache_key, payload, fetched_at) VALUES (?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    payload = excluded.payload, fetched_at = excluded.fetched_at
                """,
                (cache_key, json.dumps(payload, ensure_ascii=False), _utcnow().isoformat()),
            )

    # --- daily request budget ------------------------------------------------------

    @staticmethod
    def _today() -> str:
        return _utcnow().date().isoformat()

    def api_calls_today(self, provider: str) -> tuple[int, bool]:
        """(requests counted today, day closed by the provider) for a UTC day."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT count, exhausted FROM api_usage WHERE provider = ? AND day = ?",
                (provider, self._today()),
            ).fetchone()
        if row is None:
            return 0, False
        return int(row["count"]), bool(row["exhausted"])

    def consume_api_call(self, provider: str, daily_limit: int) -> bool:
        """Atomically count one request if the daily limit allows it."""
        day = self._today()
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO api_usage (provider, day, count, exhausted) "
                "VALUES (?, ?, 0, 0)",
                (provider, day),
            )
            cursor = conn.execute(
                """
                UPDATE api_usage SET count = count + 1
                WHERE provider = ? AND day = ? AND exhausted = 0 AND count < ?
                """,
                (provider, day, daily_limit),
            )
            return cursor.rowcount == 1

    def mark_api_exhausted(self, provider: str) -> None:
        day = self._today()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO api_usage (provider, day, count, exhausted) VALUES (?, ?, 0, 1)
                ON CONFLICT(provider, day) DO UPDATE SET exhausted = 1
                """,
                (provider, day),
            )

    # --- API-Football id mapping ---------------------------------------------------

    def get_af_team(self, fd_team_id: int) -> int | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT af_team_id FROM af_team_map WHERE fd_team_id = ?",
                (fd_team_id,),
            ).fetchone()
        return int(row["af_team_id"]) if row else None

    def upsert_af_team(
        self,
        fd_team_id: int,
        af_team_id: int,
        *,
        fd_name: str,
        af_name: str,
        method: str,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO af_team_map
                    (fd_team_id, af_team_id, fd_name, af_name, method, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(fd_team_id) DO UPDATE SET
                    af_team_id = excluded.af_team_id,
                    fd_name = excluded.fd_name,
                    af_name = excluded.af_name,
                    method = excluded.method,
                    updated_at = excluded.updated_at
                """,
                (fd_team_id, af_team_id, fd_name, af_name, method, _utcnow().isoformat()),
            )

    def get_af_fixture(self, fd_match_id: int) -> int | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT af_fixture_id FROM af_fixture_map WHERE fd_match_id = ?",
                (fd_match_id,),
            ).fetchone()
        return int(row["af_fixture_id"]) if row else None

    def upsert_af_fixture(
        self,
        fd_match_id: int,
        af_fixture_id: int,
        *,
        af_league_id: int,
        season: int,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO af_fixture_map
                    (fd_match_id, af_fixture_id, af_league_id, season, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(fd_match_id) DO UPDATE SET
                    af_fixture_id = excluded.af_fixture_id,
                    af_league_id = excluded.af_league_id,
                    season = excluded.season,
                    updated_at = excluded.updated_at
                """,
                (fd_match_id, af_fixture_id, af_league_id, season, _utcnow().isoformat()),
            )

    # --- LLM answers ---------------------------------------------------------------

    def get_llm(self, cache_key: str, ttl_hours: float = TTL_LLM_HOURS) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload, fetched_at FROM llm_cache WHERE cache_key = ?",
                (cache_key,),
            ).fetchone()
        if row is None:
            return None
        if _utcnow() - _parse_dt(row["fetched_at"]) >= timedelta(hours=ttl_hours):
            return None
        data = json.loads(row["payload"])
        return data if isinstance(data, dict) else None

    def put_llm(self, cache_key: str, payload: dict, *, model: str | None = None) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO llm_cache (cache_key, model, payload, fetched_at) VALUES (?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    model = excluded.model,
                    payload = excluded.payload,
                    fetched_at = excluded.fetched_at
                """,
                (
                    cache_key,
                    model,
                    json.dumps(payload, ensure_ascii=False),
                    _utcnow().isoformat(),
                ),
            )

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
                        home_goals, away_goals, winner, home_crest, away_crest, venue, fetched_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        venue = excluded.venue,
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
                        match.venue,
                        now,
                    ),
                )

    def list_matches(self, competition_code: str | None = None) -> list[Match]:
        query = """
            SELECT id, competition_code, utc_date, status, matchday,
                   home_id, home_name, away_id, away_name,
                   home_goals, away_goals, winner, home_crest, away_crest, venue
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
                       home_goals, away_goals, winner, home_crest, away_crest, venue
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

    def list_cached_teams(self) -> list[Team]:
        """Distinct teams from cached matches and standings. No HTTP."""
        query = """
            SELECT id, MIN(name) AS name, MAX(crest) AS crest
            FROM (
                SELECT home_id AS id, home_name AS name, home_crest AS crest FROM matches
                UNION ALL
                SELECT away_id AS id, away_name AS name, away_crest AS crest FROM matches
                UNION ALL
                SELECT team_id AS id, team_name AS name, NULL AS crest FROM standings
            )
            WHERE id IS NOT NULL AND TRIM(COALESCE(name, '')) != ''
            GROUP BY id
            ORDER BY name COLLATE NOCASE
        """
        with self._connect() as conn:
            rows = conn.execute(query).fetchall()
        return [Team(id=int(row["id"]), name=str(row["name"]), crest=row["crest"]) for row in rows]

    def upsert_roster(self, roster: TeamRoster) -> None:
        now = _utcnow().isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO team_rosters (
                    team_id, team_name, crest, coach_json, squad_json,
                    venue, city, country, country_code, fetched_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(team_id) DO UPDATE SET
                    team_name = excluded.team_name,
                    crest = excluded.crest,
                    coach_json = excluded.coach_json,
                    squad_json = excluded.squad_json,
                    venue = excluded.venue,
                    city = excluded.city,
                    country = excluded.country,
                    country_code = excluded.country_code,
                    fetched_at = excluded.fetched_at
                """,
                (
                    roster.team_id,
                    roster.team_name,
                    roster.crest,
                    json.dumps(_person_to_json(roster.coach), ensure_ascii=False),
                    json.dumps(
                        [_person_to_json(person) for person in roster.squad],
                        ensure_ascii=False,
                    ),
                    roster.venue,
                    roster.city,
                    roster.country,
                    roster.country_code,
                    now,
                ),
            )
        self.mark_fetched(f"team:{roster.team_id}")

    def get_roster(self, team_id: int) -> TeamRoster | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT team_id, team_name, crest, coach_json, squad_json,
                       venue, city, country, country_code
                FROM team_rosters WHERE team_id = ?
                """,
                (team_id,),
            ).fetchone()
        if row is None:
            return None
        coach_raw = json.loads(row["coach_json"] or "null")
        squad_raw = json.loads(row["squad_json"] or "[]")
        return TeamRoster(
            team_id=int(row["team_id"]),
            team_name=str(row["team_name"]),
            crest=row["crest"],
            coach=_person_from_json(coach_raw),
            squad=tuple(
                person
                for person in (_person_from_json(item) for item in squad_raw)
                if person is not None
            ),
            venue=row["venue"] if "venue" in row.keys() else None,
            city=row["city"] if "city" in row.keys() else None,
            country=row["country"] if "country" in row.keys() else None,
            country_code=row["country_code"] if "country_code" in row.keys() else None,
        )

    def upsert_lineup(self, match_id: int, lineup: MatchLineup) -> None:
        now = _utcnow().isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO match_lineups (
                    match_id, home_start, home_bench, away_start, away_bench, fetched_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(match_id) DO UPDATE SET
                    home_start = excluded.home_start,
                    home_bench = excluded.home_bench,
                    away_start = excluded.away_start,
                    away_bench = excluded.away_bench,
                    fetched_at = excluded.fetched_at
                """,
                (
                    match_id,
                    json.dumps(list(lineup.home_start)),
                    json.dumps(list(lineup.home_bench)),
                    json.dumps(list(lineup.away_start)),
                    json.dumps(list(lineup.away_bench)),
                    now,
                ),
            )
        self.mark_fetched(f"match:{match_id}")

    def get_lineup(self, match_id: int) -> MatchLineup | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT home_start, home_bench, away_start, away_bench
                FROM match_lineups WHERE match_id = ?
                """,
                (match_id,),
            ).fetchone()
        if row is None:
            return None
        return MatchLineup(
            home_start=tuple(json.loads(row["home_start"] or "[]")),
            home_bench=tuple(json.loads(row["home_bench"] or "[]")),
            away_start=tuple(json.loads(row["away_start"] or "[]")),
            away_bench=tuple(json.loads(row["away_bench"] or "[]")),
        )

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
            venue=row["venue"] if "venue" in row.keys() else None,
        )


def _person_to_json(person: Person | None) -> dict[str, object] | None:
    if person is None:
        return None
    return {
        "id": person.id,
        "name": person.name,
        "position": person.position,
        "nationality": person.nationality,
        "date_of_birth": person.date_of_birth,
        "role": person.role,
        "shirt_number": person.shirt_number,
        "contract_until": person.contract_until,
    }


def _person_from_json(payload: object) -> Person | None:
    if not isinstance(payload, dict):
        return None
    person_id = int(payload.get("id") or 0)
    name = str(payload.get("name") or "").strip()
    if person_id <= 0 or not name:
        return None
    shirt = payload.get("shirt_number")
    return Person(
        id=person_id,
        name=name,
        position=payload.get("position"),
        nationality=payload.get("nationality"),
        date_of_birth=payload.get("date_of_birth"),
        role=str(payload.get("role") or "PLAYER"),
        shirt_number=int(shirt) if shirt else None,
        contract_until=payload.get("contract_until"),
    )


def ttl_hours_for_status(status: MatchStatus) -> float:
    if status.is_upcoming():
        return TTL_SCHEDULED_HOURS
    return TTL_FINISHED_HOURS


class SQLiteExplanationCache:
    """ExplanationCache backed by `llm_cache` (structural protocol, no ai import)."""

    def __init__(self, store: SQLiteStore, ttl_hours: float = TTL_LLM_HOURS) -> None:
        self._store = store
        self._ttl = ttl_hours

    def get(self, key: str) -> dict | None:
        return self._store.get_llm(key, self._ttl)

    def put(self, key: str, value: dict) -> None:
        model = value.get("model") if isinstance(value, dict) else None
        self._store.put_llm(key, value, model=str(model) if model else None)
