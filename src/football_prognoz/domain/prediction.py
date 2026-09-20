from __future__ import annotations

from dataclasses import dataclass

from football_prognoz.domain.match import Match


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


@dataclass(frozen=True)
class Explanation:
    text: str
    model: str


@dataclass(frozen=True)
class MatchForecast:
    match: Match
    probabilities: Probabilities
    features: MatchFeatures
    explanation: Explanation | None
