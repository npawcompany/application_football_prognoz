"""League availability, filtering and grouping; favourite-team grouping. Pure, no I/O.

One rule set drives both the Leagues screen and the favourite-league combobox in
Settings, so a league greyed out in one place is greyed out in the other.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum

from football_prognoz.domain.country import competition_country
from football_prognoz.domain.team import COMPETITION_TYPES_RU, Competition, Team

HORIZON_DAYS = 183  # «матчи в ближайшие ~6 месяцев»


class LeagueType(StrEnum):
    ALL = "all"
    LEAGUE = "league"
    CUP = "cup"


class LeagueGrouping(StrEnum):
    NONE = "none"
    AREA = "area"
    TYPE = "type"


@dataclass(frozen=True)
class LeagueInfo:
    competition: Competition
    upcoming: int | None  # None: matches of this league were never loaded
    active: bool
    note: str

    @property
    def code(self) -> str:
        return self.competition.code

    @property
    def disabled(self) -> bool:
        return not self.active


@dataclass(frozen=True)
class LeagueFilter:
    query: str = ""
    area: str = ""  # "" = every area
    league_type: LeagueType = LeagueType.ALL
    active_only: bool = False
    favorites_only: bool = False


def area_of(competition: Competition) -> str:
    return competition.area_name or competition_country(competition.code) or "Другое"


def type_of(competition: Competition) -> str:
    return COMPETITION_TYPES_RU.get((competition.type or "LEAGUE").upper(), "Лига")


def _matches_word(count: int) -> str:
    tail = count % 100
    if 11 <= tail <= 14:
        return "матчей"
    return {1: "матч", 2: "матча", 3: "матча", 4: "матча"}.get(count % 10, "матчей")


def league_info(
    competition: Competition,
    *,
    upcoming: int,
    complete: bool,
    today: date,
    horizon_days: int = HORIZON_DAYS,
) -> LeagueInfo:
    """Decide whether a league has matches in the next ~6 months.

    - `complete`: the season calendar of this league is cached, so `upcoming` is exact.
    - otherwise a partial count > 0 still proves activity;
    - otherwise the API `currentSeason` dates decide (a finished season is inactive);
    - with no data at all the league stays selectable (we cannot prove it is idle).
    """
    horizon = today + timedelta(days=horizon_days)
    if complete:
        if upcoming > 0:
            return LeagueInfo(competition, upcoming, True, f"{upcoming} {_matches_word(upcoming)}")
        return LeagueInfo(competition, 0, False, "нет матчей в ближайшие 6 месяцев")
    if upcoming > 0:
        return LeagueInfo(competition, upcoming, True, f"от {upcoming} {_matches_word(upcoming)}")
    start, end = competition.season_start, competition.season_end
    if end is not None and end < today:
        return LeagueInfo(competition, 0, False, f"сезон завершён {end:%d.%m.%Y}")
    if start is not None and start > horizon:
        return LeagueInfo(competition, 0, False, f"сезон начнётся {start:%d.%m.%Y}")
    if end is not None:
        return LeagueInfo(competition, None, True, f"сезон до {end:%d.%m.%Y}")
    return LeagueInfo(competition, None, True, "матчи ещё не загружены")


def league_infos(
    competitions: Iterable[Competition],
    counts: Mapping[str, int],
    complete_codes: Iterable[str],
    *,
    today: date,
) -> list[LeagueInfo]:
    complete = set(complete_codes)
    return [
        league_info(
            item,
            upcoming=int(counts.get(item.code, 0)),
            complete=item.code in complete,
            today=today,
        )
        for item in competitions
    ]


def filter_leagues(
    infos: Iterable[LeagueInfo],
    flt: LeagueFilter,
    favorite_codes: Iterable[str] = (),
) -> list[LeagueInfo]:
    needle = flt.query.strip().casefold()
    favorites = {code.upper() for code in favorite_codes}
    picked: list[LeagueInfo] = []
    for info in infos:
        comp = info.competition
        if needle:
            haystack = " ".join(
                part for part in (comp.name, comp.code, area_of(comp), comp.area_code or "") if part
            ).casefold()
            if needle not in haystack:
                continue
        if flt.area and area_of(comp) != flt.area:
            continue
        if flt.league_type is LeagueType.LEAGUE and comp.is_cup:
            continue
        if flt.league_type is LeagueType.CUP and not comp.is_cup:
            continue
        if flt.active_only and not info.active:
            continue
        if flt.favorites_only and comp.code.upper() not in favorites:
            continue
        picked.append(info)
    return picked


def sort_leagues(
    infos: Iterable[LeagueInfo], favorite_codes: Iterable[str] = ()
) -> list[LeagueInfo]:
    """Favourites first, then active before greyed out, then by name."""
    favorites = {code.upper() for code in favorite_codes}
    return sorted(
        infos,
        key=lambda info: (
            info.code.upper() not in favorites,
            not info.active,
            info.competition.name.casefold(),
        ),
    )


def group_leagues(
    infos: Sequence[LeagueInfo],
    grouping: LeagueGrouping,
    favorite_codes: Iterable[str] = (),
) -> list[tuple[str, list[LeagueInfo]]]:
    ordered = sort_leagues(infos, favorite_codes)
    if grouping is LeagueGrouping.NONE:
        return [("", ordered)] if ordered else []
    keyer = area_of if grouping is LeagueGrouping.AREA else type_of
    groups: dict[str, list[LeagueInfo]] = {}
    for info in ordered:
        groups.setdefault(keyer(info.competition), []).append(info)
    return sorted(groups.items(), key=lambda pair: pair[0].casefold())


def areas(infos: Iterable[LeagueInfo]) -> list[str]:
    return sorted({area_of(info.competition) for info in infos}, key=str.casefold)


def group_teams_by_league(
    teams_by_code: Mapping[str, Sequence[Team]],
    competitions: Iterable[Competition],
    codes: Iterable[str] = (),
) -> list[tuple[Competition, list[Team]]]:
    """Teams of the chosen leagues (all cached leagues when `codes` is empty), by league.

    A club that plays in two chosen competitions (league + Champions League) is listed
    under the first one only, so the combobox never shows duplicates.
    """
    wanted = [code.upper() for code in codes]
    known = {item.code.upper(): item for item in competitions}
    order = wanted or sorted(
        teams_by_code, key=lambda code: known.get(code.upper(), Competition(0, code, code)).name
    )
    seen: set[int] = set()
    grouped: list[tuple[Competition, list[Team]]] = []
    for code in order:
        teams = [team for team in teams_by_code.get(code, ()) if team.id not in seen]
        if not teams:
            continue
        seen.update(team.id for team in teams)
        competition = known.get(code.upper(), Competition(0, code, code))
        grouped.append((competition, sorted(teams, key=lambda team: team.name.casefold())))
    return grouped
