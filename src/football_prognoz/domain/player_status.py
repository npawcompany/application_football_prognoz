"""Player availability facts from API-Football (optional source)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Absence:
    """Injury or suspension for one fixture (`GET /injuries`)."""

    player_id: int
    player_name: str
    kind: str  # "Missing Fixture" | "Questionable"
    reason: str  # e.g. "Knee Injury", "Suspended"
    expected_return: str | None = None  # from /sidelined `end`, ISO date
    key_player: bool = False  # among top-rated players of the last match

    @property
    def is_suspension(self) -> bool:
        return "suspend" in self.reason.lower()

    @property
    def is_certain(self) -> bool:
        return self.kind.lower().startswith("missing")


@dataclass(frozen=True)
class CardEvent:
    """Card from `GET /fixtures/events` of a recent finished match."""

    fixture_id: int
    fixture_date: str
    minute: int | None
    player_id: int
    player_name: str
    detail: str  # "Red Card", "Second Yellow card", "Yellow Card"

    @property
    def is_red(self) -> bool:
        text = self.detail.lower()
        return "red" in text or "second yellow" in text


@dataclass(frozen=True)
class Transfer:
    """Transfer touching the team (`GET /transfers?team=`)."""

    player_id: int
    player_name: str
    date: str
    kind: str | None  # "Loan", "Free", "€ 20M", None
    direction: str  # "in" | "out"
    other_team: str


@dataclass(frozen=True)
class LineupPlayer:
    player_id: int
    name: str
    number: int | None = None
    pos: str | None = None


@dataclass(frozen=True)
class FixtureLineup:
    """Confirmed lineup from `GET /fixtures/lineups` (20–40 min before kick-off)."""

    formation: str | None
    start_xi: tuple[LineupPlayer, ...] = ()
    substitutes: tuple[LineupPlayer, ...] = ()
    coach: str | None = None


@dataclass(frozen=True)
class PlayerRating:
    """Per-match rating from `GET /fixtures/players` (string like "7.4" upstream)."""

    player_id: int
    player_name: str
    rating: float
    minutes: int | None = None
    position: str | None = None


@dataclass(frozen=True)
class TeamStatus:
    team_name: str
    af_team_id: int | None = None
    absences: tuple[Absence, ...] = ()
    red_cards: tuple[CardEvent, ...] = ()
    transfers: tuple[Transfer, ...] = ()
    lineup: FixtureLineup | None = None
    top_ratings: tuple[PlayerRating, ...] = ()

    def is_empty(self) -> bool:
        return not (
            self.absences or self.red_cards or self.transfers or self.lineup or self.top_ratings
        )


@dataclass(frozen=True)
class PlayerStatusReport:
    """What API-Football told us about both sides. `notes` explain gaps honestly."""

    home: TeamStatus
    away: TeamStatus
    af_fixture_id: int | None = None
    sources: tuple[str, ...] = ()
    notes: tuple[str, ...] = field(default_factory=tuple)

    def has_data(self) -> bool:
        return not (self.home.is_empty() and self.away.is_empty())
