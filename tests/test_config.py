from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from football_prognoz.config import Settings, write_env_value
from football_prognoz.services.matches import current_season_year


def test_write_env_value_updates_without_dropping_keys(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text("FOO=1\nBAR=2\nFAVORITE_LEAGUES=PL\n", encoding="utf-8")
    write_env_value("BAR", "9", path=path)
    write_env_value("BAZ", "3", path=path)
    write_env_value("PREFETCH_WAIT_ON_START", "true", path=path)
    write_env_value("FAVORITE_LEAGUES", "PL,PD", path=path)
    text = path.read_text(encoding="utf-8")
    assert "FOO=1" in text
    assert "BAR=9" in text
    assert "BAZ=3" in text
    assert "FAVORITE_LEAGUES=PL,PD" in text
    assert "PREFETCH_WAIT_ON_START=true" in text
    assert text.count("FAVORITE_LEAGUES=") == 1


def test_favorite_codes_splits_strips_and_uppercases() -> None:
    settings = Settings(favorite_leagues=" pl, pd ,, sa ")
    assert settings.favorite_codes() == ["PL", "PD", "SA"]


def test_favorite_codes_drops_empty() -> None:
    assert Settings(favorite_leagues="").favorite_codes() == []
    assert Settings(favorite_leagues="  , , ").favorite_codes() == []
    assert Settings(favorite_leagues="bl1").favorite_codes() == ["BL1"]


def test_current_season_year_flips_in_july() -> None:
    assert current_season_year(datetime(2026, 6, 1, tzinfo=UTC)) == 2025
    assert current_season_year(datetime(2026, 7, 1, tzinfo=UTC)) == 2026
