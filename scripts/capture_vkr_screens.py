#!/usr/bin/env python3
"""Capture real Flet desktop screenshots for the VKR manuscript.

Writes PNGs under docs/vkr/manuscript/figures/screens/:
  leagues.png, fixtures.png, forecast.png, settings.png

Uses data/samples/ seeded into a temporary SQLite DB so no live API key is required.
Does not print secrets.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

OUT_DIR = ROOT / "docs" / "vkr" / "manuscript" / "figures" / "screens"
SAMPLES = ROOT / "data" / "samples"
TMP_DB = ROOT / "data" / "cache" / "vkr_screens.db"
LOG = ROOT / "data" / "cache" / "vkr_screens_capture.log"


def _log(msg: str) -> None:
    line = f"{datetime.now(UTC).isoformat()} {msg}\n"
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(line)
    print(msg, flush=True)


def seed_sample_db(db_path: Path) -> None:
    from football_prognoz.data.football_data_org import match_from_api
    from football_prognoz.data.store import SQLiteStore
    from football_prognoz.domain.team import Competition, StandingRow
    from football_prognoz.services.matches import current_season_year

    if db_path.exists():
        db_path.unlink()
    store = SQLiteStore(db_path)

    competitions_payload = json.loads((SAMPLES / "competitions.json").read_text(encoding="utf-8"))
    items = [
        Competition(
            id=int(raw.get("id") or 0),
            code=str(raw.get("code") or ""),
            name=str(raw.get("name") or raw.get("code") or ""),
            emblem=raw.get("emblem"),
        )
        for raw in competitions_payload.get("competitions") or []
        if raw.get("code")
    ]
    store.upsert_competitions(items)
    store.mark_fetched("competitions")

    matches_payload = json.loads((SAMPLES / "matches.json").read_text(encoding="utf-8"))
    code = str((matches_payload.get("competition") or {}).get("code") or "PL")
    matches = [match_from_api(raw, code) for raw in matches_payload.get("matches") or []]
    store.upsert_matches(matches)
    season = current_season_year()
    store.mark_fetched(f"matches:{code}:{season}")

    standings_payload = json.loads((SAMPLES / "standings.json").read_text(encoding="utf-8"))
    rows: list[StandingRow] = []
    for table in standings_payload.get("standings") or []:
        if table.get("type") and table.get("type") != "TOTAL":
            continue
        for raw in table.get("table") or []:
            team = raw.get("team") or {}
            rows.append(
                StandingRow(
                    team_id=int(team.get("id") or 0),
                    team_name=str(team.get("name") or "Unknown"),
                    position=int(raw.get("position") or 0),
                    played=int(raw.get("playedGames") or 0),
                    won=int(raw.get("won") or 0),
                    draw=int(raw.get("draw") or 0),
                    lost=int(raw.get("lost") or 0),
                    points=int(raw.get("points") or 0),
                    goals_for=int(raw.get("goalsFor") or 0),
                    goals_against=int(raw.get("goalsAgainst") or 0),
                )
            )
        break
    if rows:
        store.upsert_standings(code, rows)
    _log(f"seeded {db_path.name}: comps={len(items)} matches={len(matches)} standings={len(rows)}")


def prepare_env() -> None:
    # Dummy key so the UI boots into Leagues (not the empty-key Settings gate).
    # Client calls fail and fall back to the seeded SQLite cache — no live API needed.
    os.environ["FOOTBALL_DATA_API_KEY"] = "vkr-screenshot-offline"
    os.environ["OPENAI_API_KEY"] = ""
    os.environ["DATABASE_PATH"] = str(TMP_DB.relative_to(ROOT))
    os.environ["PREFETCH_WAIT_ON_START"] = "false"
    os.environ["SHOW_AI_BLOCK"] = "false"
    os.environ["COMPACT_FIXTURES"] = "false"


async def wait_until(predicate, timeout: float = 45.0, interval: float = 0.25) -> bool:
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(interval)
    return False


async def snap(page, path: Path) -> None:
    data = await page.take_screenshot(pixel_ratio=2, delay=200)
    path.write_bytes(data if isinstance(data, (bytes, bytearray)) else bytes(data))
    _log(f"wrote {path.name} ({path.stat().st_size} bytes)")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if LOG.exists():
        LOG.unlink()
    prepare_env()
    seed_sample_db(TMP_DB)

    import flet as ft
    from football_prognoz.config import load_settings
    from football_prognoz.ui.app import build_service, start_ui

    settings = load_settings()
    service = build_service(settings)
    holder: dict[str, object] = {}

    async def capture_flow(page: ft.Page) -> None:
        try:
            page.enable_screenshots = True
            app = start_ui(page, service=service, settings=settings)
            holder["app"] = app

            ok = await wait_until(lambda: not app.booting, timeout=60.0)
            if not ok:
                raise RuntimeError("boot timed out")
            await asyncio.sleep(0.8)

            # 1) Leagues
            app._goto("leagues")
            await asyncio.sleep(0.6)
            await snap(page, OUT_DIR / "leagues.png")

            # 2) Fixtures — select PL from seeded competitions
            pl = next((c for c in app.competitions if c.code == "PL"), None)
            if pl is None and app.competitions:
                pl = app.competitions[0]
            if pl is None:
                raise RuntimeError("no competitions after boot")
            app._select_league(pl)
            ok = await wait_until(
                lambda: not app.loading and app.busy is None and bool(app.matches),
                timeout=45.0,
            )
            if not ok:
                raise RuntimeError(f"fixtures load failed: matches={len(app.matches)} err={app.error}")
            app._goto("fixtures")
            await asyncio.sleep(0.8)
            await snap(page, OUT_DIR / "fixtures.png")

            # 3) Forecast — prefer scheduled match, else first match
            match = next((m for m in app.matches if m.status.name == "SCHEDULED"), None)
            if match is None:
                match = app.matches[0]
            app._open_match(match)
            ok = await wait_until(
                lambda: app.forecast is not None and not app.loading,
                timeout=45.0,
            )
            if not ok:
                raise RuntimeError(f"forecast failed: err={app.error}")
            app._goto("match")
            await asyncio.sleep(0.8)
            await snap(page, OUT_DIR / "forecast.png")

            # 4) Settings
            app._goto("settings")
            await asyncio.sleep(0.6)
            await snap(page, OUT_DIR / "settings.png")

            holder["ok"] = True
        except Exception:
            holder["error"] = traceback.format_exc()
            _log(holder["error"])
        finally:
            try:
                await page.window.close()
            except Exception:
                try:
                    page.window.destroy()
                except Exception:
                    pass

    def target(page: ft.Page) -> None:
        page.run_task(capture_flow, page)

    run = getattr(ft, "run", None)
    if callable(run):
        run(target)
    else:
        ft.app(target=target, view=ft.AppView.FLET_APP)

    if not holder.get("ok"):
        raise SystemExit(holder.get("error") or "capture failed")
    for name in ("leagues.png", "fixtures.png", "forecast.png", "settings.png"):
        path = OUT_DIR / name
        if not path.exists() or path.stat().st_size < 1000:
            raise SystemExit(f"missing or tiny file: {path}")
    _log("all screens captured")


if __name__ == "__main__":
    main()
