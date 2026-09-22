from __future__ import annotations

from dataclasses import dataclass


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


@dataclass(frozen=True)
class Competition:
    id: int
    code: str
    name: str
    emblem: str | None = None


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
