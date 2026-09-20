from __future__ import annotations

from collections.abc import Callable

import flet as ft

from football_prognoz.domain.prediction import MatchForecast
from football_prognoz.ui.components.crest import crest_image
from football_prognoz.ui.components.probability_bar import preliminary_score_card, probability_bar
from football_prognoz.ui.runtime import disclaimer, error_banner, info_banner
from football_prognoz.ui.theme import CARD, FG, MUTED, fact_runs, glass_border


def _fact(title: str, lines: list[str]) -> ft.Control:
    return ft.Container(
        content=ft.Column(
            [
                ft.Text(title, size=11, color=MUTED),
                *[ft.Text(line, size=13, color=FG, weight=ft.FontWeight.W_600) for line in lines],
            ],
            spacing=6,
        ),
        bgcolor=CARD,
        border=glass_border(),
        border_radius=12,
        padding=12,
        expand=True,
    )


def match_detail_view(
    forecast: MatchForecast | None,
    *,
    loading: bool,
    error: str | None,
    on_back: Callable[[], None],
    window_width: int = 1440,
    embedded: bool = False,
    show_disclaimer: bool = True,
) -> ft.Control:
    header: list[ft.Control] = []
    if not embedded:
        header.append(
            ft.IconButton(
                icon=ft.Icons.ARROW_BACK,
                tooltip="К календарю",
                on_click=lambda _e: on_back(),
            )
        )
    header.append(ft.Text("Прогноз матча", size=13, color=MUTED))
    body: list[ft.Control] = [ft.Row(header)]
    if show_disclaimer:
        body.append(disclaimer())
    if error:
        body.append(error_banner(error))
    if loading:
        body.append(
            ft.Container(
                content=ft.ProgressRing(color="#22C55E"),
                alignment=ft.Alignment.CENTER,
                expand=True,
            )
        )
        return ft.Column(body, spacing=12, expand=True, scroll=ft.ScrollMode.AUTO)
    if forecast is None:
        body.append(
            info_banner(
                "Матч не выбран.",
                action_hint="Откройте календарь и нажмите «Прогноз».",
            )
        )
        return ft.Column(body, spacing=12, expand=True, scroll=ft.ScrollMode.AUTO)

    match = forecast.match
    feats = forecast.features
    runs = fact_runs(window_width)
    facts = [
        _fact("Форма", [f"Хозяева: {feats.home_form}", f"Гости: {feats.away_form}"]),
        _fact("Рейтинг Elo", [f"Хозяева: {feats.home_elo:.0f}", f"Гости: {feats.away_elo:.0f}"]),
        _fact("Личные встречи", [feats.h2h_summary]),
        _fact(
            "Таблица",
            [
                f"Хозяева: {feats.home_position or '—'}",
                f"Гости: {feats.away_position or '—'}",
                f"Матчей в кэше: {feats.sample_matches}",
            ],
        ),
    ]
    body.extend(
        [
            ft.Row(
                [
                    crest_image(
                        match.home_crest,
                        label=match.home_name,
                        size=36,
                        team_id=match.home_id,
                    ),
                    ft.Text(match.label, size=22, weight=ft.FontWeight.BOLD, color=FG, expand=True),
                    crest_image(
                        match.away_crest,
                        label=match.away_name,
                        size=36,
                        team_id=match.away_id,
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            ft.Text(
                match.utc_date.strftime("%d.%m.%Y %H:%M UTC"),
                size=12,
                color=MUTED,
                font_family="Fira Code",
            ),
            probability_bar(forecast.probabilities),
            preliminary_score_card(forecast.scoreline),
            ft.Row(facts[:runs] if runs < 4 else facts, spacing=10)
            if runs >= 4
            else ft.Column(
                [ft.Row(facts[i : i + runs], spacing=10) for i in range(0, 4, runs)],
                spacing=10,
            ),
            ft.Container(
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Icon(ft.Icons.MEMORY, size=16, color=MUTED),
                                ft.Text(
                                    "AI-пояснение",
                                    size=15,
                                    weight=ft.FontWeight.W_600,
                                    color=FG,
                                ),
                            ],
                            spacing=8,
                        ),
                        ft.Text(forecast.explanation.text, size=13, color=FG)
                        if forecast.explanation
                        else info_banner(
                            "AI не настроен. Добавьте OPENAI_API_KEY в Настройках — "
                            "числа уже посчитаны локально."
                        ),
                    ],
                    spacing=10,
                ),
                bgcolor=CARD,
                border=glass_border(),
                border_radius=12,
                padding=12,
            ),
        ]
    )
    return ft.Column(body, spacing=12, expand=True, scroll=ft.ScrollMode.AUTO)
