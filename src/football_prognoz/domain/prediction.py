from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from football_prognoz.domain.history import HistoricalHint
from football_prognoz.domain.markets import CONFIDENCE_LABELS, MarketsTable
from football_prognoz.domain.markets import CONFIDENCE_LEVELS as CONFIDENCE_LEVELS
from football_prognoz.domain.match import Match, MatchLineup
from football_prognoz.domain.news import NewsReport, NewsSummary
from football_prognoz.domain.player_status import PlayerStatusReport
from football_prognoz.domain.team import StandingRow, TeamRoster


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
class MarketComment:
    """LLM text about one row of the markets table; `market` is a `Market.key`."""

    market: str
    comment: str


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
    market_comments: tuple[MarketComment, ...] = ()
    top_markets: tuple[MarketComment, ...] = ()  # the 3 best-grounded markets + why
    risks: tuple[str, ...] = ()
    notice: str = ""  # e.g. which fallback model answered after HTTP 402
    generated_at: datetime | None = None  # when it was generated (saved in SQLite)

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
    markets: MarketsTable | None = None
    # LLM caching policy (services/llm_policy): plan + honest notes for the UI.
    analysis_plan: str = ""
    analysis_note: str = ""  # e.g. «AI-разбор не сохранён, матч уже сыгран.»
    analysis_refresh_error: str = ""  # refresh failed; the saved analysis stays
    news_summary: NewsSummary | None = None
    news_plan: str = ""
    news_note: str = ""  # «Итог недоступен: нет ключа Ollama» etc.
    news_summary_error: str = ""
    sources: tuple[str, ...] = field(default_factory=tuple)


OUTCOME_SHORT_RU = {"1": "П1", "X": "Х", "2": "П2"}


@dataclass(frozen=True)
class ResultCheck:
    """How the forecast compares with the final score of a played match."""

    final: str  # "2:1"
    actual: str  # "1" / "X" / "2"
    predicted: str  # favourite outcome of the 1X2 probabilities
    predicted_probability: float
    outcome_hit: bool
    predicted_score: str  # most likely exact score, "1:1"
    score_hit: bool

    @property
    def summary(self) -> str:
        outcome = "угадан" if self.outcome_hit else "не угадан"
        score = "угадан" if self.score_hit else "не угадан"
        return (
            f"Исход {OUTCOME_SHORT_RU[self.predicted]} "
            f"({round(self.predicted_probability * 100)}%) — {outcome}; "
            f"счёт {self.predicted_score} — {score}."
        )


def check_against_result(forecast: MatchForecast) -> ResultCheck | None:
    """None until the match is played. Probabilities are only read, never changed."""
    match = forecast.match
    actual = match.result_side
    final = match.score_label
    if actual is None or final is None:
        return None
    probs = forecast.probabilities.normalized()
    predicted = probs.favorite_label
    chance = {"1": probs.home, "X": probs.draw, "2": probs.away}[predicted]
    line = forecast.scoreline
    return ResultCheck(
        final=final,
        actual=actual,
        predicted=predicted,
        predicted_probability=chance,
        outcome_hit=predicted == actual,
        predicted_score=line.label,
        score_hit=(line.home_goals, line.away_goals) == (match.score.home, match.score.away),
    )
