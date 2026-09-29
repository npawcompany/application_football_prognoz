from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import urlparse

from pydantic_settings import BaseSettings, SettingsConfigDict

PACKAGE_DIR = Path(__file__).resolve().parent
SRC_DIR = PACKAGE_DIR.parent
ROOT_DIR = SRC_DIR.parent  # repository root in a checkout; meaningless inside a built app
APP_NAME = "FootballPrognoz"
HOME_ENV = "FOOTBALL_PROGNOZ_HOME"


def _find_assets() -> Path:
    # `flet build` bundles `<app path>/assets` (app path = "src"); a checkout has the same.
    for candidate in (SRC_DIR / "assets", ROOT_DIR / "assets"):
        if candidate.is_dir():
            return candidate
    return SRC_DIR / "assets"


def _user_data_dir() -> Path:
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / APP_NAME


def resolve_app_home(*, env: dict[str, str] | None = None, root_dir: Path | None = None) -> Path:
    """Folder for .env, the SQLite cache and exports.

    1. FOOTBALL_PROGNOZ_HOME, if set;
    2. the repository root when running from a checkout (pyproject.toml next to src/);
    3. FLET_APP_STORAGE_DATA inside a `flet build` app (writable per-app storage);
    4. the OS user data folder (APPDATA / Application Support / XDG_DATA_HOME).
    """
    values = os.environ if env is None else env
    root = ROOT_DIR if root_dir is None else root_dir
    override = (values.get(HOME_ENV) or "").strip()
    if override:
        return Path(override).expanduser()
    if (root / "pyproject.toml").is_file():
        return root
    storage = (values.get("FLET_APP_STORAGE_DATA") or "").strip()
    if storage:
        return Path(storage)
    return _user_data_dir()


ASSETS_DIR = _find_assets()
APP_HOME = resolve_app_home()
EXPORTS_DIR = APP_HOME / "data" / "exports"  # forecast history CSV (git-ignored)
ENV_PATH = APP_HOME / ".env"

OLLAMA_CLOUD_HOST = "https://ollama.com"
# Free Ollama accounts only get "starter models"; ollama.com does not publish that list
# (docs/DATA_SOURCES.md, Ollama). gpt-oss is the documented safe choice.
DEFAULT_OLLAMA_MODEL = "gpt-oss:120b"
DEFAULT_OLLAMA_FALLBACK_MODEL = "gpt-oss:20b"
# Tried after OLLAMA_MODEL and OLLAMA_FALLBACK_MODEL when ollama.com answers 402/403-plan.
FREE_OLLAMA_MODELS = ("gpt-oss:120b", "gpt-oss:20b")
# `GET https://ollama.com/api/tags`, 2026-09-30. (name, note shown in Settings)
KNOWN_OLLAMA_MODELS: tuple[tuple[str, str], ...] = (
    ("gpt-oss:120b", "бесплатный тариф (по умолчанию)"),
    ("gpt-oss:20b", "бесплатный тариф, быстрее"),
    ("gemma4:31b", "может требовать кредиты"),
    ("nemotron-3-super", "может требовать кредиты"),
    ("nemotron-3-nano:30b", "может требовать кредиты"),
    ("deepseek-v4.1-flash", "платно (кредиты)"),
    ("deepseek-v4-pro:0813", "платно (кредиты)"),
    ("glm-5.3-flash", "платно (кредиты)"),
    ("glm-5.3", "платно (кредиты)"),
    ("glm-5.2", "платно (кредиты)"),
    ("minimax-m3", "платно (кредиты)"),
    ("minimax-m2.7", "платно (кредиты)"),
    ("mistral-large-3:675b", "платно (кредиты)"),
    ("kimi-k2.6", "платно (кредиты)"),
    ("kimi-k3", "платно (кредиты)"),
    ("nemotron-3-ultra", "платно (кредиты)"),
)


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
            path = APP_HOME / path
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
