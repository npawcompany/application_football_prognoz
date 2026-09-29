"""'Новости команд' card: recent headlines (GNews or RSS) plus the LLM «Итог по новостям».

Context only: neither the headlines nor the summary change the 1X2 probabilities.
"""

from __future__ import annotations

import flet as ft

from football_prognoz.domain.news import NewsReport, NewsSummary, TeamNews, TeamNewsTakeaway
from football_prognoz.services.llm_policy import PLAN_REFRESH, generated_caption
from football_prognoz.ui.motion import apply_motion
from football_prognoz.ui.runtime import info_banner
from football_prognoz.ui.theme import ACCENT, CARD, DRAW, FG, MUTED, SURFACE, glass_border, scaled

PROVIDER_LABELS = {"gnews": "GNews", "rss": "RSS спортивных изданий"}
SUMMARY_TITLE = "Итог по новостям"
SUMMARY_LOADING_TEXT = "Идёт анализ новостей…"
SUMMARY_REFRESH_TEXT = "Обновляем итог в фоне — пока показан сохранённый."


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


def _takeaway(
    title: str, takeaway: TeamNewsTakeaway, cited: dict[str, str], width: int
) -> list[ft.Control]:
    if not takeaway.points and not takeaway.relevance:
        return []
    rows: list[ft.Control] = [
        ft.Text(title, size=scaled(12, width), color=MUTED, weight=ft.FontWeight.W_600)
    ]
    for point in takeaway.points:
        source = cited.get(point.headline, "")
        rows.append(
            ft.Row(
                [
                    ft.Icon(ft.Icons.CHEVRON_RIGHT, size=14, color=ACCENT),
                    ft.Column(
                        [
                            ft.Text(point.text, size=scaled(12, width), color=FG),
                            *(
                                [
                                    ft.Text(
                                        f"по заголовку: «{source}»",
                                        size=scaled(11, width),
                                        color=MUTED,
                                        italic=True,
                                    )
                                ]
                                if source
                                else []
                            ),
                        ],
                        spacing=2,
                        tight=True,
                        expand=True,
                    ),
                ],
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.START,
            )
        )
    if takeaway.relevance:
        rows.append(
            ft.Text(f"Значение для матча: {takeaway.relevance}", size=scaled(12, width), color=FG)
        )
    return rows


def _loading_row(text: str, width: int, *, bar: bool) -> list[ft.Control]:
    rows: list[ft.Control] = [
        ft.Row(
            [
                ft.ProgressRing(width=14, height=14, stroke_width=2, color=ACCENT),
                ft.Text(text, size=scaled(12, width), color=FG),
            ],
            spacing=8,
        )
    ]
    if bar:
        rows.append(ft.ProgressBar(color=ACCENT, bgcolor=ft.Colors.with_opacity(0.15, ACCENT)))
    return rows


def summary_block(
    summary: NewsSummary | None,
    *,
    home_name: str,
    away_name: str,
    window_width: int,
    note: str = "",
    error: str = "",
    plan: str = "",
    loading: bool = False,
) -> ft.Control:
    """The «Итог по новостям» sub-card: summary, loading, note (no LLM / finished) or error."""
    width = window_width
    rows: list[ft.Control] = [
        ft.Row(
            [
                ft.Icon(ft.Icons.AUTO_AWESOME, size=16, color=ACCENT),
                ft.Text(
                    SUMMARY_TITLE, size=scaled(13, width), color=FG, weight=ft.FontWeight.W_600
                ),
            ],
            spacing=6,
        )
    ]
    if summary is not None:
        rows.append(ft.Text(summary.text, size=scaled(13, width), color=FG))
        rows.extend(_takeaway(f"Хозяева · {home_name}", summary.home, summary.cited, width))
        rows.extend(_takeaway(f"Гости · {away_name}", summary.away, summary.cited, width))
        if summary.stale_note:
            rows.append(
                ft.Row(
                    [
                        ft.Icon(ft.Icons.HISTORY, size=14, color=DRAW),
                        ft.Text(summary.stale_note, size=scaled(12, width), color=FG, expand=True),
                    ],
                    spacing=6,
                )
            )
        if summary.notice:
            rows.append(info_banner(summary.notice))
        if loading and plan == PLAN_REFRESH:
            rows.extend(_loading_row(SUMMARY_REFRESH_TEXT, width, bar=False))
        if error:
            rows.append(
                ft.Text(
                    f"Обновить не удалось: {error} Показан сохранённый.",
                    size=scaled(11, width),
                    color=DRAW,
                )
            )
        caption = generated_caption(summary.generated_at, summary.model)
        if caption:
            rows.append(ft.Text(caption, size=scaled(11, width), color=MUTED))
    elif note:
        rows.append(ft.Text(note, size=scaled(12, width), color=MUTED))
    elif error:
        rows.append(ft.Text(f"Итог недоступен: {error}", size=scaled(12, width), color=DRAW))
    elif loading:
        rows.extend(_loading_row(SUMMARY_LOADING_TEXT, width, bar=True))
    else:
        rows.append(ft.Text("Итог появится после AI-анализа.", size=scaled(12, width), color=MUTED))
    return ft.Container(
        content=ft.Column(rows, spacing=6, tight=True),
        bgcolor=SURFACE,
        border=glass_border(),
        border_radius=10,
        padding=10,
    )


def news_card(
    report: NewsReport,
    *,
    window_width: int,
    summary: NewsSummary | None = None,
    note: str = "",
    error: str = "",
    plan: str = "",
    loading: bool = False,
) -> ft.Control:
    body: list[ft.Control] = [
        ft.Text("Новости команд", size=scaled(13, window_width), color=MUTED),
    ]
    if report.has_data() or summary is not None or note or error or loading:
        body.append(
            summary_block(
                summary,
                home_name=report.home.team_name,
                away_name=report.away.team_name,
                window_width=window_width,
                note=note,
                error=error,
                plan=plan,
                loading=loading,
            )
        )
    if report.has_data():
        body.append(_team_block(report.home, "Хозяева", window_width))
        body.append(_team_block(report.away, "Гости", window_width))
    for note_line in report.notes:
        body.append(ft.Text(note_line, size=scaled(11, window_width), color=MUTED))
    provider = PROVIDER_LABELS.get(report.provider, report.provider or "—")
    body.append(
        ft.Text(
            f"Источник: {provider}. Заголовки СМИ не проверены; итог AI пересказывает только "
            "их и не влияет на вероятности.",
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
