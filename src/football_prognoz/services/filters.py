"""Pure in-memory list filters. No I/O, HTTP, or UI."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import TypeVar

C = TypeVar("C")
M = TypeVar("M")


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


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
    moment = _aware_utc(now if now is not None else datetime.now(UTC))
    needle = team_query.strip().casefold()
    matched: list[M] = []
    for item in items:
        if upcoming_only:
            status = getattr(item, "status", None)
            is_upcoming = getattr(status, "is_upcoming", None)
            if not callable(is_upcoming) or not is_upcoming():
                continue
            utc_date = getattr(item, "utc_date", None)
            if not isinstance(utc_date, datetime) or _aware_utc(utc_date) < moment:
                continue
        if needle:
            home = str(getattr(item, "home_name", "")).casefold()
            away = str(getattr(item, "away_name", "")).casefold()
            if needle not in home and needle not in away:
                continue
        matched.append(item)
    return matched
