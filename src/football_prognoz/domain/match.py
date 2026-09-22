from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class MatchStatus(StrEnum):
    SCHEDULED = "SCHEDULED"
    TIMED = "TIMED"
    IN_PLAY = "IN_PLAY"
    PAUSED = "PAUSED"
    FINISHED = "FINISHED"
    POSTPONED = "POSTPONED"
    CANCELLED = "CANCELLED"
    SUSPENDED = "SUSPENDED"
    AWARDED = "AWARDED"

    @classmethod
    def from_api(cls, value: str | None) -> MatchStatus:
        if not value:
            return cls.SCHEDULED
        try:
            return cls(value)
        except ValueError:
            return cls.SCHEDULED

    def is_upcoming(self) -> bool:
        return self in {self.SCHEDULED, self.TIMED}

    def is_finished(self) -> bool:
        return self in {self.FINISHED, self.AWARDED}


@dataclass(frozen=True)
class Score:
    home: int | None
    away: int | None
    winner: str | None = None


@dataclass(frozen=True)
class Match:
    id: int
    competition_code: str
    utc_date: datetime
    status: MatchStatus
    matchday: int | None
    home_id: int
    home_name: str
    away_id: int
    away_name: str
    score: Score
    home_crest: str | None = None
    away_crest: str | None = None
    venue: str | None = None

    @property
    def label(self) -> str:
        return f"{self.home_name} — {self.away_name}"


@dataclass(frozen=True)
class MatchLineup:
    """Starting XI and bench person ids from GET /v4/matches/{id}."""

    home_start: tuple[int, ...] = ()
    home_bench: tuple[int, ...] = ()
    away_start: tuple[int, ...] = ()
    away_bench: tuple[int, ...] = ()

    def is_empty(self) -> bool:
        return not (
            self.home_start or self.home_bench or self.away_start or self.away_bench
        )
