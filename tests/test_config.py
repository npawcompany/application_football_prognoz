from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from football_prognoz.config import write_env_value
from football_prognoz.services.matches import current_season_year


def test_write_env_value_updates_without_dropping_keys(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text("FOO=1\nBAR=2\n", encoding="utf-8")
    write_env_value("BAR", "9", path=path)
    write_env_value("BAZ", "3", path=path)
    text = path.read_text(encoding="utf-8")
    assert "FOO=1" in text
    assert "BAR=9" in text
    assert "BAZ=3" in text


def test_current_season_year_flips_in_july() -> None:
    assert current_season_year(datetime(2026, 6, 1, tzinfo=timezone.utc)) == 2025
    assert current_season_year(datetime(2026, 7, 1, tzinfo=timezone.utc)) == 2026
