"""Right pane before a match is picked: a summary of the calendar day, not a blank area."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime

import flet as ft

from football_prognoz.domain.match import LIVE_STATUSES, Match
from football_prognoz.domain.team import Competition
from football_prognoz.services.calendar import format_day_ru
from football_prognoz.ui.components.crest import crest_image
from football_prognoz.ui.formatters import format_kickoff_time
from football_prognoz.ui.theme import ACCENT, CARD, DRAW, FG, MUTED, SURFACE, glass_border


def day_stats(matches: Sequence[Match], now: datetime) -> dict[str, int]:
    played = sum(1 for m in matches if m.status.is_finished())
    live = sum(1 for m in matches if m.status in LIVE_STATUSES)
    ahead = sum(1 for m in matches if m.status.is_upcoming() and m.utc_date >= now)
    return {"total": len(matches), "played": played, "live": live, "ahead": ahead}


def _stat(value: int, label: str, color: str) -> ft.Control:
    return ft.Container(
        content=ft.Column(
            [
                ft.Text(str(value), size=26, weight=ft.FontWeight.BOLD, color=color),
                ft.Text(label, size=12, color=MUTED),
            ],
            spacing=0,
            tight=True,
        ),
        bgcolor=SURFACE,
        border_radius=10,
        padding=ft.Padding.symmetric(horizontal=14, vertical=10),
        expand=True,
    )


def day_overview(
    matches: Sequence[Match],
    competitions: Mapping[str, Competition],
    day: date,
    *,
    today: date,
    now: datetime,
    loading: bool = False,
) -> ft.Control:
    stats = day_stats(matches, now)
    by_league: dict[str, list[Match]] = {}
    for item in matches:
        by_league.setdefault(item.competition_code, []).append(item)
    league_rows: list[ft.Control] = []
    for code, items in sorted(by_league.items(), key=lambda kv: -len(kv[1])):
        comp = competitions.get(code)
        name = comp.name if comp else code
        done = sum(1 for m in items if m.status.is_finished())
        league_rows.append(
            ft.Row(
                [
                    crest_image(comp.emblem if comp else None, label=name, size=22, code=code),
                    ft.Text(name, size=13, color=FG, expand=True, max_lines=1),
                    ft.Text(f"{len(items)} · завершено {done}", size=12, color=MUTED),
                ],
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
        )
    upcoming = sorted(
        (m for m in matches if m.status.is_upcoming() and m.utc_date >= now),
        key=lambda m: m.utc_date,
    )
    next_line: list[ft.Control] = []
    if upcoming:
        first = upcoming[0]
        next_line.append(
            ft.Text(
                f"Ближайший матч: {format_kickoff_time(first.utc_date)} · {first.label}",
                size=13,
                color=FG,
            )
        )
    title = f"Сводка дня · {format_day_ru(day, today)}"
    body: list[ft.Control] = [
        ft.Text(title, size=18, weight=ft.FontWeight.W_600, color=FG),
        ft.Row(
            [
                _stat(stats["total"], "матчей", FG),
                _stat(stats["played"], "завершено", ACCENT),
                _stat(stats["live"], "идёт", DRAW),
                _stat(stats["ahead"], "впереди", FG),
            ],
            spacing=10,
        ),
        *next_line,
    ]
    if league_rows:
        body.append(ft.Text("По лигам", size=13, color=MUTED))
        body.extend(league_rows)
    elif loading:
        body.append(ft.Text("Загружаем матчи дня…", size=13, color=MUTED))
    else:
        body.append(ft.Text("В этот день матчей нет.", size=13, color=MUTED))
    body.append(
        ft.Row(
            [
                ft.Icon(ft.Icons.TOUCH_APP, size=16, color=ACCENT),
                ft.Text(
                    "Выберите матч в календаре слева, чтобы увидеть прогноз.",
                    size=13,
                    color=MUTED,
                ),
            ],
            spacing=8,
        )
    )
    return ft.Container(
        content=ft.Column(body, spacing=12, tight=True),
        bgcolor=CARD,
        border=glass_border(),
        border_radius=12,
        padding=16,
    )
