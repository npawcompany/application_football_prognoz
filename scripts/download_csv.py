#!/usr/bin/env python3
"""Download public football-data.co.uk CSVs into data/csv/ (gitignored)."""

from __future__ import annotations

import argparse
from pathlib import Path

import httpx

from football_prognoz.config import ROOT_DIR

BASE = "https://www.football-data.co.uk/mmz4281"
# season folder 2425 + div file, e.g. E0.csv
DEFAULT_FILES = ("E0.csv", "SP1.csv", "I1.csv", "D1.csv", "F1.csv")


def season_code(start_year: int) -> str:
    return f"{start_year % 100:02d}{(start_year + 1) % 100:02d}"


def download(dest: Path, seasons: list[int], files: tuple[str, ...]) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        for year in seasons:
            code = season_code(year)
            for name in files:
                url = f"{BASE}/{code}/{name}"
                path = dest / f"{code}_{name}"
                response = client.get(url)
                if response.status_code >= 400:
                    print(f"skip {url} ({response.status_code})")
                    continue
                path.write_bytes(response.content)
                print(f"wrote {path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-year", type=int, default=2022)
    parser.add_argument("--end-year", type=int, default=2024)
    args = parser.parse_args()
    seasons = list(range(args.start_year, args.end_year + 1))
    download(ROOT_DIR / "data" / "csv", seasons, DEFAULT_FILES)


if __name__ == "__main__":
    main()
