from __future__ import annotations

import math

from football_prognoz.domain.match import Match
from football_prognoz.domain.prediction import MatchFeatures, Probabilities, Scoreline
from football_prognoz.models.elo import elo_1x2

MAX_GOALS = 8
LEAGUE_AVG_GOALS = 1.35


def poisson_pmf(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * lam**k / math.factorial(k)


def _clip_lambda(value: float) -> float:
    return min(4.0, max(0.25, value))


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


def goals_only_lambda(features: MatchFeatures) -> tuple[float, float]:
    """Expected goals from last-5 scored/conceded averages only.

    K1 = (home goals for + away goals against) / 2
    K2 = (away goals for + home goals against) / 2
    No Elo, table, H2H, injuries, or ceil/floor rounding.
    """
    lam_home = (features.home_recent_goals_for + features.away_recent_goals_against) / 2.0
    lam_away = (features.away_recent_goals_for + features.home_recent_goals_against) / 2.0
    return _clip_lambda(lam_home), _clip_lambda(lam_away)


def poisson_mode(lam_home: float, lam_away: float) -> Scoreline:
    """Most likely exact score on the independent Poisson grid 0…MAX_GOALS."""
    best_i = best_j = 0
    best_p = -1.0
    best_dist = float("inf")
    total = 0.0
    for i in range(MAX_GOALS + 1):
        for j in range(MAX_GOALS + 1):
            p = poisson_pmf(i, lam_home) * poisson_pmf(j, lam_away)
            total += p
            dist = (i - lam_home) ** 2 + (j - lam_away) ** 2
            if p > best_p + 1e-15 or (abs(p - best_p) <= 1e-15 and dist < best_dist):
                best_i, best_j, best_p, best_dist = i, j, p, dist
    probability = best_p / total if total > 0 else 0.0
    return Scoreline(
        home_goals=best_i,
        away_goals=best_j,
        probability=probability,
        expected_home=lam_home,
        expected_away=lam_away,
    )


def _blend(a: Probabilities, b: Probabilities, weight_a: float) -> Probabilities:
    w = min(1.0, max(0.0, weight_a))
    return Probabilities(
        home=w * a.home + (1 - w) * b.home,
        draw=w * a.draw + (1 - w) * b.draw,
        away=w * a.away + (1 - w) * b.away,
    ).normalized()


def _lambda(attack: float, defense: float, elo_shift: float) -> float:
    value = LEAGUE_AVG_GOALS * attack * defense * (1.0 + elo_shift)
    return _clip_lambda(value)


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

    def preliminary_score(self, features: MatchFeatures) -> Scoreline:
        lam_home, lam_away = goals_only_lambda(features)
        return poisson_mode(lam_home, lam_away)
