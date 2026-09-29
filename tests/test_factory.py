from __future__ import annotations

from pathlib import Path

from football_prognoz.config import Settings
from football_prognoz.services import factory
from football_prognoz.services.factory import build_llm, build_service


def _settings(tmp_path: Path, **kwargs) -> Settings:
    values = {"football_data_api_key": "fd", "database_path": str(tmp_path / "db.sqlite")}
    values.update(kwargs)
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


def test_llm_built_only_when_configured(tmp_path: Path) -> None:
    assert build_llm(_settings(tmp_path)) is None
    cloud = build_llm(_settings(tmp_path, ollama_api_key="k"))
    assert cloud is not None
    assert cloud.host == "https://ollama.com"
    assert cloud.model == "deepseek-v4.1-flash"
    assert cloud.fallback_model == "gpt-oss:120b"
    local = build_llm(_settings(tmp_path, ollama_host="http://127.0.0.1:11434"))
    assert local is not None and local.host == "http://127.0.0.1:11434"


def test_rebuild_shares_rate_limiter_and_closes_clients(tmp_path: Path) -> None:
    first = build_service(_settings(tmp_path))
    second = build_service(_settings(tmp_path, ollama_api_key="k", api_football_key="af"))
    assert first._client._limiter is factory.FOOTBALL_DATA_LIMITER  # noqa: SLF001
    assert second._client._limiter is factory.FOOTBALL_DATA_LIMITER  # noqa: SLF001
    assert first.llm_enabled is False and first.player_status_enabled is False
    assert second.llm_enabled is True and second.player_status_enabled is True
    first.close()
    assert first._client._client.is_closed  # noqa: SLF001
    second.close()
    assert second._client._client.is_closed  # noqa: SLF001
