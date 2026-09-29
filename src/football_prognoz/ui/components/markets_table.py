"""«Таблица ставок»: bookmaker markets with the model's probability and fair odds.

Numbers come from `models/markets.py` only. LLM comments (validated against the table)
are shown under their rows; the three «наиболее обоснованные» rows get a star.
"""

from __future__ import annotations

import flet as ft

from football_prognoz.domain.markets import MARKET_GROUPS, Market, MarketsTable
from football_prognoz.domain.prediction import Explanation
from football_prognoz.ui.motion import apply_motion
from football_prognoz.ui.theme import (
    ACCENT,
    CARD,
    DRAW,
    FG,
    MUTED,
    SURFACE,
    glass_border,
    scaled,
)

FILTER_POPULAR = "popular"
FILTER_ALL = "all"
POPULAR_ROWS = 14
NARROW = 620

TITLE = "Таблица ставок"
SUBTITLE = (
    "Вероятность выигрыша по модели и справедливый коэффициент 1/p без маржи букмекера. "
    "Не совет ставить деньги."
)
CONFIDENCE_COLORS = {"high": ACCENT, "medium": DRAW, "low": MUTED}

# Selected filter per match id: survives repaints of the forecast pane.
_FILTERS: dict[int, str] = {}


def percent(value: float | None) -> str:
    if value is None:
        return "—"
    pct = value * 100
    if 0 < pct < 1:
        return "<1%"
    if 99 < pct < 100:
        return ">99%"
    return f"{pct:.0f}%"


def odds_text(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.2f}" if value < 100 else "99+"


def outcome_text(market: Market) -> str:
    """«в 45% · возврат 20% · п 35%» for markets with a refund, else empty."""
    if not market.has_push or market.win is None or market.lose is None:
        return ""
    return (
        f"выигрыш {percent(market.win)} · возврат {percent(market.push)} · "
        f"проигрыш {percent(market.lose)}"
    )


def visible_rows(table: MarketsTable, selected: str) -> list[Market]:
    if selected == FILTER_POPULAR:
        rows = [m for m in table.sorted() if m.available][:POPULAR_ROWS]
        return rows
    if selected == FILTER_ALL:
        return table.sorted()
    return table.in_group(selected)


def _confidence_chip(market: Market, width: int) -> ft.Control:
    color = CONFIDENCE_COLORS.get(market.confidence, MUTED)
    return ft.Container(
        content=ft.Text(
            market.confidence_label or "—", size=scaled(10, width), color=color, no_wrap=True
        ),
        border=ft.Border.all(1, ft.Colors.with_opacity(0.6, color)),
        border_radius=8,
        padding=ft.Padding.symmetric(horizontal=6, vertical=1),
        width=74,
        alignment=ft.Alignment.CENTER,
    )


def _bar(value: float, width: int) -> ft.Control:
    track = 90 if width >= NARROW else 56
    fill = max(2, round(track * min(1.0, max(0.0, value))))
    return ft.Stack(
        [
            ft.Container(width=track, height=6, bgcolor=SURFACE, border_radius=3),
            ft.Container(width=fill, height=6, bgcolor=ACCENT, border_radius=3),
        ],
        width=track,
        height=6,
    )


def market_row(
    market: Market,
    width: int,
    *,
    comment: str = "",
    top_reason: str | None = None,
) -> ft.Control:
    size = scaled(12, width)
    wide = width >= NARROW
    label_parts: list[ft.Control] = []
    if top_reason is not None:
        label_parts.append(ft.Icon(ft.Icons.STAR, size=14, color=DRAW, tooltip="AI: обоснованный"))
    label_parts.append(
        ft.Text(market.label, size=size, color=FG, weight=ft.FontWeight.W_500, expand=True)
    )
    cells: list[ft.Control] = [ft.Row(label_parts, spacing=4, expand=True)]
    if wide:
        cells.append(
            ft.Text(
                market.group_label, size=scaled(11, width), color=MUTED, width=150, no_wrap=True
            )
        )
    if market.available:
        eff = market.effective or 0.0
        cells.extend(
            [
                _bar(eff, width),
                ft.Text(
                    percent(eff),
                    size=size,
                    color=FG,
                    weight=ft.FontWeight.W_600,
                    width=46,
                    text_align=ft.TextAlign.RIGHT,
                ),
                ft.Text(
                    odds_text(market.fair_odds),
                    size=size,
                    color=FG,
                    width=48,
                    text_align=ft.TextAlign.RIGHT,
                    tooltip="Справедливый коэффициент без маржи",
                ),
                _confidence_chip(market, width),
            ]
        )
    else:
        cells.append(
            ft.Text(market.note, size=scaled(11, width), color=MUTED, italic=True, width=260)
        )
    lines: list[ft.Control] = [
        ft.Row(cells, spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER)
    ]
    extra = outcome_text(market)
    if extra:
        lines.append(ft.Text(extra, size=scaled(11, width), color=MUTED))
    for text, color in ((top_reason, DRAW), (comment, MUTED)):
        if text:
            lines.append(
                ft.Row(
                    [
                        ft.Icon(ft.Icons.AUTO_AWESOME, size=12, color=color),
                        ft.Text(text, size=scaled(11, width), color=FG, expand=True),
                    ],
                    spacing=6,
                )
            )
    return ft.Container(
        content=ft.Column(lines, spacing=3, tight=True),
        padding=ft.Padding.symmetric(horizontal=8, vertical=6),
        border=ft.Border.only(bottom=ft.BorderSide(1, ft.Colors.with_opacity(0.08, FG))),
    )


class MarketsTableCard(ft.Container):
    """Card with filter chips; repaints itself when a chip is clicked."""

    def __init__(
        self,
        table: MarketsTable,
        *,
        match_id: int,
        window_width: int,
        explanation: Explanation | None = None,
    ) -> None:
        super().__init__(
            bgcolor=CARD,
            border=glass_border(),
            border_radius=12,
            padding=12,
        )
        self.table = table
        self.match_id = match_id
        self.width_hint = window_width
        self.explanation = explanation
        self.selected = _FILTERS.get(match_id, FILTER_POPULAR)
        self._paint()

    def select(self, value: str) -> None:
        self.selected = value
        _FILTERS[self.match_id] = value
        self._paint()
        try:
            self.update()
        except (AssertionError, RuntimeError):
            pass  # not mounted (tests)

    def _chips(self) -> ft.Control:
        options = [(FILTER_POPULAR, "Популярные"), (FILTER_ALL, "Все")]
        options += [(g, MARKET_GROUPS[g]) for g in self.table.groups()]
        chips = []
        for key, label in options:
            active = key == self.selected
            chips.append(
                ft.Container(
                    content=ft.Text(
                        label,
                        size=scaled(11, self.width_hint),
                        color="#0F172A" if active else FG,
                        weight=ft.FontWeight.W_600 if active else ft.FontWeight.W_400,
                    ),
                    bgcolor=ACCENT if active else SURFACE,
                    border_radius=14,
                    padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                    on_click=lambda _e, k=key: self.select(k),
                    data=key,
                )
            )
        return ft.Row(chips, wrap=True, spacing=6, run_spacing=6)

    def _paint(self) -> None:
        width = self.width_hint
        comments: dict[str, str] = {}
        tops: dict[str, str] = {}
        if self.explanation is not None:
            comments = {c.market: c.comment for c in self.explanation.market_comments}
            tops = {c.market: c.comment for c in self.explanation.top_markets}
        rows = visible_rows(self.table, self.selected)
        header = ft.Row(
            [
                ft.Icon(ft.Icons.TABLE_CHART_OUTLINED, size=16, color=ACCENT),
                ft.Text(TITLE, size=scaled(15, width), weight=ft.FontWeight.W_600, color=FG),
                ft.Container(expand=True),
                ft.Text(
                    f"λ {self.table.lambda_home:.2f} : {self.table.lambda_away:.2f}",
                    size=scaled(11, width),
                    color=MUTED,
                    tooltip="Ожидаемые голы модели (хозяева : гости)",
                ),
            ],
            spacing=8,
        )
        columns = ft.Row(
            [
                ft.Text("Рынок", size=scaled(11, width), color=MUTED, expand=True),
                *(
                    [ft.Text("Тип", size=scaled(11, width), color=MUTED, width=150)]
                    if width >= NARROW
                    else []
                ),
                ft.Text(
                    "Вероятность",
                    size=scaled(11, width),
                    color=MUTED,
                    width=(90 if width >= NARROW else 56) + 56,
                    text_align=ft.TextAlign.RIGHT,
                ),
                ft.Text(
                    "Кэф",
                    size=scaled(11, width),
                    color=MUTED,
                    width=48,
                    text_align=ft.TextAlign.RIGHT,
                ),
                ft.Text(
                    "Уверенность",
                    size=scaled(11, width),
                    color=MUTED,
                    width=74,
                    text_align=ft.TextAlign.CENTER,
                ),
            ],
            spacing=10,
        )
        body: list[ft.Control] = [
            header,
            ft.Text(SUBTITLE, size=scaled(11, width), color=MUTED),
            self._chips(),
            ft.Container(content=columns, padding=ft.Padding.symmetric(horizontal=8)),
        ]
        body.extend(
            market_row(m, width, comment=comments.get(m.key, ""), top_reason=tops.get(m.key))
            for m in rows
        )
        if not rows:
            body.append(ft.Text("Нет рынков в этой группе.", size=scaled(12, width), color=MUTED))
        body.append(ft.Text(self.table.method, size=scaled(10, width), color=MUTED))
        self.content = ft.Column(body, spacing=6, tight=True)


def markets_card(
    table: MarketsTable | None,
    *,
    match_id: int,
    window_width: int,
    explanation: Explanation | None = None,
) -> ft.Control | None:
    if table is None:
        return None
    return apply_motion(
        MarketsTableCard(
            table, match_id=match_id, window_width=window_width, explanation=explanation
        )
    )
