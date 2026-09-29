"""Markets table: internal consistency, handicap pushes, set-piece gating."""

from __future__ import annotations

import math

import pytest

from football_prognoz.domain.markets import NOTE_NO_KEY, NOTE_PENDING, TeamSetPieces
from football_prognoz.domain.prediction import Probabilities
from football_prognoz.models.markets import (
    build_markets,
    calibrate_to_1x2,
    outcome_sums,
    poisson_over,
    score_matrix,
)

PROBS = Probabilities(0.48, 0.27, 0.25)


def _table(**kwargs):
    return build_markets(1.55, 1.05, PROBS, sample_matches=12, **kwargs)


def _p(table, key: str) -> float:
    market = table.by_key(key)
    assert market is not None, key
    assert market.win is not None, key
    return market.win


def test_calibrated_matrix_matches_model_1x2_exactly() -> None:
    matrix = calibrate_to_1x2(score_matrix(1.55, 1.05), PROBS)
    assert math.isclose(sum(map(sum, matrix)), 1.0, abs_tol=1e-12)
    for got, want in zip(outcome_sums(matrix), (0.48, 0.27, 0.25), strict=True):
        assert got == pytest.approx(want, abs=1e-12)
    table = _table()
    assert _p(table, "1x2_1") == pytest.approx(0.48)
    assert _p(table, "1x2_x") == pytest.approx(0.27)
    assert _p(table, "1x2_2") == pytest.approx(0.25)


@pytest.mark.parametrize("line", ["0.5", "1.5", "2.5", "3.5", "4.5"])
def test_over_and_under_add_up_to_one(line: str) -> None:
    table = _table()
    assert _p(table, f"total_over_{line}") + _p(table, f"total_under_{line}") == pytest.approx(1)


def test_complementary_markets_are_consistent() -> None:
    t = _table()
    assert _p(t, "btts_yes") + _p(t, "btts_no") == pytest.approx(1)
    for side in ("1", "2"):
        for line in ("0.5", "1.5", "2.5"):
            total = _p(t, f"tt{side}_over_{line}") + _p(t, f"tt{side}_under_{line}")
            assert total == pytest.approx(1)
    assert _p(t, "dc_1x") == pytest.approx(0.48 + 0.27)
    assert _p(t, "dc_x2") == pytest.approx(0.27 + 0.25)
    assert _p(t, "dc_12") == pytest.approx(0.48 + 0.25)
    # Totals are monotone in the line.
    overs = [_p(t, f"total_over_{x}") for x in ("0.5", "1.5", "2.5", "3.5", "4.5")]
    assert overs == sorted(overs, reverse=True)
    # European handicap is 3-way: each triple sums to 1.
    assert _p(t, "eh_1_-1") + _p(t, "eh_x_1-1") + _p(t, "eh_2_+1_vs1") == pytest.approx(1)
    assert _p(t, "eh_2_-1") + _p(t, "eh_x_2-1") + _p(t, "eh_1_+1_vs2") == pytest.approx(1)
    # Win to nil is a subset of the win.
    assert _p(t, "wtn_1") < _p(t, "1x2_1")


def test_handicap_push_on_whole_lines_and_none_on_half_lines() -> None:
    t = _table()
    dnb = t.by_key("dnb_1")
    assert dnb is not None and dnb.push == pytest.approx(0.27)  # draw refunds the stake
    assert dnb.win == pytest.approx(0.48)
    assert dnb.effective == pytest.approx(0.48 / 0.73)
    assert dnb.fair_odds == pytest.approx(0.73 / 0.48)

    minus_one = t.by_key("ah_1_-1")
    assert minus_one is not None and minus_one.has_push
    # -1 for the hosts: win by 2+ wins, win by exactly 1 is a push.
    assert minus_one.win == pytest.approx(_p(t, "ah_1_-1.5"))
    assert minus_one.push == pytest.approx(_p(t, "eh_x_1-1"))
    assert minus_one.win + minus_one.push + minus_one.lose == pytest.approx(1)

    for key in ("ah_1_-0.5", "ah_1_+0.5", "ah_2_-1.5", "ah_2_+1.5"):
        market = t.by_key(key)
        assert market is not None and not market.has_push, key
    assert _p(t, "ah_1_-0.5") == pytest.approx(0.48)  # -0.5 == outright win
    assert _p(t, "ah_2_+0.5") == pytest.approx(0.27 + 0.25)
    # Mirror lines: hosts -1.5 wins exactly when guests +1.5 loses.
    assert _p(t, "ah_1_-1.5") + _p(t, "ah_2_+1.5") == pytest.approx(1)


def test_top_five_scores_and_popular_markets_first() -> None:
    t = _table()
    scores = t.in_group("correct_score")
    assert len(scores) == 5
    values = [m.win for m in scores]
    assert values == sorted(values, reverse=True)
    first = [m.group for m in t.sorted()[:7]]
    assert first[:3] == ["1x2", "1x2", "1x2"]
    assert "totals" in first and "btts" in first


def test_set_piece_rows_without_key_have_no_numbers() -> None:
    t = _table()
    for group in ("corners", "cards", "fouls", "penalty"):
        rows = t.in_group(group)
        assert rows, group
        assert all(m.win is None and m.note == NOTE_NO_KEY for m in rows)
        assert all(m.fair_odds is None for m in rows)
    pending = _table(set_pieces_note=NOTE_PENDING)
    assert pending.by_key("corners_over_9.5").note == NOTE_PENDING
    assert "corners_over_9.5" not in t.available_keys


def test_set_piece_markets_from_api_football_averages() -> None:
    home = TeamSetPieces(
        matches=3,
        corners_for=6.0,
        corners_against=4.0,
        yellow_for=2.0,
        yellow_against=1.5,
        fouls_for=11.0,
        fouls_against=12.0,
        penalties_for=0.33,
        penalties_against=0.0,
        penalty_matches=3,
    )
    away = TeamSetPieces(
        matches=3,
        corners_for=4.0,
        corners_against=5.0,
        yellow_for=2.5,
        yellow_against=2.0,
        fouls_for=13.0,
        fouls_against=10.0,
        penalties_for=0.0,
        penalties_against=0.33,
        penalty_matches=3,
    )
    t = _table(set_pieces=(home, away))
    lam_corners = (6.0 + 5.0) / 2 + (4.0 + 4.0) / 2
    assert _p(t, "corners_over_9.5") == pytest.approx(poisson_over(9.5, lam_corners))
    assert _p(t, "corners_over_9.5") + _p(t, "corners_under_9.5") == pytest.approx(1)
    lam_pen = (0.33 + 0.33) / 2 + 0.0
    assert _p(t, "penalty_yes") == pytest.approx(1 - math.exp(-lam_pen))
    assert t.by_key("cards_over_4.5").confidence in {"low", "medium"}
    few = TeamSetPieces(matches=1, corners_for=5, corners_against=5)
    thin = _table(set_pieces=(few, few))
    assert thin.by_key("corners_over_9.5").win is None


def test_small_sample_keeps_every_goal_market_low_confidence() -> None:
    t = build_markets(1.3, 1.2, PROBS, sample_matches=2)
    assert {m.confidence for m in t.markets if m.available} == {"low"}
    assert _p(t, "total_over_2.5") + _p(t, "total_under_2.5") == pytest.approx(1)


def test_to_json_is_serialisable_and_sorted() -> None:
    import json

    data = _table().to_json()
    text = json.dumps(data, ensure_ascii=False)
    assert "total_over_2.5" in text
    assert data["markets"][0]["id"] == "1x2_1"
    corners = next(m for m in data["markets"] if m["id"] == "corners_over_9.5")
    assert "probability" not in corners and corners["note"] == NOTE_NO_KEY
