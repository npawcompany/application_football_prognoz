from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]
ENV_PATH = ROOT_DIR / ".env"

OLLAMA_CLOUD_HOST = "https://ollama.com"
DEFAULT_OLLAMA_MODEL = "deepseek-v4.1-flash"
DEFAULT_OLLAMA_FALLBACK_MODEL = "gpt-oss:120b"


class Settings(BaseSettings):
    # env_file is always set: pydantic-settings skips a missing file and re-reads it on
    # every instantiation, so a .env created after startup is picked up by load_settings().
    model_config = SettingsConfigDict(
        env_file=ENV_PATH,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    football_data_api_key: str = ""
    ollama_api_key: str = ""
    ollama_host: str = OLLAMA_CLOUD_HOST
    ollama_model: str = DEFAULT_OLLAMA_MODEL
    ollama_fallback_model: str = DEFAULT_OLLAMA_FALLBACK_MODEL
    api_football_key: str = ""
    gnews_api_key: str = ""
    news_rss_enabled: bool = True
    database_path: str = "data/cache/prognoz.db"
    favorite_leagues: str = ""  # comma-separated codes e.g. PL,PD
    favorite_teams: str = ""  # comma-separated football-data.org team ids
    prefetch_wait_on_start: bool = False
    show_ai_block: bool = True
    compact_fixtures: bool = False
    system_notifications: bool = False

    @property
    def db_path(self) -> Path:
        path = Path(self.database_path)
        if not path.is_absolute():
            path = ROOT_DIR / path
        return path

    def favorite_codes(self) -> list[str]:
        """Split/strip/upper favorite league codes; drop empty parts."""
        return [part.strip().upper() for part in self.favorite_leagues.split(",") if part.strip()]

    def favorite_team_ids(self) -> list[int]:
        """Parse favorite team ids from the comma-separated FAVORITE_TEAMS value."""
        ids: list[int] = []
        seen: set[int] = set()
        for part in self.favorite_teams.split(","):
            text = part.strip()
            if not text.isdigit():
                continue
            team_id = int(text)
            if team_id in seen:
                continue
            seen.add(team_id)
            ids.append(team_id)
        return ids

    @property
    def has_football_key(self) -> bool:
        return bool(self.football_data_api_key.strip())

    @property
    def has_ollama_key(self) -> bool:
        return bool(self.ollama_api_key.strip())

    @property
    def ollama_base_url(self) -> str:
        host = self.ollama_host.strip() or OLLAMA_CLOUD_HOST
        return host.rstrip("/")

    @property
    def is_ollama_cloud(self) -> bool:
        """True when OLLAMA_HOST points at ollama.com (the key is mandatory there)."""
        hostname = (urlparse(self.ollama_base_url).hostname or "").lower()
        return hostname == "ollama.com" or hostname.endswith(".ollama.com")

    @property
    def llm_configured(self) -> bool:
        """Cloud needs OLLAMA_API_KEY; a local/self-hosted OLLAMA_HOST works without it."""
        if not (self.ollama_model.strip() or self.ollama_fallback_model.strip()):
            return False
        return self.has_ollama_key or not self.is_ollama_cloud

    @property
    def has_api_football_key(self) -> bool:
        return bool(self.api_football_key.strip())

    @property
    def has_gnews_key(self) -> bool:
        return bool(self.gnews_api_key.strip())

    @property
    def news_enabled(self) -> bool:
        return self.has_gnews_key or self.news_rss_enabled


def load_settings(env_file: Path | None = None) -> Settings:
    """Read settings from the environment and the .env file as it is *now*."""
    path = env_file if env_file is not None else ENV_PATH
    return Settings(_env_file=path)  # type: ignore[call-arg]


def write_env_value(key: str, value: str, path: Path | None = None) -> None:
    """Update a single KEY=value in .env without dropping other keys."""
    path = path if path is not None else ENV_PATH
    lines: list[str] = []
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()
    found = False
    out: list[str] = []
    prefix = f"{key}="
    for line in lines:
        if line.startswith(prefix) or line.startswith(f"{key} ="):
            out.append(f"{key}={value}")
            found = True
        else:
            out.append(line)
    if not found:
        if out and out[-1] != "":
            out.append("")
        out.append(f"{key}={value}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
