from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from football_prognoz.ui.formatters import format_kickoff, format_kickoff_date, format_kickoff_time
from football_prognoz.ui.theme import scaled, type_scale


def test_moscow_converts_utc_noon_to_1500() -> None:
    utc = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
    moscow = ZoneInfo("Europe/Moscow")
    assert format_kickoff_time(utc, tz=moscow).startswith("15:00")
    assert "UTC" not in format_kickoff(utc, tz=moscow)
    assert format_kickoff_date(utc, tz=moscow) == "02.10.2026"


def test_date_digits_are_ascii() -> None:
    utc = datetime(2026, 9, 28, 23, 0, tzinfo=UTC)
    text = format_kickoff(utc, tz=ZoneInfo("Europe/Moscow"))
    assert "28.09.2026" in text or "29.09.2026" in text
    assert all(ch.isascii() for ch in text if ch.isdigit())


def test_type_scale_grows_with_width() -> None:
    assert type_scale(800) < type_scale(1440) < type_scale(1600)
    assert scaled(20, 800) <= scaled(20, 1440)
    assert scaled(10, 800) >= 10
