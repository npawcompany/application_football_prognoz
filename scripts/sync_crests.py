#!/usr/bin/env python3
"""Download official football-data.org crests into assets/crests/.

Live HTTP is allowed only in this script (not from the UI). Uses
FootballDataOrgClient + RateLimiter (10 req/min). The API key is read from
`.env` (FOOTBALL_DATA_API_KEY) and is never logged.
"""

from __future__ import annotations

import json
import re
import sys
import time
import unicodedata
from pathlib import Path

import httpx
from dotenv import load_dotenv

from football_prognoz.config import ENV_PATH, ROOT_DIR, load_settings
from football_prognoz.data import FREE_COMPETITIONS
from football_prognoz.data.football_data_org import (
    API_BASE,
    FootballDataError,
    FootballDataOrgClient,
    RateLimiter,
)
from football_prognoz.domain.team import Team

CREST_CDN = "https://crests.football-data.org"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
ASSETS_DIR = ROOT_DIR / "assets" / "crests"
FREE_CODES_ORDERED = tuple(item.code for item in FREE_COMPETITIONS)
COMPETITION_IDS = {item.code: item.id for item in FREE_COMPETITIONS}


def team_slug(team: Team) -> str:
    source = team.short_name or team.name or str(team.id)
    ascii_text = unicodedata.normalize("NFKD", source).encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^a-z0-9]+", "", ascii_text.lower())
    return cleaned or str(team.id)


def is_png(path: Path) -> bool:
    return path.is_file() and path.read_bytes()[:8] == PNG_MAGIC


def league_urls(code: str) -> list[str]:
    urls = [f"{CREST_CDN}/{code}.png"]
    competition_id = COMPETITION_IDS.get(code)
    if competition_id:
        id_url = f"{CREST_CDN}/{competition_id}.png"
        if id_url not in urls:
            urls.append(id_url)
    return urls


def fetch_png(client: httpx.Client, url: str, dest: Path) -> tuple[bool, int]:
    """Write dest when the body is a PNG. Returns (written, http_status)."""
    response = client.get(url)
    status = response.status_code
    if status == 404:
        return False, 404
    if status >= 400:
        print(f"skip {url} (HTTP {status})")
        return False, status
    body = response.content
    if not body.startswith(PNG_MAGIC):
        print(f"skip {url} (not png)")
        return False, status
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(body)
    return True, status


def list_teams_retry(client: FootballDataOrgClient, code: str) -> list[Team]:
    try:
        return client.list_teams(code)
    except FootballDataError as exc:
        if exc.status_code == 429:
            print(f"429 on {code}; waiting 60s")
            time.sleep(60)
            return client.list_teams(code)
        print(f"skip teams {code}: HTTP {exc.status_code}")
        return []


def existing_team_files() -> dict[int, str]:
    """Map team id → relative path from already bundled PNGs."""
    found: dict[int, str] = {}
    team_dir = ASSETS_DIR / "teams"
    if not team_dir.exists():
        return found
    for path in team_dir.glob("*.png"):
        team_id_text = path.stem.split("-", 1)[0]
        if team_id_text.isdigit():
            found[int(team_id_text)] = f"teams/{path.name}"
    return found


def write_manifest(
    leagues: dict[str, str],
    teams: dict[str, str],
    missing_leagues: list[str],
    missing_teams: list[str],
) -> Path:
    manifest = {
        "source": f"{CREST_CDN}/",
        "leagues": leagues,
        "teams": teams,
        "missing": {
            "leagues": missing_leagues,
            "teams": missing_teams,
        },
    }
    path = ASSETS_DIR / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        f"manifest {path}: {len(leagues)} league PNGs, {len(teams)} team PNGs, "
        f"missing leagues={missing_leagues}, missing teams={len(missing_teams)}"
    )
    return path


def sync() -> int:
    load_dotenv(ENV_PATH)
    settings = load_settings()
    api_key = settings.football_data_api_key.strip()
    has_key = bool(api_key)
    if not has_key:
        print("No FOOTBALL_DATA_API_KEY in .env — skip GET /competitions and /teams.")
        print(
            "League emblems still download from the official CDN. "
            "Copy .env.example to .env to sync all clubs."
        )

    leagues: dict[str, str] = {}
    teams: dict[str, str] = {}
    missing_leagues: list[str] = []
    missing_teams: list[str] = []
    unique: dict[int, Team] = {}

    (ASSETS_DIR / "leagues").mkdir(parents=True, exist_ok=True)
    (ASSETS_DIR / "teams").mkdir(parents=True, exist_ok=True)

    if has_key:
        limiter = RateLimiter(max_per_minute=10)
        with httpx.Client(base_url=API_BASE, timeout=20.0, follow_redirects=True) as api_http:
            api = FootballDataOrgClient(api_key, client=api_http, limiter=limiter)
            competitions = api.list_competitions()
            print(f"competitions listed: {len(competitions)}")
            for code in FREE_CODES_ORDERED:
                found = list_teams_retry(api, code)
                print(f"teams {code}: {len(found)}")
                for team in found:
                    unique[team.id] = team

    with httpx.Client(timeout=30.0, follow_redirects=True) as cdn:
        for code in FREE_CODES_ORDERED:
            rel = f"leagues/{code}.png"
            dest = ASSETS_DIR / rel
            written = False
            status = 404
            for url in league_urls(code):
                written, status = fetch_png(cdn, url, dest)
                if written:
                    print(f"wrote {rel} from {url}")
                    break
            if written or is_png(dest):
                leagues[code] = rel
                if not written:
                    print(f"kept bundled {rel}")
            else:
                missing_leagues.append(code)
                print(f"missing league {code} (HTTP {status})")

        if unique:
            for team_id, team in sorted(unique.items()):
                slug = team_slug(team)
                rel = f"teams/{team_id}-{slug}.png"
                written, status = fetch_png(cdn, f"{CREST_CDN}/{team_id}.png", ASSETS_DIR / rel)
                if written:
                    teams[str(team_id)] = rel
                else:
                    missing_teams.append(str(team_id))
                    if status == 404:
                        print(f"missing team {team_id} (404)")
        else:
            for team_id, rel in sorted(existing_team_files().items()):
                dest = ASSETS_DIR / rel
                written, status = fetch_png(cdn, f"{CREST_CDN}/{team_id}.png", dest)
                if written:
                    teams[str(team_id)] = rel
                elif is_png(dest):
                    teams[str(team_id)] = rel
                else:
                    missing_teams.append(str(team_id))
                    if status == 404:
                        print(f"missing team {team_id} (404)")

    write_manifest(leagues, teams, missing_leagues, missing_teams)
    return 0 if has_key else 1


def main() -> None:
    sys.exit(sync())


if __name__ == "__main__":
    main()
