"""Calendar day logic: local-day bounds, week windows, grouping. Pure, no I/O."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, tzinfo
from enum import StrEnum

from football_prognoz.domain.match import Match
from football_prognoz.domain.team import Competition

WINDOW_DAYS = 7  # one GET /v4/matches per week (the API allows up to 10 days)
FAVORITES_KEY = "__favorites__"


class GroupMode(StrEnum):
    LEAGUE = "league"
    TEAM = "team"


@dataclass(frozen=True)
class MatchGroup:
    key: str
    title: str
    matches: tuple[Match, ...]
    code: str | None = None
    emblem: str | None = None
    crest: str | None = None
    favorite: bool = False


def local_tz() -> tzinfo:
    return datetime.now().astimezone().tzinfo or UTC


def local_date(moment: datetime, tz: tzinfo | None = None) -> date:
    aware = moment if moment.tzinfo else moment.replace(tzinfo=UTC)
    return aware.astimezone(tz or local_tz()).date()


def day_bounds(day: date, tz: tzinfo | None = None) -> tuple[datetime, datetime]:
    """[start, end) of a local calendar day, as UTC instants."""
    zone = tz or local_tz()
    start = datetime.combine(day, time.min, tzinfo=zone).astimezone(UTC)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=zone).astimezone(UTC)
    return start, end


def week_window(day: date) -> tuple[date, date]:
    """Monday..Sunday week that contains `day` (inclusive bounds)."""
    start = day - timedelta(days=day.weekday())
    return start, start + timedelta(days=WINDOW_DAYS - 1)


def request_range(day: date) -> tuple[date, date]:
    """UTC dates to request for the week of `day`, padded by a day for timezone offsets."""
    start, end = week_window(day)
    return start - timedelta(days=1), end + timedelta(days=1)


def matches_on(matches: Iterable[Match], day: date, tz: tzinfo | None = None) -> list[Match]:
    zone = tz or local_tz()
    picked = [item for item in matches if local_date(item.utc_date, zone) == day]
    picked.sort(key=lambda item: (item.utc_date, item.id))
    return picked


def match_days(matches: Iterable[Match], tz: tzinfo | None = None) -> list[date]:
    zone = tz or local_tz()
    return sorted({local_date(item.utc_date, zone) for item in matches})


def nearest_day(days: Sequence[date], day: date, step: int) -> date | None:
    """Next (step > 0) or previous (step < 0) day with matches, strictly after/before."""
    if step > 0:
        later = [item for item in days if item > day]
        return min(later) if later else None
    earlier = [item for item in days if item < day]
    return max(earlier) if earlier else None


def _involves(match: Match, team_ids: set[int]) -> bool:
    return match.home_id in team_ids or match.away_id in team_ids


def group_day_matches(
    matches: Sequence[Match],
    competitions: Mapping[str, Competition],
    *,
    mode: GroupMode = GroupMode.LEAGUE,
    favorite_team_ids: Iterable[int] = (),
    favorite_codes: Iterable[str] = (),
    team_query: str = "",
) -> list[MatchGroup]:
    """Group one day's matches by league (favourite leagues first) or by team.

    Matches with a favourite team are also pinned in a first «Любимые команды» group.
    `team_query` keeps matches whose home or away name contains the text.
    """
    needle = team_query.strip().casefold()
    items = sorted(
        (
            item
            for item in matches
            if not needle
            or needle in item.home_name.casefold()
            or needle in item.away_name.casefold()
        ),
        key=lambda item: (item.utc_date, item.id),
    )
    fav_teams = set(favorite_team_ids)
    fav_codes = {code.upper() for code in favorite_codes}
    groups: list[MatchGroup] = []
    pinned = tuple(item for item in items if fav_teams and _involves(item, fav_teams))
    if pinned:
        groups.append(MatchGroup(FAVORITES_KEY, "Любимые команды", pinned, favorite=True))
    if mode is GroupMode.TEAM:
        by_team: dict[int, list[Match]] = {}
        names: dict[int, tuple[str, str | None]] = {}
        for item in items:
            for team_id, name, crest in (
                (item.home_id, item.home_name, item.home_crest),
                (item.away_id, item.away_name, item.away_crest),
            ):
                by_team.setdefault(team_id, []).append(item)
                names.setdefault(team_id, (name, crest))
        order = sorted(
            by_team,
            key=lambda team_id: (team_id not in fav_teams, names[team_id][0].casefold()),
        )
        for team_id in order:
            name, crest = names[team_id]
            if needle and needle not in name.casefold():
                continue  # the opponent of a searched team gets no group of its own
            groups.append(
                MatchGroup(
                    f"team:{team_id}",
                    name,
                    tuple(by_team[team_id]),
                    crest=crest,
                    favorite=team_id in fav_teams,
                )
            )
        return groups
    by_code: dict[str, list[Match]] = {}
    for item in items:
        by_code.setdefault(item.competition_code, []).append(item)

    def league_key(code: str) -> tuple[bool, str]:
        competition = competitions.get(code)
        return (
            code.upper() not in fav_codes,
            (competition.name if competition else code).casefold(),
        )

    for code in sorted(by_code, key=league_key):
        competition = competitions.get(code)
        groups.append(
            MatchGroup(
                f"league:{code}",
                competition.name if competition else code,
                tuple(by_code[code]),
                code=code,
                emblem=competition.emblem if competition else None,
                favorite=code.upper() in fav_codes,
            )
        )
    return groups


def format_day_ru(day: date, today: date | None = None) -> str:
    """«Сегодня, 29 сентября», «Завтра, …», «Пт, 3 октября 2027»."""
    months = (
        "января",
        "февраля",
        "марта",
        "апреля",
        "мая",
        "июня",
        "июля",
        "августа",
        "сентября",
        "октября",
        "ноября",
        "декабря",
    )
    weekdays = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")
    base = f"{day.day} {months[day.month - 1]}"
    reference = today or date.today()
    if day.year != reference.year:
        base = f"{base} {day.year}"
    delta = (day - reference).days
    prefix = {0: "Сегодня", 1: "Завтра", -1: "Вчера"}.get(delta, weekdays[day.weekday()])
    return f"{prefix}, {base}"
