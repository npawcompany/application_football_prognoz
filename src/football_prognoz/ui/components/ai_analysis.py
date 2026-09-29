"""AI block of the Forecast screen: loading / error / not configured / analysis."""

from __future__ import annotations

import flet as ft

from football_prognoz.domain.prediction import Explanation, Factor, MarketComment, MatchForecast
from football_prognoz.services.llm_policy import PLAN_REFRESH, generated_caption
from football_prognoz.ui.motion import apply_motion
from football_prognoz.ui.runtime import error_banner, info_banner
from football_prognoz.ui.theme import ACCENT, AWAY, CARD, DRAW, FG, MUTED, glass_border, scaled

AI_LOADING = "loading"
AI_ERROR = "error"
AI_READY = "ready"
AI_NOT_CONFIGURED = "not_configured"
AI_NOTE = "note"  # finished match, nothing saved: no LLM call
REFRESH_TEXT = "Обновляем разбор в фоне — пока показан сохранённый."

NOT_CONFIGURED_TEXT = (
    "AI не настроен. Добавьте OLLAMA_API_KEY в Настройках или укажите локальный "
    "OLLAMA_HOST — числа уже посчитаны локально."
)
LOADING_TEXT = "Идёт анализ…"
LOADING_HINT = "Статистический прогноз уже готов выше, AI-разбор придёт в фоне."

_DIRECTION_ICON = {
    "up": (ft.Icons.ARROW_UPWARD, ACCENT),
    "down": (ft.Icons.ARROW_DOWNWARD, AWAY),
    "neutral": (ft.Icons.REMOVE, MUTED),
}


def resolve_ai_state(
    forecast: MatchForecast,
    ai_state: str | None,
    ai_error: str | None,
) -> str:
    """The forecast content wins over the app flag; unknown flags mean 'not configured'."""
    if forecast.explanation is not None:
        return AI_READY
    if forecast.analysis_note:
        return AI_NOTE
    if forecast.explanation_error or ai_error or ai_state == AI_ERROR:
        return AI_ERROR
    if ai_state == AI_LOADING:
        return AI_LOADING
    return AI_NOT_CONFIGURED


def _factor_row(item: Factor, width: int) -> ft.Control:
    icon, color = _DIRECTION_ICON.get(item.direction, _DIRECTION_ICON["neutral"])
    return ft.Row(
        [
            ft.Icon(icon, size=14, color=color),
            ft.Column(
                [
                    ft.Text(item.factor, size=scaled(13, width), color=FG),
                    ft.Text(item.effect, size=scaled(12, width), color=MUTED),
                ],
                spacing=2,
                tight=True,
                expand=True,
            ),
        ],
        spacing=8,
        vertical_alignment=ft.CrossAxisAlignment.START,
    )


def _side(title: str, factors: tuple[Factor, ...], width: int) -> ft.Control:
    rows: list[ft.Control] = [
        ft.Text(title, size=scaled(12, width), color=MUTED, weight=ft.FontWeight.W_600)
    ]
    if factors:
        rows.extend(_factor_row(item, width) for item in factors)
    else:
        rows.append(ft.Text("Значимых факторов не выделено.", size=scaled(12, width), color=MUTED))
    return ft.Column(rows, spacing=6, tight=True)


def _analysis(explanation: Explanation, forecast: MatchForecast, width: int) -> list[ft.Control]:
    match = forecast.match
    probs = forecast.probabilities
    blocks: list[ft.Control] = [ft.Text(explanation.text, size=scaled(13, width), color=FG)]
    if explanation.home_factors or explanation.away_factors or explanation.verdict:
        blocks.append(_side(f"Хозяева · {match.home_name}", explanation.home_factors, width))
        blocks.append(_side(f"Гости · {match.away_name}", explanation.away_factors, width))
    if explanation.verdict:
        blocks.append(
            ft.Column(
                [
                    ft.Text(
                        "Итог", size=scaled(12, width), color=MUTED, weight=ft.FontWeight.W_600
                    ),
                    ft.Text(explanation.verdict, size=scaled(13, width), color=FG),
                    ft.Text(
                        f"Расчёт модели: 1 — {probs.home:.0%} · X — {probs.draw:.0%} · "
                        f"2 — {probs.away:.0%}",
                        size=scaled(12, width),
                        color=MUTED,
                    ),
                ],
                spacing=4,
                tight=True,
            )
        )
    if explanation.confidence_label:
        reason = f" — {explanation.confidence_reason}" if explanation.confidence_reason else ""
        blocks.append(
            ft.Text(
                f"Уверенность: {explanation.confidence_label}{reason}",
                size=scaled(12, width),
                color=FG,
            )
        )
    if explanation.top_markets:
        blocks.append(_top_markets(explanation.top_markets, forecast, width))
    if explanation.risks:
        blocks.append(
            ft.Column(
                [
                    ft.Text(
                        "Риски", size=scaled(12, width), color=MUTED, weight=ft.FontWeight.W_600
                    ),
                    *[
                        ft.Row(
                            [
                                ft.Icon(ft.Icons.WARNING_AMBER, size=14, color=DRAW),
                                ft.Text(risk, size=scaled(12, width), color=FG, expand=True),
                            ],
                            spacing=6,
                        )
                        for risk in explanation.risks
                    ],
                ],
                spacing=4,
                tight=True,
            )
        )
    blocks.append(
        ft.Text(
            f"Модель: {explanation.model}. AI объясняет расчёт, но не меняет вероятности "
            "и не гарантирует исход.",
            size=scaled(11, width),
            color=MUTED,
        )
    )
    return blocks


def _top_markets(
    items: tuple[MarketComment, ...], forecast: MatchForecast, width: int
) -> ft.Control:
    rows: list[ft.Control] = [
        ft.Text(
            "Наиболее обоснованные рынки (по фактам, вероятности — из таблицы)",
            size=scaled(12, width),
            color=MUTED,
            weight=ft.FontWeight.W_600,
        )
    ]
    table = forecast.markets
    for item in items:
        market = table.by_key(item.market) if table is not None else None
        if market is None:
            continue
        chance = f"{(market.effective or 0) * 100:.0f}%"
        odds = f" · кэф {market.fair_odds:.2f}" if market.fair_odds else ""
        rows.append(
            ft.Row(
                [
                    ft.Icon(ft.Icons.STAR, size=14, color=DRAW),
                    ft.Column(
                        [
                            ft.Text(
                                f"{market.label} — {chance}{odds}",
                                size=scaled(12, width),
                                color=FG,
                                weight=ft.FontWeight.W_600,
                            ),
                            ft.Text(item.comment, size=scaled(12, width), color=FG),
                        ],
                        spacing=2,
                        tight=True,
                        expand=True,
                    ),
                ],
                spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.START,
            )
        )
    return ft.Column(rows, spacing=6, tight=True)


def _status_lines(forecast: MatchForecast, ai_state: str | None, width: int) -> list[ft.Control]:
    """Caption «Сгенерировано …, модель X», fallback notice, refresh progress / error."""
    explanation = forecast.explanation
    lines: list[ft.Control] = []
    if explanation is None:
        return lines
    if explanation.notice:
        lines.append(info_banner(explanation.notice))
    if forecast.analysis_plan == PLAN_REFRESH and ai_state == AI_LOADING:
        lines.append(
            ft.Row(
                [
                    ft.ProgressRing(width=12, height=12, stroke_width=2, color=ACCENT),
                    ft.Text(REFRESH_TEXT, size=scaled(11, width), color=MUTED),
                ],
                spacing=8,
            )
        )
    if forecast.analysis_refresh_error:
        lines.append(
            ft.Text(
                f"Обновить не удалось: {forecast.analysis_refresh_error} Показан сохранённый.",
                size=scaled(11, width),
                color=DRAW,
            )
        )
    caption = generated_caption(explanation.generated_at, explanation.model)
    if caption:
        lines.append(ft.Text(caption, size=scaled(11, width), color=MUTED))
    return lines


def sources_line(sources: tuple[str, ...], *, window_width: int) -> ft.Control:
    return ft.Text(
        "Источники: " + "; ".join(sources),
        size=scaled(11, window_width),
        color=MUTED,
        selectable=True,
    )


def ai_block(
    forecast: MatchForecast,
    *,
    ai_state: str | None,
    ai_error: str | None,
    window_width: int,
) -> ft.Control:
    state = resolve_ai_state(forecast, ai_state, ai_error)
    content: list[ft.Control] = [
        ft.Row(
            [
                ft.Icon(ft.Icons.MEMORY, size=16, color=MUTED),
                ft.Text(
                    "AI-разбор факторов",
                    size=scaled(15, window_width),
                    weight=ft.FontWeight.W_600,
                    color=FG,
                ),
            ],
            spacing=8,
        )
    ]
    if state == AI_READY and forecast.explanation is not None:
        content.extend(_analysis(forecast.explanation, forecast, window_width))
        content.extend(_status_lines(forecast, ai_state, window_width))
    elif state == AI_NOTE:
        content.append(info_banner(forecast.analysis_note))
    elif state == AI_LOADING:
        content.extend(
            [
                ft.Row(
                    [
                        ft.ProgressRing(width=16, height=16, stroke_width=2, color=ACCENT),
                        ft.Text(
                            LOADING_TEXT,
                            size=scaled(13, window_width),
                            color=FG,
                            weight=ft.FontWeight.W_600,
                        ),
                    ],
                    spacing=10,
                ),
                ft.ProgressBar(color=ACCENT, bgcolor=ft.Colors.with_opacity(0.15, ACCENT)),
                ft.Text(LOADING_HINT, size=scaled(12, window_width), color=MUTED),
            ]
        )
    elif state == AI_ERROR:
        message = forecast.explanation_error or ai_error or "неизвестная ошибка"
        content.append(
            error_banner(f"Не удалось получить AI-разбор: {message} Числа посчитаны локально.")
        )
    else:
        content.append(info_banner(NOT_CONFIGURED_TEXT))
    if forecast.sources:
        content.append(sources_line(forecast.sources, window_width=window_width))
    return apply_motion(
        ft.Container(
            content=ft.Column(content, spacing=10, tight=True),
            bgcolor=CARD,
            border=glass_border(),
            border_radius=12,
            padding=12,
        )
    )
