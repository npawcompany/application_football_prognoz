from __future__ import annotations

import math

from football_prognoz.domain.match import Match
from football_prognoz.domain.prediction import MatchFeatures, Probabilities
from football_prognoz.models.elo import elo_1x2

MAX_GOALS = 8
LEAGUE_AVG_GOALS = 1.35


def poisson_pmf(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * lam**k / math.factorial(k)


def poisson_1x2(lam_home: float, lam_away: float) -> Probabilities:
    p_home = p_draw = p_away = 0.0
    for i in range(MAX_GOALS + 1):
        for j in range(MAX_GOALS + 1):
            p = poisson_pmf(i, lam_home) * poisson_pmf(j, lam_away)
            if i > j:
                p_home += p
            elif i == j:
                p_draw += p
            else:
                p_away += p
    return Probabilities(p_home, p_draw, p_away).normalized()


def _blend(a: Probabilities, b: Probabilities, weight_a: float) -> Probabilities:
    w = min(1.0, max(0.0, weight_a))
    return Probabilities(
        home=w * a.home + (1 - w) * b.home,
        draw=w * a.draw + (1 - w) * b.draw,
        away=w * a.away + (1 - w) * b.away,
    ).normalized()


def _lambda(attack: float, defense: float, elo_shift: float) -> float:
    value = LEAGUE_AVG_GOALS * attack * defense * (1.0 + elo_shift)
    return min(4.0, max(0.25, value))


class Predictor:
    """Elo + independent Poisson blend. Deterministic given the same features."""

    def predict(self, match: Match, features: MatchFeatures) -> Probabilities:
        _ = match
        if features.sample_matches < 4:
            home, draw, away = elo_1x2(features.home_elo, features.away_elo)
            return Probabilities(home, draw, away).normalized()

        league_avg = LEAGUE_AVG_GOALS
        home_att = max(0.4, features.home_recent_goals_for / league_avg)
        home_def = max(0.4, features.home_recent_goals_against / league_avg)
        away_att = max(0.4, features.away_recent_goals_for / league_avg)
        away_def = max(0.4, features.away_recent_goals_against / league_avg)
        elo_diff = (features.home_elo + 80.0 - features.away_elo) / 1000.0
        lam_home = _lambda(home_att, away_def, elo_diff)
        lam_away = _lambda(away_att, home_def, -elo_diff)
        poisson = poisson_1x2(lam_home, lam_away)
        elo_home, elo_draw, elo_away = elo_1x2(features.home_elo, features.away_elo)
        elo = Probabilities(elo_home, elo_draw, elo_away).normalized()
        return _blend(poisson, elo, 0.65)
