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


STATUS_RU: dict[MatchStatus, str] = {
    MatchStatus.SCHEDULED: "Запланирован",
    MatchStatus.TIMED: "Запланирован",
    MatchStatus.IN_PLAY: "Идёт",
    MatchStatus.PAUSED: "Перерыв",
    MatchStatus.FINISHED: "Завершён",
    MatchStatus.POSTPONED: "Перенесён",
    MatchStatus.CANCELLED: "Отменён",
    MatchStatus.SUSPENDED: "Прерван",
    MatchStatus.AWARDED: "Тех. результат",
}
LIVE_STATUSES = frozenset({MatchStatus.IN_PLAY, MatchStatus.PAUSED})


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

    @property
    def has_score(self) -> bool:
        return self.score.home is not None and self.score.away is not None

    @property
    def is_played(self) -> bool:
        """Finished (or awarded) with a known final score."""
        return self.status.is_finished() and self.has_score

    @property
    def score_label(self) -> str | None:
        if not self.has_score:
            return None
        return f"{self.score.home}:{self.score.away}"

    @property
    def result_side(self) -> str | None:
        """'1' home win, 'X' draw, '2' away win; None until the final score is known."""
        if not self.is_played:
            return None
        home, away = self.score.home or 0, self.score.away or 0
        if home > away:
            return "1"
        if away > home:
            return "2"
        return "X"

    @property
    def status_text(self) -> str:
        """Russian status; the score is part of it once known: «Завершён 2:1», «Идёт 1:0»."""
        base = STATUS_RU.get(self.status, "Запланирован")
        if (self.status.is_finished() or self.status in LIVE_STATUSES) and self.has_score:
            return f"{base} {self.score_label}"
        return base


@dataclass(frozen=True)
class MatchLineup:
    """Starting XI and bench person ids from GET /v4/matches/{id}."""

    home_start: tuple[int, ...] = ()
    home_bench: tuple[int, ...] = ()
    away_start: tuple[int, ...] = ()
    away_bench: tuple[int, ...] = ()

    def is_empty(self) -> bool:
        return not (self.home_start or self.home_bench or self.away_start or self.away_bench)
