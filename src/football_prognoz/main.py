from __future__ import annotations

import flet as ft

from football_prognoz.ui.app import start_ui


def main(page: ft.Page) -> None:
    start_ui(page)


def run() -> None:
    ft.app(target=main)


if __name__ == "__main__":
    run()
