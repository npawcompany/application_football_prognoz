from __future__ import annotations

from datetime import UTC, datetime

from football_prognoz.domain.match import Match, MatchStatus, Score
from football_prognoz.domain.prediction import MatchFeatures
from football_prognoz.models.predictor import (
    Predictor,
    goals_only_lambda,
    poisson_1x2,
    poisson_mode,
)


def _match() -> Match:
    return Match(
        id=1,
        competition_code="PL",
        utc_date=datetime(2026, 9, 26, 14, 0, tzinfo=UTC),
        status=MatchStatus.SCHEDULED,
        matchday=6,
        home_id=57,
        home_name="Arsenal",
        away_id=65,
        away_name="Man City",
        score=Score(None, None),
    )


def _features(**overrides: object) -> MatchFeatures:
    data = dict(
        home_form="WWDLW",
        away_form="WDWWL",
        home_elo=1600.0,
        away_elo=1580.0,
        h2h_summary="Последние 3: Arsenal 1, ничьи 1, Man City 1",
        home_position=2,
        away_position=1,
        home_recent_goals_for=2.0,
        home_recent_goals_against=0.8,
        away_recent_goals_for=2.2,
        away_recent_goals_against=1.0,
        sample_matches=20,
    )
    data.update(overrides)
    return MatchFeatures(**data)  # type: ignore[arg-type]


def test_probabilities_sum_to_one() -> None:
    probs = Predictor().predict(_match(), _features())
    assert abs(probs.home + probs.draw + probs.away - 1.0) < 1e-9
    assert 0 < probs.home < 1
    assert 0 < probs.draw < 1
    assert 0 < probs.away < 1


def test_predictor_is_deterministic() -> None:
    first = Predictor().predict(_match(), _features())
    second = Predictor().predict(_match(), _features())
    assert first == second


def test_stronger_attack_raises_home_probability() -> None:
    base = Predictor().predict(_match(), _features())
    stronger = Predictor().predict(
        _match(),
        _features(home_recent_goals_for=3.4, home_elo=1750.0),
    )
    assert stronger.home > base.home


def test_poisson_grid_normalizes() -> None:
    probs = poisson_1x2(1.4, 1.1)
    assert abs(probs.home + probs.draw + probs.away - 1.0) < 1e-9


def test_goals_only_lambda_averages_attack_and_defence() -> None:
    lam_home, lam_away = goals_only_lambda(_features())
    assert lam_home == (2.0 + 1.0) / 2
    assert lam_away == (2.2 + 0.8) / 2


def test_preliminary_score_ignores_elo() -> None:
    base = Predictor().preliminary_score(_features(home_elo=1500.0, away_elo=1800.0))
    shifted = Predictor().preliminary_score(_features(home_elo=1900.0, away_elo=1400.0))
    assert base == shifted


def test_preliminary_score_is_poisson_mode_not_ceil_floor() -> None:
    # Heuristic ceil(1.2):floor(0.8) would print 2:0. Poisson modes are 1 and 0.
    score = poisson_mode(1.2, 0.8)
    assert score.label == "1:0"
    assert 0 < score.probability < 0.25
    assert score.expected_home == 1.2
    assert score.expected_away == 0.8


def test_stronger_home_attack_raises_expected_home_goals() -> None:
    base = Predictor().preliminary_score(_features())
    stronger = Predictor().preliminary_score(_features(home_recent_goals_for=3.4))
    assert stronger.expected_home > base.expected_home


def test_preliminary_score_is_deterministic() -> None:
    first = Predictor().preliminary_score(_features())
    second = Predictor().preliminary_score(_features())
    assert first == second
