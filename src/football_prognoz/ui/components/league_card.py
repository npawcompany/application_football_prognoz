"""League tile: crest, name, availability note, area flag, type and season.

Dense by design: natural height (no aspect-ratio box), every line carries data.
"""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from football_prognoz.domain.country import competition_country
from football_prognoz.domain.team import COMPETITION_TYPES_RU, Competition
from football_prognoz.ui.components.crest import crest_image
from football_prognoz.ui.components.flag import country_label
from football_prognoz.ui.components.team_label import team_label
from football_prognoz.ui.motion import apply_motion
from football_prognoz.ui.theme import ACCENT, CARD, DRAW, FG, MUTED, SURFACE, glass_border


def season_text(item: Competition) -> str | None:
    start, end = item.season_start, item.season_end
    if start and end:
        if start.year == end.year:
            return f"Сезон {start:%d.%m}–{end:%d.%m.%Y}"
        return f"Сезон {start:%m.%Y}–{end:%m.%Y}"
    if end:
        return f"Сезон до {end:%d.%m.%Y}"
    return None


def league_card(
    item: Competition,
    on_select: Callable[[Competition], None],
    *,
    selected: bool = False,
    note: str | None = None,
    dimmed: bool = False,
    favorite: bool = False,
) -> ft.Control:
    country = item.area_name or competition_country(item.code)
    kind = COMPETITION_TYPES_RU.get((item.type or "LEAGUE").upper(), "Лига")
    meta: list[ft.Control] = []
    if country:
        meta.append(country_label(country, size=11, iso3=item.area_code, flag_url=item.area_flag))
    details = " · ".join(part for part in (kind, season_text(item)) if part)
    meta.append(
        ft.Text(
            details,
            size=11,
            color=MUTED,
            max_lines=1,
            overflow=ft.TextOverflow.ELLIPSIS,
            expand=True,
        )
    )
    badge_bits: list[ft.Control] = []
    if favorite:
        badge_bits.append(ft.Icon(ft.Icons.STAR_ROUNDED, size=12, color=DRAW))
    badge_bits.append(ft.Text(item.code, size=11, weight=ft.FontWeight.W_600, color=FG))
    return apply_motion(
        ft.Container(
            content=ft.Row(
                [
                    crest_image(item.emblem, label=item.name, size=40, code=item.code),
                    ft.Column(
                        [
                            ft.Row(
                                [team_label(item.name, size=14)],
                                spacing=0,
                                expand=True,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            ft.Text(
                                note or "Календарь",
                                size=11,
                                color=MUTED if dimmed else ACCENT,
                                max_lines=1,
                                overflow=ft.TextOverflow.ELLIPSIS,
                            ),
                            ft.Row(
                                meta,
                                spacing=8,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                        ],
                        spacing=3,
                        expand=True,
                        tight=True,
                        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                    ),
                    ft.Container(
                        content=ft.Row(badge_bits, spacing=3, tight=True),
                        bgcolor=SURFACE,
                        padding=ft.Padding.symmetric(horizontal=8, vertical=3),
                        border_radius=6,
                    ),
                ],
                spacing=12,
                expand=True,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=CARD,
            border=ft.Border.all(1, ACCENT) if selected else glass_border(),
            border_radius=12,
            padding=ft.Padding.symmetric(horizontal=12, vertical=10),
            ink=True,
            on_click=lambda _e, current=item: on_select(current),
            tooltip=f"{item.name}: {note}" if note else item.name,
            opacity=0.8 if dimmed else 1.0,
        ),
        interactive=True,
    )
