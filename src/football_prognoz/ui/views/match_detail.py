from __future__ import annotations

from collections.abc import Callable

import flet as ft

from football_prognoz.domain.match import LIVE_STATUSES, Match
from football_prognoz.domain.prediction import MatchForecast
from football_prognoz.ui.components.ai_analysis import AI_LOADING, ai_block, sources_line
from football_prognoz.ui.components.crest import crest_image
from football_prognoz.ui.components.fact_card import fact_card
from football_prognoz.ui.components.form_pills import form_pills
from football_prognoz.ui.components.h2h_table import h2h_table
from football_prognoz.ui.components.markets_table import markets_card
from football_prognoz.ui.components.news_card import news_card
from football_prognoz.ui.components.player_status_card import player_status_card
from football_prognoz.ui.components.probability_bar import preliminary_score_card, probability_bar
from football_prognoz.ui.components.result_banner import result_banner
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


def _optional(control: ft.Control | None) -> list[ft.Control]:
    return [control] if control is not None else []


def _centre_score(match: Match, width: int) -> ft.Control:
    """Final (or live) score between the club names; a dash before kickoff."""
    if match.has_score and (match.is_played or match.status in LIVE_STATUSES):
        return ft.Container(
            content=ft.Text(
                match.score_label,
                size=scaled(24, width),
                weight=ft.FontWeight.BOLD,
                color=FG,
            ),
            bgcolor=SURFACE,
            border_radius=8,
            padding=ft.Padding.symmetric(horizontal=12, vertical=2),
            tooltip=match.status_text,
        )
    return ft.Text("—", size=scaled(18, width), color=MUTED)


def _history_hint_row(forecast: MatchForecast, width: int) -> list[ft.Control]:
    """'Historically such an outcome came true in N%' — hidden when data is too thin."""
    hint = forecast.history_hint
    if hint is None:
        return []
    return [
        ft.Text(
            f"{hint.text} Это статистика прошлых прогнозов, вероятности выше не меняются.",
            size=scaled(12, width),
            color=MUTED,
        )
    ]


TWO_COLUMNS_WIDTH = 1500


def _main_blocks(forecast: MatchForecast, layout_width: int) -> list[ft.Control]:
    match = forecast.match
    feats = forecast.features
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
    return [
        *_optional(result_banner(forecast, window_width=layout_width)),
        probability_bar(
            forecast.probabilities,
            compact=runs == 1,
            window_width=layout_width,
        ),
        *_history_hint_row(forecast, layout_width),
        preliminary_score_card(
            forecast.scoreline,
            match,
            compact=runs == 1,
            window_width=layout_width,
            home_roster=forecast.home_roster,
        ),
        *_optional(
            markets_card(
                forecast.markets,
                match_id=match.id,
                window_width=layout_width,
                explanation=forecast.explanation,
            )
        ),
        context,
    ]


def _side_blocks(
    forecast: MatchForecast,
    layout_width: int,
    *,
    show_ai_block: bool,
    ai_state: str | None,
    ai_error: str | None,
) -> list[ft.Control]:
    feats = forecast.features
    runs = fact_runs(layout_width)
    blocks: list[ft.Control] = [
        squad_card(
            forecast.home_roster,
            forecast.away_roster,
            compact=runs == 1,
            window_width=layout_width,
            home_elo=feats.home_elo,
            away_elo=feats.away_elo,
            lineup=forecast.lineup,
        )
    ]
    if forecast.player_status is not None:
        blocks.append(player_status_card(forecast.player_status, window_width=layout_width))
    if forecast.news is not None:
        blocks.append(
            news_card(
                forecast.news,
                window_width=layout_width,
                summary=forecast.news_summary,
                note=forecast.news_note,
                error=forecast.news_summary_error,
                plan=forecast.news_plan,
                loading=ai_state == AI_LOADING,
            )
        )
    if show_ai_block:
        blocks.append(
            ai_block(
                forecast,
                ai_state=ai_state,
                ai_error=ai_error,
                window_width=layout_width,
            )
        )
    elif forecast.sources:
        blocks.append(sources_line(forecast.sources, window_width=layout_width))
    return blocks


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
    ai_state: str | None = None,
    ai_error: str | None = None,
    pane_width: int | None = None,
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
    if pane_width is not None:
        layout_width = max(pane_width, 360)
    else:
        layout_width = max(window_width // 2, 360) if embedded else window_width
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
                    _centre_score(match, layout_width),
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
        ]
    )
    if layout_width >= TWO_COLUMNS_WIDTH:
        # Wide panes: numbers on the left, clubs/news/AI on the right — no empty half.
        half = layout_width // 2 - 8
        body.append(
            ft.Row(
                [
                    ft.Column(_main_blocks(forecast, half), spacing=12, tight=True, expand=1),
                    ft.Column(
                        _side_blocks(
                            forecast,
                            half,
                            show_ai_block=show_ai_block,
                            ai_state=ai_state,
                            ai_error=ai_error,
                        ),
                        spacing=12,
                        tight=True,
                        expand=1,
                    ),
                ],
                spacing=16,
                vertical_alignment=ft.CrossAxisAlignment.START,
            )
        )
        return scroll_pane(body)
    body.extend(_main_blocks(forecast, layout_width))
    body.extend(
        _side_blocks(
            forecast,
            layout_width,
            show_ai_block=show_ai_block,
            ai_state=ai_state,
            ai_error=ai_error,
        )
    )
    return scroll_pane(body)
