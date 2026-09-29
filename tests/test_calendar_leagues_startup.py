"""Pure calendar grouping, league availability/filtering and startup gate/splash rules."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone

from football_prognoz.config import Settings
from football_prognoz.domain.match import Match, MatchStatus, Score
from football_prognoz.domain.team import Competition, Team
from football_prognoz.services.calendar import (
    FAVORITES_KEY,
    GroupMode,
    day_bounds,
    format_day_ru,
    group_day_matches,
    match_days,
    matches_on,
    nearest_day,
    request_range,
    week_window,
)
from football_prognoz.services.leagues import (
    LeagueFilter,
    LeagueGrouping,
    LeagueType,
    areas,
    filter_leagues,
    group_leagues,
    group_teams_by_league,
    league_info,
    league_infos,
)
from football_prognoz.services.startup import (
    GateState,
    KeyGate,
    SplashTimer,
    missing_required_keys,
)

MSK = timezone(timedelta(hours=3))


def _m(mid: int, code: str, when: datetime, home: tuple[int, str], away: tuple[int, str]) -> Match:
    return Match(
        mid, code, when, MatchStatus.TIMED, 1, home[0], home[1], away[0], away[1], Score(None, None)
    )


COMPS = {
    "PL": Competition(2021, "PL", "Premier League", type="LEAGUE", area_name="England"),
    "CL": Competition(2001, "CL", "UEFA Champions League", type="CUP", area_name="Europe"),
    "PD": Competition(2014, "PD", "Primera Division", type="LEAGUE", area_name="Spain"),
}

DAY = [
    _m(1, "PL", datetime(2026, 10, 3, 11, 30, tzinfo=UTC), (57, "Arsenal"), (61, "Chelsea")),
    _m(2, "PD", datetime(2026, 10, 3, 19, 0, tzinfo=UTC), (86, "Real Madrid"), (81, "Barcelona")),
    _m(3, "CL", datetime(2026, 10, 3, 19, 0, tzinfo=UTC), (65, "Man City"), (57, "Arsenal")),
]


def test_day_bounds_follow_the_local_zone() -> None:
    start, end = day_bounds(date(2026, 10, 3), MSK)
    assert start == datetime(2026, 10, 2, 21, 0, tzinfo=UTC)
    assert end - start == timedelta(days=1)
    late = _m(9, "PL", datetime(2026, 10, 2, 22, 0, tzinfo=UTC), (1, "A"), (2, "B"))
    assert [m.id for m in matches_on([late], date(2026, 10, 3), MSK)] == [9]
    assert matches_on([late], date(2026, 10, 3), UTC) == []


def test_week_window_and_padded_request_range() -> None:
    assert week_window(date(2026, 10, 1)) == (date(2026, 9, 28), date(2026, 10, 4))
    assert request_range(date(2026, 10, 4)) == (date(2026, 9, 27), date(2026, 10, 5))


def test_nearest_match_day_jumps() -> None:
    days = match_days(DAY + [_m(4, "PL", datetime(2026, 10, 18, tzinfo=UTC), (1, "A"), (2, "B"))])
    assert nearest_day(days, date(2026, 10, 3), 1) == date(2026, 10, 18)
    assert nearest_day(days, date(2026, 10, 10), -1) == date(2026, 10, 3)
    assert nearest_day(days, date(2026, 10, 18), 1) is None


def test_group_by_league_favourite_league_first() -> None:
    groups = group_day_matches(DAY, COMPS, favorite_codes=["PD"])
    assert [g.key for g in groups] == ["league:PD", "league:PL", "league:CL"]
    assert groups[0].favorite is True
    assert groups[2].title == "UEFA Champions League"


def test_favourite_team_matches_are_pinned_first() -> None:
    groups = group_day_matches(DAY, COMPS, favorite_team_ids=[57])
    assert groups[0].key == FAVORITES_KEY
    assert [m.id for m in groups[0].matches] == [1, 3]
    # the matches stay in their league groups too
    assert sum(len(g.matches) for g in groups[1:]) == 3


def test_group_by_team_and_team_query() -> None:
    groups = group_day_matches(DAY, COMPS, mode=GroupMode.TEAM)
    arsenal = next(g for g in groups if g.title == "Arsenal")
    assert [m.id for m in arsenal.matches] == [1, 3]
    only = group_day_matches(DAY, COMPS, team_query="barc")
    assert [m.id for g in only for m in g.matches] == [2]


def test_format_day_ru() -> None:
    today = date(2026, 9, 29)
    assert format_day_ru(today, today) == "Сегодня, 29 сентября"
    assert format_day_ru(date(2026, 9, 30), today) == "Завтра, 30 сентября"
    assert format_day_ru(date(2027, 1, 1), today) == "Пт, 1 января 2027"


TODAY = date(2026, 9, 29)


def test_league_info_rules() -> None:
    pl = COMPS["PL"]
    assert league_info(pl, upcoming=5, complete=True, today=TODAY).note == "5 матчей"
    idle = league_info(pl, upcoming=0, complete=True, today=TODAY)
    assert idle.disabled and "нет матчей" in idle.note
    assert league_info(pl, upcoming=2, complete=False, today=TODAY).note == "от 2 матча"
    finished = Competition(1, "EC", "Euro", type="CUP", season_end=date(2024, 7, 14))
    assert league_info(finished, upcoming=0, complete=False, today=TODAY).disabled
    far = Competition(2, "WC", "World Cup", type="CUP", season_start=date(2030, 6, 1))
    assert league_info(far, upcoming=0, complete=False, today=TODAY).disabled
    unknown = league_info(pl, upcoming=0, complete=False, today=TODAY)
    assert unknown.active and unknown.upcoming is None


def _infos():
    comps = [*COMPS.values(), Competition(3, "EC", "European Championship", type="CUP")]
    return league_infos(comps, {"PL": 10, "CL": 4}, ["PL", "CL", "PD", "EC"], today=TODAY)


def test_filter_leagues_by_text_area_type_and_activity() -> None:
    infos = _infos()
    code = lambda items: sorted(i.code for i in items)  # noqa: E731
    assert code(filter_leagues(infos, LeagueFilter(query="prem"))) == ["PL"]
    assert code(filter_leagues(infos, LeagueFilter(query="spain"))) == ["PD"]
    assert code(filter_leagues(infos, LeagueFilter(area="Europe"))) == ["CL", "EC"]
    assert code(filter_leagues(infos, LeagueFilter(league_type=LeagueType.CUP))) == ["CL", "EC"]
    assert code(filter_leagues(infos, LeagueFilter(league_type=LeagueType.LEAGUE))) == ["PD", "PL"]
    assert code(filter_leagues(infos, LeagueFilter(active_only=True))) == ["CL", "PL"]
    fav = filter_leagues(infos, LeagueFilter(favorites_only=True), ["pd"])
    assert code(fav) == ["PD"]
    assert "England" in areas(infos)


def test_group_leagues_by_area_and_type() -> None:
    infos = _infos()
    by_type = dict(group_leagues(infos, LeagueGrouping.TYPE))
    assert sorted(i.code for i in by_type["Кубок"]) == ["CL", "EC"]
    by_area = group_leagues(infos, LeagueGrouping.AREA, ["PD"])
    assert [title for title, _ in by_area] == sorted(t for t, _ in by_area)
    flat = group_leagues(infos, LeagueGrouping.NONE, ["PD"])
    assert flat[0][1][0].code == "PD"  # favourite first
    assert flat[0][1][-1].disabled  # greyed-out leagues last


def test_teams_grouped_by_league_without_duplicates() -> None:
    teams = {
        "PL": [Team(57, "Arsenal"), Team(61, "Chelsea")],
        "CL": [Team(57, "Arsenal"), Team(86, "Real Madrid")],
    }
    grouped = group_teams_by_league(teams, COMPS.values(), ["PL", "CL"])
    assert [(c.code, [t.name for t in ts]) for c, ts in grouped] == [
        ("PL", ["Arsenal", "Chelsea"]),
        ("CL", ["Real Madrid"]),
    ]


class _Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def test_splash_waits_at_least_three_seconds_for_fast_loads() -> None:
    clock = _Clock()
    timer = SplashTimer(clock=clock)
    clock.now += 0.4
    timer.mark_loaded()
    assert not timer.can_hide()
    assert abs(timer.remaining() - 2.6) < 1e-9
    clock.now += 2.6
    assert timer.can_hide()


def test_splash_waits_for_slow_loads() -> None:
    clock = _Clock()
    timer = SplashTimer(clock=clock)
    clock.now += 7.0
    assert timer.remaining() == 0.0
    assert not timer.can_hide()  # still loading
    timer.mark_loaded()
    assert timer.can_hide()
    loaded_at = timer.loaded_at
    clock.now += 1
    timer.mark_loaded()  # idempotent
    assert timer.loaded_at == loaded_at


def _settings(**values) -> Settings:
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


def test_only_football_data_key_is_required() -> None:
    assert missing_required_keys(_settings()) == ["FOOTBALL_DATA_API_KEY"]
    assert missing_required_keys(_settings(football_data_api_key="  ")) == ["FOOTBALL_DATA_API_KEY"]
    assert missing_required_keys(_settings(football_data_api_key="k")) == []


def test_gate_blocks_everything_but_settings_until_key_is_valid() -> None:
    gate = KeyGate.from_settings(_settings())
    assert gate.state is GateState.MISSING and gate.locked
    assert gate.target("fixtures") == "settings"
    assert gate.target("leagues") == "settings"
    assert gate.allows("settings")
    assert "football-data.org" in gate.notice()

    gate.evaluate(_settings(football_data_api_key="new"))
    assert not gate.locked  # a key is present; the ping decides below
    gate.start_check()
    assert gate.locked and gate.target("forecast") == "settings"
    gate.check_failed("Ключ не принят", rejected=True)
    assert gate.state is GateState.REJECTED and "не принят" in gate.notice()
    gate.start_check()
    gate.check_passed()
    assert not gate.locked and gate.target("fixtures") == "fixtures"


def test_gate_opens_on_network_failure_but_not_on_rejection() -> None:
    gate = KeyGate.from_settings(_settings(football_data_api_key="k"), key_rejected=True)
    assert gate.state is GateState.REJECTED
    gate.start_check()
    gate.check_failed("Нет связи", rejected=False)
    assert not gate.locked
