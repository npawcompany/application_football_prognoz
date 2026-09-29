from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from football_prognoz.data.api_football import AfFixture
from football_prognoz.domain.match import Match, MatchStatus, Score
from football_prognoz.services.team_matching import (
    find_fixture,
    names_match,
    normalize_team_name,
)

KICKOFF = datetime(2026, 9, 26, 14, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("fd", "af"),
    [
        ("Arsenal FC", "Arsenal"),
        ("Wolverhampton Wanderers FC", "Wolves"),
        ("FC Internazionale Milano", "Inter"),
        ("Paris Saint-Germain FC", "Paris Saint Germain"),
        ("Club Atlético de Madrid", "Atletico Madrid"),
        ("FC Bayern München", "Bayern Munich"),
        ("Brighton & Hove Albion FC", "Brighton"),
        ("AFC Bournemouth", "Bournemouth"),
    ],
)
def test_known_names_match(fd: str, af: str) -> None:
    assert names_match(fd, af)


@pytest.mark.parametrize(
    ("fd", "af"),
    [("Manchester City FC", "Manchester United"), ("Chelsea FC", "Arsenal"), ("", "Arsenal")],
)
def test_different_names_do_not_match(fd: str, af: str) -> None:
    assert not names_match(fd, af)


def test_normalize_strips_diacritics_and_noise() -> None:
    assert normalize_team_name("Club Atlético de Madrid") == "atletico madrid"


def _match(home: str = "Arsenal FC", away: str = "Manchester City FC") -> Match:
    return Match(
        id=201,
        competition_code="PL",
        utc_date=KICKOFF,
        status=MatchStatus.SCHEDULED,
        matchday=6,
        home_id=57,
        home_name=home,
        away_id=65,
        away_name=away,
        score=Score(None, None),
    )


def _fx(fid: int, home: tuple[int, str], away: tuple[int, str], shift_h: float = 0) -> AfFixture:
    return AfFixture(
        fixture_id=fid,
        date=KICKOFF + timedelta(hours=shift_h),
        status_short="NS",
        league_id=39,
        season=2026,
        home_id=home[0],
        home_name=home[1],
        away_id=away[0],
        away_name=away[1],
    )


def test_find_fixture_uses_names_and_date_tolerance() -> None:
    fixtures = [
        _fx(1, (42, "Arsenal"), (50, "Manchester City"), shift_h=24 * 7),  # other round
        _fx(2, (42, "Arsenal"), (50, "Manchester City"), shift_h=2),  # rescheduled +2 h
        _fx(3, (40, "Liverpool"), (39, "Wolves")),
    ]
    assert find_fixture(_match(), fixtures).fixture_id == 2
    assert find_fixture(_match("Liverpool FC", "Chelsea FC"), fixtures) is None


def test_exact_name_beats_partial_name() -> None:
    fixtures = [
        _fx(10, (529, "Barcelona"), (541, "Real Madrid")),
        _fx(11, (540, "Espanyol Barcelona"), (541, "Real Madrid")),
    ]
    assert find_fixture(_match("FC Barcelona", "Real Madrid CF"), fixtures).fixture_id == 10


def test_known_team_ids_override_names() -> None:
    fixtures = [_fx(5, (42, "Arsenal London"), (50, "Man. City"))]
    assert find_fixture(_match(), fixtures, known_home=42, known_away=50).fixture_id == 5
    assert find_fixture(_match(), fixtures, known_home=99, known_away=50) is None
