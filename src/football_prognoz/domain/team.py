from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Team:
    id: int
    name: str
    short_name: str | None = None
    tla: str | None = None
    crest: str | None = None


@dataclass(frozen=True)
class Person:
    """Player or coach from football-data.org Team / Person resources."""

    id: int
    name: str
    position: str | None = None
    nationality: str | None = None
    date_of_birth: str | None = None
    role: str = "PLAYER"
    shirt_number: int | None = None
    contract_until: str | None = None


@dataclass(frozen=True)
class TeamRoster:
    team_id: int
    team_name: str
    crest: str | None
    coach: Person | None
    squad: tuple[Person, ...]
    venue: str | None = None
    city: str | None = None
    country: str | None = None
    country_code: str | None = None


COMPETITION_TYPES_RU = {
    "LEAGUE": "Лига",
    "CUP": "Кубок",
    "LEAGUE_CUP": "Турнир",
    "PLAYOFFS": "Плей-офф",
}


@dataclass(frozen=True)
class Competition:
    """football-data.org Competition. Metadata fields come from GET /v4/competitions."""

    id: int
    code: str
    name: str
    emblem: str | None = None
    type: str | None = None  # LEAGUE | CUP | LEAGUE_CUP | PLAYOFFS
    area_name: str | None = None
    area_code: str | None = None
    area_flag: str | None = None
    season_start: date | None = None
    season_end: date | None = None

    @property
    def is_cup(self) -> bool:
        return (self.type or "LEAGUE") != "LEAGUE"


@dataclass(frozen=True)
class StandingRow:
    team_id: int
    team_name: str
    position: int
    played: int
    won: int
    draw: int
    lost: int
    points: int
    goals_for: int
    goals_against: int
    group: str | None = None  # GROUP_A… for tournaments, None for a league table
