from __future__ import annotations

import json
from pathlib import Path

import pytest

from football_prognoz.config import ROOT_DIR

SAMPLES = ROOT_DIR / "data" / "samples"


@pytest.fixture
def competitions_payload() -> dict:
    return json.loads((SAMPLES / "competitions.json").read_text(encoding="utf-8"))


@pytest.fixture
def matches_payload() -> dict:
    return json.loads((SAMPLES / "matches.json").read_text(encoding="utf-8"))


@pytest.fixture
def standings_payload() -> dict:
    return json.loads((SAMPLES / "standings.json").read_text(encoding="utf-8"))


@pytest.fixture
def sample_csv() -> Path:
    return SAMPLES / "sample_results.csv"


@pytest.fixture
def teams_payload() -> dict:
    return {
        "count": 2,
        "filters": {},
        "competition": {"id": 2021, "name": "Premier League", "code": "PL"},
        "teams": [
            {
                "id": 57,
                "name": "Arsenal FC",
                "shortName": "Arsenal",
                "tla": "ARS",
                "crest": "https://crests.football-data.org/57.png",
            },
            {
                "id": 65,
                "name": "Manchester City FC",
                "shortName": "Man City",
                "tla": "MCI",
                "crest": "https://crests.football-data.org/65.png",
            },
        ],
    }
