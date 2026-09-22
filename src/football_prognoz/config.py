from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]
ENV_PATH = ROOT_DIR / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_PATH if ENV_PATH.exists() else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    football_data_api_key: str = ""
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = "https://api.openai.com/v1"
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
    def has_openai_key(self) -> bool:
        return bool(self.openai_api_key.strip())


def load_settings() -> Settings:
    return Settings()


def write_env_value(key: str, value: str, path: Path = ENV_PATH) -> None:
    """Update a single KEY=value in .env without dropping other keys."""
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
