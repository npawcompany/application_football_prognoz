from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from football_prognoz.config import Settings, load_settings, write_env_value
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


def test_favorite_team_ids_parses_unique_ints() -> None:
    settings = Settings(favorite_teams=" 57, 57, abc, 64 ,")
    assert settings.favorite_team_ids() == [57, 64]
    assert Settings(favorite_teams="").favorite_team_ids() == []


def test_current_season_year_flips_in_july() -> None:
    assert current_season_year(datetime(2026, 6, 1, tzinfo=UTC)) == 2025
    assert current_season_year(datetime(2026, 7, 1, tzinfo=UTC)) == 2026


def test_load_settings_picks_up_env_created_after_startup(tmp_path: Path, monkeypatch) -> None:
    """Regression: .env missing at import time must still be read after a save."""
    env = tmp_path / ".env"
    monkeypatch.setattr("football_prognoz.config.ENV_PATH", env)
    for name in ("FOOTBALL_DATA_API_KEY", "OLLAMA_API_KEY", "API_FOOTBALL_KEY"):
        monkeypatch.delenv(name, raising=False)
    assert not env.exists()
    assert load_settings().football_data_api_key == ""
    write_env_value("FOOTBALL_DATA_API_KEY", "fd-key")
    write_env_value("OLLAMA_API_KEY", "ol-key")
    write_env_value("API_FOOTBALL_KEY", "af-key")
    settings = load_settings()
    assert env.exists()
    assert settings.football_data_api_key == "fd-key"
    assert settings.has_ollama_key
    assert settings.has_api_football_key
    write_env_value("OLLAMA_MODEL", "gpt-oss:120b")
    assert load_settings().ollama_model == "gpt-oss:120b"


def test_ollama_defaults_and_llm_configured(monkeypatch) -> None:
    for name in ("OLLAMA_API_KEY", "OLLAMA_HOST", "OLLAMA_MODEL"):
        monkeypatch.delenv(name, raising=False)
    base = Settings(_env_file=None)  # type: ignore[call-arg]
    assert base.ollama_host == "https://ollama.com"
    assert base.ollama_model == "deepseek-v4.1-flash"
    assert base.ollama_fallback_model == "gpt-oss:120b"
    assert base.is_ollama_cloud
    assert base.llm_configured is False  # cloud without a key
    assert Settings(_env_file=None, ollama_api_key="k").llm_configured is True  # type: ignore[call-arg]
    local = Settings(_env_file=None, ollama_host="http://127.0.0.1:11434/")  # type: ignore[call-arg]
    assert local.is_ollama_cloud is False
    assert local.llm_configured is True
    assert local.ollama_base_url == "http://127.0.0.1:11434"


def test_legacy_openai_keys_in_env_are_ignored(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    env = tmp_path / ".env"
    env.write_text("OPENAI_API_KEY=old\nOPENAI_MODEL=gpt-4o-mini\n", encoding="utf-8")
    settings = load_settings(env)
    assert not hasattr(settings, "openai_api_key")
    assert settings.has_ollama_key is False
    assert settings.llm_configured is False


def test_app_home_prefers_override_then_checkout_then_flet_storage(tmp_path: Path) -> None:
    from football_prognoz.config import resolve_app_home

    checkout = tmp_path / "repo"
    checkout.mkdir()
    (checkout / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    custom = tmp_path / "custom"
    assert resolve_app_home(env={"FOOTBALL_PROGNOZ_HOME": str(custom)}, root_dir=checkout) == custom
    assert resolve_app_home(env={}, root_dir=checkout) == checkout
    storage = tmp_path / "storage"
    flet_env = {"FLET_APP_STORAGE_DATA": str(storage)}
    assert resolve_app_home(env=flet_env, root_dir=bundle) == storage
    fallback = resolve_app_home(env={}, root_dir=bundle)
    assert fallback.name == "FootballPrognoz"


def test_relative_database_path_resolves_against_app_home() -> None:
    from football_prognoz.config import APP_HOME, Settings

    settings = Settings(_env_file=None, database_path="data/cache/x.db")  # type: ignore[call-arg]
    assert settings.db_path == APP_HOME / "data" / "cache" / "x.db"


def test_assets_live_under_src_for_flet_build() -> None:
    from football_prognoz.config import ASSETS_DIR, SRC_DIR

    assert ASSETS_DIR == SRC_DIR / "assets"
    assert (ASSETS_DIR / "crests" / "manifest.json").is_file()
