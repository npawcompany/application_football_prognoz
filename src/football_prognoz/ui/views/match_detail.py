from __future__ import annotations

from collections.abc import Callable

import flet as ft

from football_prognoz.domain.prediction import MatchForecast
from football_prognoz.ui.components.crest import crest_image
from football_prognoz.ui.components.fact_card import fact_card
from football_prognoz.ui.components.form_pills import form_pills
from football_prognoz.ui.components.h2h_table import h2h_table
from football_prognoz.ui.components.probability_bar import preliminary_score_card, probability_bar
from football_prognoz.ui.components.squad_card import squad_card
from football_prognoz.ui.components.standings_duel import standings_duel
from football_prognoz.ui.components.team_label import team_label
from football_prognoz.ui.components.venue import venue_badge
from football_prognoz.ui.formatters import format_kickoff
from football_prognoz.ui.motion import apply_motion, scroll_pane, with_cursor
from football_prognoz.ui.runtime import disclaimer, error_banner, info_banner
from football_prognoz.ui.theme import (
    CARD,
    FG,
    MUTED,
    SURFACE,
    fact_columns,
    fact_runs,
    glass_border,
    scaled,
)


def _form_block(home: str, away: str, *, window_width: int) -> ft.Control:
    label_size = scaled(12, window_width)
    return ft.Column(
        [
            ft.Row(
                [
                    venue_badge("home", size=14),
                    ft.Text("Хозяева", size=label_size, color=MUTED, width=56),
                    form_pills(home),
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            ft.Row(
                [
                    venue_badge("away", size=14),
                    ft.Text("Гости", size=label_size, color=MUTED, width=56),
                    form_pills(away),
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        ],
        spacing=6,
        tight=True,
    )


def _elo_block(home: float, away: float, *, window_width: int) -> ft.Control:
    delta = home - away
    sign = f"{delta:+.0f}"
    return ft.Column(
        [
            ft.Text(
                f"{home:.0f}  ·  {away:.0f}",
                size=scaled(16, window_width),
                weight=ft.FontWeight.W_600,
                color=FG,
            ),
            ft.Text(f"разница {sign}", size=scaled(12, window_width), color=MUTED),
        ],
        spacing=4,
        tight=True,
    )


def _team_chip(
    crest: str | None,
    name: str,
    team_id: int,
    side: str,
    *,
    window_width: int,
) -> ft.Control:
    return ft.Row(
        [
            venue_badge(side, size=16),
            crest_image(crest, label=name, size=scaled(28, window_width), team_id=team_id),
            team_label(name, size=scaled(18, window_width), expand=False),
        ],
        spacing=8,
        tight=True,
        wrap=False,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )


def _fact_grid(facts: list[ft.Control], columns: int) -> ft.Control:
    columns = max(1, min(columns, len(facts)))
    if columns == 1:
        return ft.Column(facts, spacing=10, tight=True)
    rows: list[ft.Control] = []
    for index in range(0, len(facts), columns):
        chunk = facts[index : index + columns]
        rows.append(
            ft.Row(
                [ft.Container(content=card, expand=True) for card in chunk],
                spacing=10,
            )
        )
    return ft.Column(rows, spacing=10, tight=True)


def match_detail_view(
    forecast: MatchForecast | None,
    *,
    loading: bool,
    error: str | None,
    on_back: Callable[[], None],
    window_width: int = 1440,
    embedded: bool = False,
    show_disclaimer: bool = True,
    show_ai_block: bool = True,
) -> ft.Control:
    header: list[ft.Control] = []
    if not embedded:
        header.append(
            with_cursor(
                ft.IconButton(
                    icon=ft.Icons.ARROW_BACK,
                    tooltip="К календарю",
                    on_click=lambda _e: on_back(),
                ),
                interactive=True,
            )
        )
    header.append(ft.Text("Прогноз матча", size=scaled(13, window_width), color=MUTED))
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
                padding=24,
            )
        )
        return scroll_pane(body)
    if forecast is None:
        body.append(
            info_banner(
                "Матч не выбран.",
                action_hint="Откройте календарь и нажмите «Прогноз».",
            )
        )
        return scroll_pane(body)

    match = forecast.match
    feats = forecast.features
    layout_width = max(window_width // 2, 360) if embedded else window_width
    runs = fact_runs(layout_width)
    columns = fact_columns(layout_width)
    tile_h = max(120, scaled(128, layout_width)) if columns > 1 else None
    facts = [
        fact_card(
            "Форма",
            _form_block(feats.home_form, feats.away_form, window_width=layout_width),
            bgcolor=SURFACE,
            height=tile_h,
        ),
        fact_card(
            "Рейтинг Elo",
            _elo_block(feats.home_elo, feats.away_elo, window_width=layout_width),
            bgcolor=SURFACE,
            height=tile_h,
        ),
    ]
    context = apply_motion(
        ft.Container(
            content=ft.Column(
                [
                    ft.Text("Контекст матча", size=scaled(13, layout_width), color=MUTED),
                    _fact_grid(facts, min(2, columns)),
                    ft.Text("Личные встречи", size=scaled(13, layout_width), color=MUTED),
                    h2h_table(feats.h2h_matches, window_width=layout_width),
                    ft.Text("Таблица", size=scaled(13, layout_width), color=MUTED),
                    standings_duel(
                        match,
                        feats.home_standing,
                        feats.away_standing,
                        window_width=layout_width,
                    ),
                ],
                spacing=10,
                tight=True,
            ),
            bgcolor=CARD,
            border=glass_border(),
            border_radius=12,
            padding=12,
        )
    )
    body.extend(
        [
            ft.Row(
                [
                    _team_chip(
                        match.home_crest,
                        match.home_name,
                        match.home_id,
                        "home",
                        window_width=layout_width,
                    ),
                    ft.Text("—", size=scaled(18, layout_width), color=MUTED),
                    _team_chip(
                        match.away_crest,
                        match.away_name,
                        match.away_id,
                        "away",
                        window_width=layout_width,
                    ),
                ],
                spacing=12,
                wrap=True,
                run_spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            ft.Text(
                format_kickoff(match.utc_date),
                size=scaled(12, layout_width),
                color=MUTED,
            ),
            probability_bar(
                forecast.probabilities,
                compact=runs == 1,
                window_width=layout_width,
            ),
            preliminary_score_card(
                forecast.scoreline,
                match,
                compact=runs == 1,
                window_width=layout_width,
                home_roster=forecast.home_roster,
            ),
            context,
            squad_card(
                forecast.home_roster,
                forecast.away_roster,
                compact=runs == 1,
                window_width=layout_width,
                home_elo=feats.home_elo,
                away_elo=feats.away_elo,
                lineup=forecast.lineup,
            ),
        ]
    )
    if show_ai_block:
        body.append(
            apply_motion(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Icon(ft.Icons.MEMORY, size=16, color=MUTED),
                                    ft.Text(
                                        "AI-пояснение",
                                        size=scaled(15, layout_width),
                                        weight=ft.FontWeight.W_600,
                                        color=FG,
                                    ),
                                ],
                                spacing=8,
                            ),
                            ft.Text(
                                forecast.explanation.text,
                                size=scaled(13, layout_width),
                                color=FG,
                            )
                            if forecast.explanation
                            else info_banner(
                                "AI не настроен. Добавьте OPENAI_API_KEY в Настройках — "
                                "числа уже посчитаны локально."
                            ),
                        ],
                        spacing=10,
                        tight=True,
                    ),
                    bgcolor=CARD,
                    border=glass_border(),
                    border_radius=12,
                    padding=12,
                )
            )
        )
    return scroll_pane(body)
