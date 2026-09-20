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
