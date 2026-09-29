from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from football_prognoz.domain.history import HistoricalHint
from football_prognoz.domain.match import Match, MatchLineup
from football_prognoz.domain.news import NewsReport
from football_prognoz.domain.player_status import PlayerStatusReport
from football_prognoz.domain.team import StandingRow, TeamRoster

CONFIDENCE_LEVELS = ("low", "medium", "high")
CONFIDENCE_LABELS = {"low": "низкая", "medium": "средняя", "high": "высокая"}


@dataclass(frozen=True)
class Probabilities:
    home: float
    draw: float
    away: float

    def normalized(self) -> Probabilities:
        total = self.home + self.draw + self.away
        if total <= 0:
            return Probabilities(1 / 3, 1 / 3, 1 / 3)
        return Probabilities(self.home / total, self.draw / total, self.away / total)

    @property
    def favorite_label(self) -> str:
        best = max(self.home, self.draw, self.away)
        if best == self.home:
            return "1"
        if best == self.away:
            return "2"
        return "X"


@dataclass(frozen=True)
class Scoreline:
    """Most likely exact score from historical goals only (no Elo / injuries)."""

    home_goals: int
    away_goals: int
    probability: float
    expected_home: float
    expected_away: float

    @property
    def label(self) -> str:
        return f"{self.home_goals}:{self.away_goals}"

    @property
    def winner_side(self) -> str | None:
        if self.home_goals > self.away_goals:
            return "home"
        if self.away_goals > self.home_goals:
            return "away"
        return None


@dataclass(frozen=True)
class MatchFeatures:
    home_form: str
    away_form: str
    home_elo: float
    away_elo: float
    h2h_summary: str
    home_position: int | None
    away_position: int | None
    home_recent_goals_for: float
    home_recent_goals_against: float
    away_recent_goals_for: float
    away_recent_goals_against: float
    sample_matches: int
    h2h_matches: tuple[Match, ...] = ()
    home_standing: StandingRow | None = None
    away_standing: StandingRow | None = None


@dataclass(frozen=True)
class Factor:
    """One indirect factor from the LLM analysis and how it shifts the picture."""

    factor: str
    effect: str
    direction: str = "neutral"  # up | down | neutral, for the side it belongs to


@dataclass(frozen=True)
class FactsPackage:
    """Structured facts handed to the LLM. Built by services, never by the model."""

    data: dict[str, Any]
    sources: tuple[str, ...] = ()


@dataclass(frozen=True)
class Explanation:
    """LLM analysis. `text` is the short summary; probabilities stay untouched."""

    text: str
    model: str
    home_factors: tuple[Factor, ...] = ()
    away_factors: tuple[Factor, ...] = ()
    verdict: str = ""
    confidence: str = ""  # one of CONFIDENCE_LEVELS or "" for legacy plain text
    confidence_reason: str = ""
    sources: tuple[str, ...] = ()

    @property
    def confidence_label(self) -> str:
        return CONFIDENCE_LABELS.get(self.confidence, "")


@dataclass(frozen=True)
class MatchForecast:
    match: Match
    probabilities: Probabilities
    features: MatchFeatures
    explanation: Explanation | None
    scoreline: Scoreline
    home_roster: TeamRoster | None = None
    away_roster: TeamRoster | None = None
    lineup: MatchLineup | None = None
    player_status: PlayerStatusReport | None = None
    news: NewsReport | None = None
    history_hint: HistoricalHint | None = None
    explanation_error: str | None = None
    sources: tuple[str, ...] = field(default_factory=tuple)
