from __future__ import annotations

import flet as ft

from football_prognoz.config import ASSETS_DIR
from football_prognoz.ui.app import start_ui


def main(page: ft.Page) -> None:
    start_ui(page)


def run() -> None:
    ft.run(main, assets_dir=str(ASSETS_DIR))


if __name__ == "__main__":
    run()
