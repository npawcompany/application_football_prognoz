"""Home / away marks used on every team row."""

from __future__ import annotations

import flet as ft

from football_prognoz.ui.theme import ACCENT, AWAY

HOME_SIDE = "home"
AWAY_SIDE = "away"


def venue_badge(side: str, *, size: int = 14) -> ft.Icon:
    home = side == HOME_SIDE
    return ft.Icon(
        ft.Icons.HOME if home else ft.Icons.DIRECTIONS_BUS,
        size=size,
        color=ACCENT if home else AWAY,
        tooltip="Дома" if home else "В гостях",
    )
