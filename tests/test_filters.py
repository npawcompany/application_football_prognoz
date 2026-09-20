from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from football_prognoz.domain.match import Match, MatchStatus, Score
from football_prognoz.services.filters import filter_competitions, filter_matches


@dataclass(frozen=True)
class Item:
    name: str
    code: str


NOW = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)


def _match(
    *,
    home: str = "Arsenal",
    away: str = "Man City",
    when: datetime | None = None,
    status: MatchStatus = MatchStatus.SCHEDULED,
    match_id: int = 1,
) -> Match:
    return Match(
        id=match_id,
        competition_code="PL",
        utc_date=when if when is not None else NOW + timedelta(days=1),
        status=status,
        matchday=6,
        home_id=57,
        home_name=home,
        away_id=65,
        away_name=away,
        score=Score(None, None),
    )


def test_filter_competitions_matches_name_or_code_casefold() -> None:
    items = [
        Item("Premier League", "PL"),
        Item("La Liga", "PD"),
        Item("Campeonato Brasileiro Série A", "BSA"),
    ]
    assert [item.code for item in filter_competitions(items, "premier")] == ["PL"]
    assert [item.code for item in filter_competitions(items, "pd")] == ["PD"]
    assert [item.code for item in filter_competitions(items, "  LIGA  ")] == ["PD"]
    assert filter_competitions(items, "") == items
    assert filter_competitions(items, "   ") == items
    assert filter_competitions(items, "xyz") == []


def test_filter_matches_team_query_and_upcoming() -> None:
    past = _match(home="Chelsea", away="Everton", when=NOW - timedelta(hours=1), match_id=1)
    live = _match(
        home="Arsenal",
        away="Fulham",
        when=NOW - timedelta(minutes=10),
        status=MatchStatus.IN_PLAY,
        match_id=2,
    )
    finished = _match(
        home="Liverpool",
        away="Man City",
        when=NOW - timedelta(days=1),
        status=MatchStatus.FINISHED,
        match_id=3,
    )
    future_city = _match(
        home="Brighton",
        away="Man City",
        when=NOW + timedelta(days=2),
        match_id=4,
    )
    future_ars = _match(
        home="Arsenal",
        away="Spurs",
        when=NOW + timedelta(hours=3),
        match_id=5,
    )
    timed = _match(
        home="Wolves",
        away="Leeds",
        when=NOW,
        status=MatchStatus.TIMED,
        match_id=6,
    )
    items = [past, live, finished, future_city, future_ars, timed]

    upcoming = filter_matches(items, now=NOW)
    assert [item.id for item in upcoming] == [4, 5, 6]

    by_team = filter_matches(items, team_query="CITY", now=NOW)
    assert [item.id for item in by_team] == [4]

    by_home = filter_matches(items, team_query=" arsenal ", now=NOW)
    assert [item.id for item in by_home] == [5]

    all_city = filter_matches(items, team_query="city", upcoming_only=False)
    assert [item.id for item in all_city] == [3, 4]

    assert filter_matches(items, team_query="xyz", now=NOW) == []
    assert filter_matches([], team_query="ars", now=NOW) == []
