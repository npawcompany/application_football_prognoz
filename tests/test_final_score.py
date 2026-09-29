from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import flet as ft

from football_prognoz.domain.match import Match, MatchStatus, Score
from football_prognoz.domain.prediction import (
    MatchFeatures,
    MatchForecast,
    Probabilities,
    Scoreline,
    check_against_result,
)
from football_prognoz.ui.components.match_card import match_card
from football_prognoz.ui.components.result_banner import result_banner


def _match(status: MatchStatus, home: int | None, away: int | None) -> Match:
    return Match(
        id=1,
        competition_code="PL",
        utc_date=datetime(2026, 9, 27, 14, 0, tzinfo=UTC),
        status=status,
        matchday=6,
        home_id=61,
        home_name="Chelsea FC",
        away_id=66,
        away_name="Manchester United FC",
        score=Score(home, away),
    )


def _forecast(match: Match, probs=(0.46, 0.25, 0.29), line=(1, 1)) -> MatchForecast:
    return MatchForecast(
        match=match,
        probabilities=Probabilities(*probs),
        features=MatchFeatures("", "", 1500, 1500, "", None, None, 0, 0, 0, 0, 0),
        explanation=None,
        scoreline=Scoreline(line[0], line[1], 0.12, 1.3, 1.3),
    )


def _texts(control) -> list[str]:
    out: list[str] = []

    def walk(node) -> None:
        if isinstance(node, ft.Text) and isinstance(node.value, str):
            out.append(node.value)
        for attr in ("content", "controls"):
            value = getattr(node, attr, None)
            if isinstance(value, list):
                for child in value:
                    walk(child)
            elif isinstance(value, ft.Control):
                walk(value)

    walk(control)
    return out


def test_status_text_in_russian_with_the_score() -> None:
    assert _match(MatchStatus.FINISHED, 2, 1).status_text == "Завершён 2:1"
    assert _match(MatchStatus.IN_PLAY, 1, 0).status_text == "Идёт 1:0"
    assert _match(MatchStatus.PAUSED, 0, 0).status_text == "Перерыв 0:0"
    assert _match(MatchStatus.TIMED, None, None).status_text == "Запланирован"
    assert _match(MatchStatus.POSTPONED, None, None).status_text == "Перенесён"
    assert _match(MatchStatus.AWARDED, 3, 0).status_text == "Тех. результат 3:0"
    finished_no_score = _match(MatchStatus.FINISHED, None, None)
    assert finished_no_score.status_text == "Завершён"
    assert finished_no_score.is_played is False
    assert _match(MatchStatus.FINISHED, 0, 2).result_side == "2"
    assert _match(MatchStatus.FINISHED, 1, 1).result_side == "X"
    assert _match(MatchStatus.IN_PLAY, 1, 0).result_side is None


def test_check_against_result_reads_but_never_changes_probabilities() -> None:
    forecast = _forecast(_match(MatchStatus.FINISHED, 2, 1))
    check = check_against_result(forecast)
    assert check is not None
    assert (check.final, check.actual, check.predicted) == ("2:1", "1", "1")
    assert check.outcome_hit is True and check.score_hit is False
    assert check.summary == "Исход П1 (46%) — угадан; счёт 1:1 — не угадан."
    assert forecast.probabilities == Probabilities(0.46, 0.25, 0.29)
    draw = check_against_result(_forecast(_match(MatchStatus.FINISHED, 1, 1)))
    assert draw is not None and draw.score_hit is True and draw.outcome_hit is False
    assert check_against_result(_forecast(_match(MatchStatus.TIMED, None, None))) is None
    assert check_against_result(_forecast(_match(MatchStatus.IN_PLAY, 1, 0))) is None


def test_match_card_shows_the_final_score_prominently() -> None:
    card = match_card(_match(MatchStatus.FINISHED, 2, 1), lambda _m: None)
    texts = _texts(card)
    assert "Завершён 2:1" in texts
    assert "2" in texts and "1" in texts
    assert "FINISHED" not in texts
    upcoming = _texts(match_card(_match(MatchStatus.TIMED, None, None), lambda _m: None))
    assert "Запланирован" in upcoming and "TIMED" not in upcoming


def test_result_banner_compares_with_the_forecast() -> None:
    banner = result_banner(_forecast(_match(MatchStatus.FINISHED, 2, 1)))
    texts = _texts(banner)
    assert "Завершён 2:1" in texts
    assert any(t.startswith("Исход П1 (46%) — угадан") for t in texts)
    assert any(t.startswith("Счёт 1:1 — нет") for t in texts)
    live = result_banner(_forecast(replace(_match(MatchStatus.IN_PLAY, 1, 0))))
    assert "Идёт 1:0" in _texts(live)
    assert result_banner(_forecast(_match(MatchStatus.TIMED, None, None))) is None
