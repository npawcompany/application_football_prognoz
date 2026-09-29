"""Format kickoff instants in the OS timezone of the running app."""

from __future__ import annotations

from datetime import UTC, datetime, tzinfo


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def to_local(value: datetime, *, tz: tzinfo | None = None) -> datetime:
    """Convert a stored UTC (or aware) instant to the app host timezone."""
    moment = _aware(value)
    if tz is not None:
        return moment.astimezone(tz)
    return moment.astimezone()


def format_kickoff_date(value: datetime, *, tz: tzinfo | None = None) -> str:
    return to_local(value, tz=tz).strftime("%d.%m.%Y")


def format_kickoff_time(value: datetime, *, tz: tzinfo | None = None) -> str:
    local = to_local(value, tz=tz)
    zone = local.tzname() or ""
    clock = local.strftime("%H:%M")
    return f"{clock} {zone}".strip()


def format_kickoff(value: datetime, *, tz: tzinfo | None = None) -> str:
    local = to_local(value, tz=tz)
    zone = local.tzname() or ""
    stamp = local.strftime("%d.%m.%Y %H:%M")
    return f"{stamp} {zone}".strip()
