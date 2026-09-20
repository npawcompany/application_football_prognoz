from __future__ import annotations

from pathlib import Path

import flet as ft

from football_prognoz.ui.app import start_ui

ROOT = Path(__file__).resolve().parents[2]
ASSETS_DIR = ROOT / "assets"


def main(page: ft.Page) -> None:
    start_ui(page)


def run() -> None:
    ft.app(target=main, assets_dir=str(ASSETS_DIR))


if __name__ == "__main__":
    run()
