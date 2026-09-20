"""Official competition and club marks.

Runtime prefers the football-data.org `emblem` / `crest` URL (the same files
the API serves). Bundled PNGs from assets/crests/manifest.json are the
offline fallback. Missing codes use a colour placeholder from LEAGUE_COLORS.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import flet as ft

from football_prognoz.config import ROOT_DIR
from football_prognoz.ui.theme import FG, MUTED, SURFACE

LEAGUE_COLORS: dict[str, str] = {
    "PL": "#3D195B",
    "PD": "#EE2524",
    "SA": "#024494",
    "BL1": "#D20515",
    "FL1": "#091C3E",
    "PPL": "#0054A6",
    "DED": "#F36C21",
    "ELC": "#1D4A9E",
    "BSA": "#009739",
    "CL": "#0A1E6F",
    "WC": "#326295",
    "EC": "#003399",
}

ASSET_PREFIX = "/crests"
DEFAULT_MANIFEST = ROOT_DIR / "assets" / "crests" / "manifest.json"

_manifest: dict[str, Any] | None = None
_manifest_path: Path | None = None


def reset_crest_manifest() -> None:
    global _manifest, _manifest_path
    _manifest = None
    _manifest_path = None


def load_crest_manifest(path: Path | None = None, *, force: bool = False) -> dict[str, Any]:
    global _manifest, _manifest_path
    if not force and _manifest is not None and (path is None or _manifest_path == path):
        return _manifest
    target = path or DEFAULT_MANIFEST
    if not target.is_file():
        _manifest = {"leagues": {}, "teams": {}, "missing": []}
        _manifest_path = target
        return _manifest
    raw = json.loads(target.read_text(encoding="utf-8"))
    _manifest = raw if isinstance(raw, dict) else {"leagues": {}, "teams": {}}
    _manifest_path = target
    return _manifest


def _missing_codes(manifest: dict[str, Any]) -> set[str]:
    raw = manifest.get("missing") or []
    codes: set[str] = set()
    if isinstance(raw, dict):
        for items in raw.values():
            if isinstance(items, list):
                codes.update(str(item) for item in items)
            elif items:
                codes.add(str(items))
    else:
        codes = {str(item) for item in raw}
    extra = manifest.get("leagues_runtime_only") or []
    codes.update(str(item) for item in extra)
    return codes


def _to_asset_src(relative: str) -> str:
    rel = relative.strip().lstrip("/")
    if rel.startswith("crests/"):
        return f"/{rel}"
    return f"{ASSET_PREFIX}/{rel}"


def league_asset(code: str) -> str:
    manifest = load_crest_manifest()
    rel = (manifest.get("leagues") or {}).get(code)
    if rel:
        return _to_asset_src(str(rel)).lstrip("/")
    return f"crests/leagues/{code}.png"


def resolve_src(
    url: str | None,
    *,
    code: str | None = None,
    team_id: int | None = None,
) -> str | None:
    if url:
        return url
    manifest = load_crest_manifest()
    if team_id is not None:
        rel = (manifest.get("teams") or {}).get(str(team_id))
        if rel:
            return _to_asset_src(str(rel))
    if code:
        if code in _missing_codes(manifest):
            return None
        rel = (manifest.get("leagues") or {}).get(code)
        if rel:
            return _to_asset_src(str(rel))
    return None


def _placeholder(label: str, size: int, color: str) -> ft.Container:
    return ft.Container(
        width=size,
        height=size,
        bgcolor=color,
        border_radius=size / 2,
        alignment=ft.Alignment.CENTER,
        content=ft.Text(
            label[:3].upper(),
            size=max(9, size // 4),
            weight=ft.FontWeight.BOLD,
            color=FG,
        ),
        border=ft.border.all(1, ft.Colors.with_opacity(0.14, ft.Colors.WHITE)),
    )


def crest_image(
    src: str | None,
    *,
    label: str,
    size: int = 40,
    code: str | None = None,
    team_id: int | None = None,
) -> ft.Control:
    resolved = resolve_src(src, code=code, team_id=team_id)
    if resolved:
        return ft.Container(
            width=size,
            height=size,
            bgcolor=SURFACE,
            border_radius=8,
            alignment=ft.Alignment.CENTER,
            content=ft.Image(
                src=resolved,
                width=size - 6,
                height=size - 6,
                fit=ft.BoxFit.CONTAIN,
            ),
            tooltip=label,
        )
    return _placeholder(label, size, LEAGUE_COLORS.get(code or "", MUTED))
