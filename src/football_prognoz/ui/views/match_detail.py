from __future__ import annotations

from collections.abc import Callable

import flet as ft

from football_prognoz.domain.prediction import MatchForecast
from football_prognoz.ui.components.probability_bar import probability_bar
from football_prognoz.ui.runtime import disclaimer, error_banner, info_banner


def match_detail_view(
    forecast: MatchForecast | None,
    *,
    loading: bool,
    error: str | None,
    on_back: Callable[[], None],
) -> ft.Control:
    body: list[ft.Control] = [
        ft.Row(
            [
                ft.IconButton(icon=ft.Icons.ARROW_BACK, on_click=lambda _e: on_back()),
                ft.Text("Прогноз матча", size=22, weight=ft.FontWeight.BOLD),
            ]
        ),
        disclaimer(),
    ]
    if error:
        body.append(error_banner(error))
    if loading:
        body.append(ft.ProgressRing())
        return ft.Column(body, spacing=12, expand=True, scroll=ft.ScrollMode.AUTO)
    if forecast is None:
        body.append(info_banner("Матч не выбран."))
        return ft.Column(body, spacing=12, expand=True, scroll=ft.ScrollMode.AUTO)

    match = forecast.match
    feats = forecast.features
    body.extend(
        [
            ft.Text(match.label, size=24, weight=ft.FontWeight.BOLD),
            ft.Text(match.utc_date.strftime("%d.%m.%Y %H:%M UTC")),
            probability_bar(forecast.probabilities),
            ft.Text("Факты модели", weight=ft.FontWeight.BOLD),
            ft.Text(f"Форма хозяев: {feats.home_form}"),
            ft.Text(f"Форма гостей: {feats.away_form}"),
            ft.Text(f"Elo: {feats.home_elo:.0f} — {feats.away_elo:.0f}"),
            ft.Text(f"H2H: {feats.h2h_summary}"),
            ft.Text(
                "Места в таблице: "
                f"{feats.home_position or '—'} / {feats.away_position or '—'}"
            ),
            ft.Text(f"Матчей в кэше лиги: {feats.sample_matches}"),
            ft.Text("AI-пояснение", weight=ft.FontWeight.BOLD),
        ]
    )
    if forecast.explanation:
        body.append(ft.Text(forecast.explanation.text))
        body.append(
            ft.Text(
                f"Модель: {forecast.explanation.model}",
                size=12,
                color=ft.Colors.GREY_400,
            )
        )
    else:
        body.append(
            info_banner(
                "AI не настроен. Добавьте OPENAI_API_KEY в Настройках — "
                "числа уже посчитаны локально."
            )
        )
    return ft.Column(body, spacing=10, expand=True, scroll=ft.ScrollMode.AUTO)
