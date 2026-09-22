from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from football_prognoz.domain.match import Match, MatchStatus, Score
from football_prognoz.services.filters import (
    DateWindow,
    FixtureQuery,
    MatchSort,
    MatchStatusFilter,
    apply_fixture_query,
    filter_competitions,
    filter_matches,
    paginate,
    sort_matches,
)


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
    matchday: int | None = 6,
) -> Match:
    return Match(
        id=match_id,
        competition_code="PL",
        utc_date=when if when is not None else NOW + timedelta(days=1),
        status=status,
        matchday=matchday,
        home_id=57,
        home_name=home,
        away_id=65,
        away_name=away,
        score=Score(None, None),
    )


def _ids(result: object) -> list[int]:
    items = getattr(result, "items", result)
    return [item.id for item in items]


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


def test_live_filter_keeps_in_play_not_finished() -> None:
    live = _match(status=MatchStatus.IN_PLAY, when=NOW - timedelta(minutes=10), match_id=1)
    paused = _match(home="Chelsea", status=MatchStatus.PAUSED, when=NOW, match_id=2)
    finished = _match(
        home="Liverpool",
        status=MatchStatus.FINISHED,
        when=NOW - timedelta(hours=2),
        match_id=3,
    )
    scheduled = _match(home="Spurs", when=NOW + timedelta(hours=2), match_id=4)
    result = apply_fixture_query(
        [live, paused, finished, scheduled],
        FixtureQuery(status=MatchStatusFilter.LIVE),
        now=NOW,
    )
    assert _ids(result) == [1, 2]


def test_finished_filter_keeps_finished_and_awarded() -> None:
    finished = _match(status=MatchStatus.FINISHED, when=NOW - timedelta(days=1), match_id=1)
    awarded = _match(
        home="Chelsea",
        status=MatchStatus.AWARDED,
        when=NOW - timedelta(hours=3),
        match_id=2,
    )
    live = _match(home="Spurs", status=MatchStatus.IN_PLAY, when=NOW, match_id=3)
    upcoming = _match(home="Wolves", when=NOW + timedelta(days=1), match_id=4)
    result = apply_fixture_query(
        [finished, awarded, live, upcoming],
        FixtureQuery(status=MatchStatusFilter.FINISHED),
        now=NOW,
    )
    assert _ids(result) == [1, 2]


def test_date_window_today() -> None:
    today = _match(when=NOW + timedelta(hours=3), match_id=1)
    today_morning = _match(
        home="Chelsea",
        when=NOW.replace(hour=8),
        status=MatchStatus.FINISHED,
        match_id=2,
    )
    tomorrow = _match(home="Spurs", when=NOW + timedelta(days=1), match_id=3)
    yesterday = _match(
        home="Wolves",
        when=NOW - timedelta(days=1),
        status=MatchStatus.FINISHED,
        match_id=4,
    )
    result = apply_fixture_query(
        [today, today_morning, tomorrow, yesterday],
        FixtureQuery(status=MatchStatusFilter.ALL, date_window=DateWindow.TODAY),
        now=NOW,
    )
    assert _ids(result) == [1, 2]


def test_date_window_days_7_forward() -> None:
    within = _match(when=NOW + timedelta(days=5), match_id=1)
    edge = _match(home="Chelsea", when=NOW + timedelta(days=7), match_id=2)
    too_far = _match(home="Spurs", when=NOW + timedelta(days=8), match_id=3)
    past = _match(
        home="Wolves",
        when=NOW - timedelta(days=1),
        status=MatchStatus.FINISHED,
        match_id=4,
    )
    result = apply_fixture_query(
        [within, edge, too_far, past],
        FixtureQuery(status=MatchStatusFilter.ALL, date_window=DateWindow.DAYS_7),
        now=NOW,
    )
    assert _ids(result) == [1, 2]


def test_date_window_days_7_backward_for_finished() -> None:
    within = _match(status=MatchStatus.FINISHED, when=NOW - timedelta(days=5), match_id=1)
    edge = _match(
        home="Chelsea",
        status=MatchStatus.FINISHED,
        when=NOW - timedelta(days=7),
        match_id=2,
    )
    too_old = _match(
        home="Spurs",
        status=MatchStatus.FINISHED,
        when=NOW - timedelta(days=8),
        match_id=3,
    )
    future = _match(
        home="Wolves",
        status=MatchStatus.FINISHED,
        when=NOW + timedelta(days=1),
        match_id=4,
    )
    result = apply_fixture_query(
        [within, edge, too_old, future],
        FixtureQuery(status=MatchStatusFilter.FINISHED, date_window=DateWindow.DAYS_7),
        now=NOW,
    )
    assert _ids(result) == [1, 2]


def test_matchday_filter() -> None:
    md6 = _match(matchday=6, match_id=1)
    md7 = _match(home="Chelsea", matchday=7, match_id=2)
    none = _match(home="Spurs", matchday=None, match_id=3)
    result = apply_fixture_query(
        [md6, md7, none],
        FixtureQuery(status=MatchStatusFilter.ALL, matchday=6),
        now=NOW,
    )
    assert _ids(result) == [1]


def test_sort_date_desc_and_home() -> None:
    earlier = _match(home="Arsenal", when=NOW + timedelta(hours=1), match_id=1)
    mid = _match(home="Chelsea", when=NOW + timedelta(hours=5), match_id=2)
    later = _match(home="brighton", when=NOW + timedelta(days=2), match_id=3)
    items = [earlier, mid, later]
    desc = sort_matches(items, MatchSort.DATE_DESC)
    assert [item.id for item in desc] == [3, 2, 1]
    by_home = sort_matches(items, MatchSort.HOME)
    assert [item.home_name for item in by_home] == ["Arsenal", "brighton", "Chelsea"]
    via_query = apply_fixture_query(
        items,
        FixtureQuery(status=MatchStatusFilter.ALL, sort=MatchSort.DATE_DESC),
        now=NOW,
    )
    assert _ids(via_query) == [3, 2, 1]


def test_paginate_page_size_2_page_1() -> None:
    items = [_match(home=f"T{i}", match_id=i, when=NOW + timedelta(hours=i)) for i in range(1, 6)]
    result = paginate(items, page=1, page_size=2)
    assert _ids(result) == [3, 4]
    assert result.total == 5
    assert result.page == 1
    assert result.page_size == 2
    assert result.page_count == 3


def test_page_clamped_if_out_of_range() -> None:
    items = [_match(home=f"T{i}", match_id=i, when=NOW + timedelta(hours=i)) for i in range(1, 6)]
    result = apply_fixture_query(
        items,
        FixtureQuery(status=MatchStatusFilter.ALL, page=99, page_size=2),
        now=NOW,
    )
    assert result.page == 2
    assert _ids(result) == [5]
    negative = paginate(items, page=-3, page_size=2)
    assert negative.page == 0
    assert _ids(negative) == [1, 2]

