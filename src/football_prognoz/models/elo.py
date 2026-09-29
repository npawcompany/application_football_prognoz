from __future__ import annotations

import math
from collections import defaultdict

from football_prognoz.domain.match import Match

INITIAL_ELO = 1500.0
K_FACTOR = 20.0
HOME_ADVANTAGE = 80.0


def expected_score(rating_a: float, rating_b: float) -> float:
    return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))


def result_score(home_goals: int, away_goals: int) -> tuple[float, float]:
    if home_goals > away_goals:
        return 1.0, 0.0
    if home_goals < away_goals:
        return 0.0, 1.0
    return 0.5, 0.5


def build_elo(matches: list[Match]) -> dict[int, float]:
    ratings: dict[int, float] = defaultdict(lambda: INITIAL_ELO)
    ordered = sorted(
        (m for m in matches if m.status.is_finished() and m.score.home is not None),
        key=lambda m: m.utc_date,
    )
    for match in ordered:
        assert match.score.home is not None
        assert match.score.away is not None
        home_rating = ratings[match.home_id]
        away_rating = ratings[match.away_id]
        exp_home = expected_score(home_rating + HOME_ADVANTAGE, away_rating)
        actual_home, actual_away = result_score(match.score.home, match.score.away)
        ratings[match.home_id] = home_rating + K_FACTOR * (actual_home - exp_home)
        ratings[match.away_id] = away_rating + K_FACTOR * (actual_away - (1.0 - exp_home))
    return dict(ratings)


def elo_1x2(home_elo: float, away_elo: float) -> tuple[float, float, float]:
    diff = home_elo + HOME_ADVANTAGE - away_elo
    exp_home = expected_score(home_elo + HOME_ADVANTAGE, away_elo)
    draw = 0.27 - 0.06 * math.tanh(abs(diff) / 200.0)
    draw = min(0.32, max(0.18, draw))
    rest = 1.0 - draw
    home = rest * exp_home
    away = rest - home
    return home, draw, away
