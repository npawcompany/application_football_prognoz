"""'Новости команд' card: recent headlines (GNews or RSS). Context only, not part of 1X2."""

from __future__ import annotations

import flet as ft

from football_prognoz.domain.news import NewsReport, TeamNews
from football_prognoz.ui.motion import apply_motion
from football_prognoz.ui.theme import CARD, FG, MUTED, glass_border, scaled

PROVIDER_LABELS = {"gnews": "GNews", "rss": "RSS спортивных изданий"}


def _team_block(team: TeamNews, title: str, width: int) -> ft.Control:
    rows: list[ft.Control] = [
        ft.Text(
            f"{title} · {team.team_name}",
            size=scaled(13, width),
            weight=ft.FontWeight.W_600,
            color=FG,
        )
    ]
    if not team.items:
        rows.append(ft.Text("свежих заголовков нет", size=scaled(12, width), color=MUTED))
    for item in team.items:
        rows.append(
            ft.Text(
                f"{item.published_at:%d.%m} · {item.topic_label} · {item.title} ({item.source})",
                size=scaled(12, width),
                color=FG,
                selectable=True,
            )
        )
    return ft.Column(rows, spacing=4, tight=True)


def news_card(report: NewsReport, *, window_width: int) -> ft.Control:
    body: list[ft.Control] = [
        ft.Text("Новости команд", size=scaled(13, window_width), color=MUTED),
    ]
    if report.has_data():
        body.append(_team_block(report.home, "Хозяева", window_width))
        body.append(_team_block(report.away, "Гости", window_width))
    for note in report.notes:
        body.append(ft.Text(note, size=scaled(11, window_width), color=MUTED))
    provider = PROVIDER_LABELS.get(report.provider, report.provider or "—")
    body.append(
        ft.Text(
            f"Источник: {provider}. Заголовки СМИ не проверены и не влияют на вероятности 1X2.",
            size=scaled(11, window_width),
            color=MUTED,
        )
    )
    return apply_motion(
        ft.Container(
            content=ft.Column(body, spacing=10, tight=True),
            bgcolor=CARD,
            border=glass_border(),
            border_radius=12,
            padding=12,
        )
    )
