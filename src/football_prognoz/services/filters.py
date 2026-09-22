"""Pure in-memory list filters. No I/O, HTTP, or UI."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from math import ceil
from typing import TypeVar

C = TypeVar("C")
M = TypeVar("M")
T = TypeVar("T")

PAGE_SIZE = 25

_LIVE_STATUSES = frozenset({"IN_PLAY", "PAUSED"})
_FINISHED_STATUSES = frozenset({"FINISHED", "AWARDED"})
_UPCOMING_STATUSES = frozenset({"SCHEDULED", "TIMED"})


class MatchStatusFilter(StrEnum):
    UPCOMING = "upcoming"
    LIVE = "live"
    FINISHED = "finished"
    ALL = "all"


class DateWindow(StrEnum):
    ANY = "any"
    TODAY = "today"
    DAYS_7 = "days_7"
    DAYS_30 = "days_30"


class MatchSort(StrEnum):
    DATE_ASC = "date_asc"
    DATE_DESC = "date_desc"
    MATCHDAY = "matchday"
    HOME = "home"
    AWAY = "away"
    STATUS = "status"


@dataclass(frozen=True)
class FixtureQuery:
    team_query: str = ""
    status: MatchStatusFilter = MatchStatusFilter.UPCOMING
    date_window: DateWindow = DateWindow.ANY
    matchday: int | None = None
    sort: MatchSort = MatchSort.DATE_ASC
    page: int = 0
    page_size: int = PAGE_SIZE


@dataclass(frozen=True)
class PageResult:
    items: list
    total: int
    page: int
    page_size: int

    @property
    def page_count(self) -> int:
        if self.total <= 0 or self.page_size <= 0:
            return 1
        return max(1, ceil(self.total / self.page_size))


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _status_token(item: object) -> str:
    status = getattr(item, "status", None)
    if status is None:
        return ""
    value = getattr(status, "value", None)
    if isinstance(value, str):
        return value
    return str(status)


def _utc_date(item: object) -> datetime | None:
    utc_date = getattr(item, "utc_date", None)
    if not isinstance(utc_date, datetime):
        return None
    return _aware_utc(utc_date)


def _matches_status(item: object, status_filter: MatchStatusFilter, now: datetime) -> bool:
    if status_filter is MatchStatusFilter.ALL:
        return True

    status = getattr(item, "status", None)
    if status_filter is MatchStatusFilter.UPCOMING:
        is_upcoming = getattr(status, "is_upcoming", None)
        if callable(is_upcoming):
            if not is_upcoming():
                return False
        elif _status_token(item) not in _UPCOMING_STATUSES:
            return False
        moment = _utc_date(item)
        return moment is not None and moment >= now

    if status_filter is MatchStatusFilter.LIVE:
        return _status_token(item) in _LIVE_STATUSES

    if status_filter is MatchStatusFilter.FINISHED:
        is_finished = getattr(status, "is_finished", None)
        if callable(is_finished):
            return bool(is_finished())
        return _status_token(item) in _FINISHED_STATUSES

    return True


def _in_date_window(item: object, query: FixtureQuery, now: datetime) -> bool:
    if query.date_window is DateWindow.ANY:
        return True
    moment = _utc_date(item)
    if moment is None:
        return False
    if query.date_window is DateWindow.TODAY:
        return moment.date() == now.date()
    days = 7 if query.date_window is DateWindow.DAYS_7 else 30
    delta = timedelta(days=days)
    if query.status is MatchStatusFilter.FINISHED:
        return now - delta <= moment <= now
    return now <= moment <= now + delta


def _matches_team(item: object, needle: str) -> bool:
    if not needle:
        return True
    home = str(getattr(item, "home_name", "")).casefold()
    away = str(getattr(item, "away_name", "")).casefold()
    return needle in home or needle in away


def _matchday_sort_key(item: object) -> tuple[int, int]:
    matchday = getattr(item, "matchday", None)
    if matchday is None:
        return (1, 0)
    return (0, int(matchday))


def sort_matches(items: Sequence[T], key: MatchSort) -> list[T]:
    """DATE_ASC keeps store order; DATE_DESC reverses it. Other keys sort explicitly."""
    ordered = list(items)
    if key is MatchSort.DATE_ASC:
        return ordered
    if key is MatchSort.DATE_DESC:
        ordered.reverse()
        return ordered
    if key is MatchSort.MATCHDAY:
        return sorted(ordered, key=_matchday_sort_key)
    if key is MatchSort.HOME:
        return sorted(ordered, key=lambda item: str(getattr(item, "home_name", "")).casefold())
    if key is MatchSort.AWAY:
        return sorted(ordered, key=lambda item: str(getattr(item, "away_name", "")).casefold())
    if key is MatchSort.STATUS:
        return sorted(ordered, key=_status_token)
    return ordered


def paginate(items: Sequence[T], page: int, page_size: int) -> PageResult:
    selected = list(items)
    total = len(selected)
    size = page_size if page_size > 0 else PAGE_SIZE
    page_count = max(1, ceil(total / size)) if total else 1
    clamped = min(max(page, 0), page_count - 1)
    start = clamped * size
    return PageResult(
        items=selected[start : start + size],
        total=total,
        page=clamped,
        page_size=size,
    )


def apply_fixture_query(
    items: Sequence[T],
    query: FixtureQuery,
    now: datetime | None = None,
) -> PageResult:
    moment = _aware_utc(now if now is not None else datetime.now(UTC))
    needle = query.team_query.strip().casefold()
    matched: list[T] = []
    for item in items:
        if not _matches_status(item, query.status, moment):
            continue
        if not _in_date_window(item, query, moment):
            continue
        if query.matchday is not None and getattr(item, "matchday", None) != query.matchday:
            continue
        if not _matches_team(item, needle):
            continue
        matched.append(item)
    return paginate(sort_matches(matched, query.sort), query.page, query.page_size)


def filter_competitions(items: Sequence[C], query: str) -> list[C]:
    needle = query.strip().casefold()
    if not needle:
        return list(items)
    matched: list[C] = []
    for item in items:
        name = str(getattr(item, "name", "")).casefold()
        code = str(getattr(item, "code", "")).casefold()
        if needle in name or needle in code:
            matched.append(item)
    return matched


def filter_matches(
    items: Sequence[M],
    *,
    team_query: str = "",
    upcoming_only: bool = True,
    now: datetime | None = None,
) -> list[M]:
    result = apply_fixture_query(
        items,
        FixtureQuery(
            team_query=team_query,
            status=MatchStatusFilter.UPCOMING if upcoming_only else MatchStatusFilter.ALL,
            page=0,
            page_size=max(len(items), 1),
        ),
        now=now,
    )
    return list(result.items)
