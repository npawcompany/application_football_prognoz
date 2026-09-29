from __future__ import annotations

import json
from pathlib import Path

from football_prognoz.ui.components.crest import (
    load_crest_manifest,
    reset_crest_manifest,
    resolve_src,
)


def test_resolve_src_prefers_live_api_url() -> None:
    assert resolve_src("https://crests.football-data.org/57.png", team_id=57) == (
        "https://crests.football-data.org/57.png"
    )


def test_resolve_src_uses_temp_manifest(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps(
            {
                "leagues": {"PL": "leagues/PL.png"},
                "teams": {"99": "teams/99-demo.png"},
                "missing": ["WC"],
            }
        ),
        encoding="utf-8",
    )
    try:
        load_crest_manifest(path, force=True)
        assert resolve_src(None, team_id=99) == "/crests/teams/99-demo.png"
        assert resolve_src(None, code="PL") == "/crests/leagues/PL.png"
        assert resolve_src(None, code="WC") is None
        assert resolve_src(None, team_id=1, code="PL") == "/crests/leagues/PL.png"
        assert resolve_src(None) is None
    finally:
        reset_crest_manifest()


def test_resolve_src_parses_nested_missing_lists(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps(
            {
                "leagues": {"PL": "leagues/PL.png", "BSA": "leagues/BSA.png"},
                "teams": {},
                "missing": {"leagues": ["BSA"], "teams": ["999"]},
            }
        ),
        encoding="utf-8",
    )
    try:
        load_crest_manifest(path, force=True)
        assert resolve_src(None, code="BSA") is None
        assert resolve_src(None, code="PL") == "/crests/leagues/PL.png"
    finally:
        reset_crest_manifest()


def test_resolve_src_treats_runtime_only_as_missing(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps(
            {
                "leagues": {"CL": "leagues/CL.png"},
                "teams": {},
                "leagues_runtime_only": ["BSA"],
            }
        ),
        encoding="utf-8",
    )
    try:
        load_crest_manifest(path, force=True)
        assert resolve_src(None, code="BSA") is None
        assert resolve_src(None, code="CL") == "/crests/leagues/CL.png"
    finally:
        reset_crest_manifest()
