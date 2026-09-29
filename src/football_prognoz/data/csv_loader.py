from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path

import pandas as pd

from football_prognoz.data import CSV_DIV_TO_CODE
from football_prognoz.domain.match import Match, MatchStatus, Score


def _parse_date(value: str) -> datetime:
    text = str(value).strip()
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    raise ValueError(f"Unsupported CSV date: {value!r}")


def _hash_id(*parts: str) -> int:
    key = "|".join(parts)
    digest = hashlib.md5(key.encode("utf-8")).hexdigest()
    return int(digest[:12], 16) % 2_000_000_000


def _team_id(competition_code: str, name: str) -> int:
    return _hash_id(competition_code, "team", name.strip().lower())


def _match_id(competition_code: str, date: datetime, home: str, away: str) -> int:
    return _hash_id(competition_code, date.date().isoformat(), home, away)


def matches_from_frame(frame: pd.DataFrame) -> list[Match]:
    required = {"HomeTeam", "AwayTeam", "FTHG", "FTAG"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"CSV missing columns: {sorted(missing)}")

    matches: list[Match] = []
    for data in frame.to_dict(orient="records"):
        home = str(data.get("HomeTeam") or "").strip()
        away = str(data.get("AwayTeam") or "").strip()
        if not home or not away:
            continue
        try:
            home_goals = int(data.get("FTHG"))
            away_goals = int(data.get("FTAG"))
        except (TypeError, ValueError):
            continue
        try:
            utc_date = _parse_date(str(data.get("Date")))
        except ValueError:
            continue
        div = str(data.get("Div") or "").strip()
        competition_code = CSV_DIV_TO_CODE.get(div, div or "UNK")
        if home_goals > away_goals:
            winner = "HOME_TEAM"
        elif away_goals > home_goals:
            winner = "AWAY_TEAM"
        else:
            winner = "DRAW"
        matches.append(
            Match(
                id=_match_id(competition_code, utc_date, home, away),
                competition_code=competition_code,
                utc_date=utc_date,
                status=MatchStatus.FINISHED,
                matchday=None,
                home_id=_team_id(competition_code, home),
                home_name=home,
                away_id=_team_id(competition_code, away),
                away_name=away,
                score=Score(home=home_goals, away=away_goals, winner=winner),
            )
        )
    matches.sort(key=lambda m: m.utc_date)
    return matches


def load_csv(path: Path) -> list[Match]:
    frame = pd.read_csv(path)
    return matches_from_frame(frame)


def load_csv_text(text: str) -> list[Match]:
    frame = pd.read_csv(StringIO(text))
    return matches_from_frame(frame)
