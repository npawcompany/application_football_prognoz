"""Russian match-day picker: month grid on the right, that day's matches on the left.

Flet's DatePicker cannot host custom content (and its header stays empty), so this is
a plain AlertDialog. Weeks start on Monday; today has a ring, the highlighted day is
filled, days with cached matches get a dot. The list on the left is read-only and
follows the highlighted day. Data comes through callbacks the app runs off the UI
thread; the dialog only paints what it is given.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from datetime import date

import flet as ft

from football_prognoz.domain.match import LIVE_STATUSES, Match
from football_prognoz.domain.team import Competition
from football_prognoz.services.calendar import (
    WEEKDAYS_SHORT_RU,
    by_kickoff,
    first_of_month,
    format_day_ru,
    month_bounds,
    month_grid,
    month_title_ru,
    shift_month,
)
from football_prognoz.ui.components.crest import crest_image
from football_prognoz.ui.formatters import format_kickoff_time
from football_prognoz.ui.motion import with_cursor
from football_prognoz.ui.runtime import safe_update
from football_prognoz.ui.theme import ACCENT, AWAY, CARD, FG, MUTED, SURFACE

DayLoader = Callable[[date, Callable[[date, list[Match], bool], None]], None]
MonthLoader = Callable[[date, date, Callable[[date, set[date]], None]], None]

CELL = 40
LIST_WIDTH = 300
GRID_WIDTH = CELL * 7 + 6 * 4


def cell_style(day: date, *, selected: date, today: date, marked: bool) -> dict[str, object]:
    """Visual state of a day cell (pure; tested)."""
    is_selected = day == selected
    is_today = day == today
    style: dict[str, object] = {
        "filled": is_selected,
        "ring": is_today,
        "dot": marked,
        "bold": is_selected or is_today,
        "weekend": day.weekday() >= 5,
    }
    return style


class MatchDayPicker:
    def __init__(
        self,
        *,
        day: date,
        today: date,
        on_pick: Callable[[date], None],
        load_day: DayLoader | None = None,
        load_month: MonthLoader | None = None,
        competitions: Mapping[str, Competition] | None = None,
    ) -> None:
        self.day = day
        self.today = today
        self.month = first_of_month(day)
        self.marked: set[date] = set()
        self.matches: list[Match] = []
        self.loading = False
        self._on_pick = on_pick
        self._load_day = load_day
        self._load_month = load_month
        self._competitions = competitions or {}
        self._page: ft.Page | None = None

        self._day_title = ft.Text("", size=18, weight=ft.FontWeight.W_600, color=FG)
        self._count = ft.Text("", size=12, color=MUTED)
        self._spinner = ft.ProgressRing(width=14, height=14, stroke_width=2, color=ACCENT)
        self._spinner_box = ft.Container(content=self._spinner, visible=False)
        self._list = ft.ListView(controls=[], spacing=6, expand=True, padding=0)
        self._month_title = ft.Text("", size=15, weight=ft.FontWeight.W_600, color=FG)
        self._grid = ft.Column([], spacing=4, tight=True)
        left = ft.Container(
            content=ft.Column(
                [
                    ft.Text("Матчи дня", size=12, color=MUTED),
                    self._day_title,
                    ft.Row([self._count, self._spinner_box], spacing=8),
                    ft.Divider(height=1, color=ft.Colors.with_opacity(0.12, FG)),
                    self._list,
                ],
                spacing=6,
                expand=True,
            ),
            width=LIST_WIDTH,
            padding=ft.Padding.only(right=16),
            border=ft.Border.only(right=ft.BorderSide(1, ft.Colors.with_opacity(0.12, FG))),
        )
        right = ft.Column(
            [
                ft.Row(
                    [
                        with_cursor(
                            ft.IconButton(
                                icon=ft.Icons.CHEVRON_LEFT,
                                tooltip="Предыдущий месяц",
                                on_click=lambda _e: self.show_month(-1),
                            ),
                            interactive=True,
                        ),
                        ft.Container(
                            content=self._month_title, expand=True, alignment=ft.Alignment.CENTER
                        ),
                        with_cursor(
                            ft.IconButton(
                                icon=ft.Icons.CHEVRON_RIGHT,
                                tooltip="Следующий месяц",
                                on_click=lambda _e: self.show_month(1),
                            ),
                            interactive=True,
                        ),
                    ],
                    width=GRID_WIDTH,
                ),
                self._grid,
                ft.Row(
                    [
                        self._legend_ring(),
                        ft.Text("сегодня", size=11, color=MUTED),
                        ft.Container(width=8),
                        ft.Container(width=6, height=6, bgcolor=ACCENT, border_radius=3),
                        ft.Text("есть матчи (в кэше)", size=11, color=MUTED),
                    ],
                    spacing=6,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                with_cursor(
                    ft.TextButton("Сегодня", on_click=lambda _e: self.select(self.today)),
                    interactive=True,
                ),
            ],
            spacing=8,
            tight=True,
        )
        self.dialog = ft.AlertDialog(
            modal=False,
            bgcolor=CARD,
            content_padding=ft.Padding.all(20),
            content=ft.Container(
                content=ft.Row(
                    [left, right],
                    spacing=16,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                ),
                height=400,
                width=LIST_WIDTH + GRID_WIDTH + 16,
            ),
            actions=[
                with_cursor(
                    ft.TextButton("Отмена", on_click=lambda _e: self.close()), interactive=True
                ),
                with_cursor(
                    ft.FilledButton(
                        "Показать",
                        bgcolor=ACCENT,
                        color="#0F172A",
                        on_click=lambda _e: self.confirm(),
                    ),
                    interactive=True,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self._sync()

    # --- lifecycle -------------------------------------------------------------------

    def open(self, page: ft.Page) -> None:
        self._page = page
        page.show_dialog(self.dialog)
        self._request_month()
        self._request_day()

    def close(self) -> None:
        page = self._page
        if page is not None:
            page.pop_dialog()

    def confirm(self) -> None:
        self.close()
        self._on_pick(self.day)

    # --- interaction -----------------------------------------------------------------

    def select(self, day: date) -> None:
        month_changed = first_of_month(day) != self.month
        self.day = day
        self.month = first_of_month(day)
        self.matches = []
        self._sync()
        self._paint()
        if month_changed:
            self._request_month()
        self._request_day()

    def show_month(self, step: int) -> None:
        self.month = shift_month(self.month, step)
        self._sync_grid()
        safe_update(self._grid, self._month_title)
        self._request_month()

    # --- data from the app (UI thread) -------------------------------------------------

    def deliver_day(self, day: date, matches: Iterable[Match], loading: bool) -> None:
        if day != self.day:
            return  # the user already moved on
        self.matches = by_kickoff(matches)
        self.loading = loading
        self._sync_list()
        safe_update(self._list, self._count, self._spinner_box)

    def deliver_month(self, month: date, days: Iterable[date]) -> None:
        first, last = month_bounds(month)
        self.marked = {d for d in self.marked if not first <= d <= last} | set(days)
        if first_of_month(month) == self.month:
            self._sync_grid()
            safe_update(self._grid)

    def _request_day(self) -> None:
        if self._load_day is None:
            return
        self.loading = True
        self._sync_list()
        safe_update(self._list, self._count, self._spinner_box)
        self._load_day(self.day, self.deliver_day)

    def _request_month(self) -> None:
        if self._load_month is None:
            return
        first, last = month_bounds(self.month)
        self._load_month(first, last, lambda _month, days: self.deliver_month(first, days))

    # --- rendering ---------------------------------------------------------------------

    def _paint(self) -> None:
        safe_update(
            self._grid,
            self._month_title,
            self._day_title,
            self._list,
            self._count,
            self._spinner_box,
        )

    def _sync(self) -> None:
        self._sync_grid()
        self._sync_list()

    def _legend_ring(self) -> ft.Control:
        return ft.Container(width=12, height=12, border_radius=6, border=ft.Border.all(1.5, ACCENT))

    def _cell(self, day: date | None) -> ft.Control:
        if day is None:
            return ft.Container(width=CELL, height=CELL)
        style = cell_style(day, selected=self.day, today=self.today, marked=day in self.marked)
        filled = bool(style["filled"])
        text_color = "#0F172A" if filled else (ACCENT if style["ring"] else FG)
        if not filled and not style["ring"] and style["weekend"]:
            text_color = ft.Colors.with_opacity(0.8, AWAY)
        dot_color = "#0F172A" if filled else ACCENT
        return with_cursor(
            ft.Container(
                content=ft.Column(
                    [
                        ft.Text(
                            str(day.day),
                            size=13,
                            color=text_color,
                            weight=ft.FontWeight.BOLD if style["bold"] else None,
                        ),
                        ft.Container(
                            width=5,
                            height=5,
                            border_radius=3,
                            bgcolor=dot_color if style["dot"] else None,
                        ),
                    ],
                    spacing=1,
                    tight=True,
                    alignment=ft.MainAxisAlignment.CENTER,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                width=CELL,
                height=CELL,
                border_radius=CELL / 2,
                bgcolor=ACCENT if filled else None,
                border=ft.Border.all(2, FG if filled else ACCENT) if style["ring"] else None,
                alignment=ft.Alignment.CENTER,
                ink=True,
                tooltip=format_day_ru(day, self.today),
                on_click=lambda _e, picked=day: self.select(picked),
                data=day,
            ),
            interactive=True,
        )

    def _sync_grid(self) -> None:
        self._month_title.value = month_title_ru(self.month)
        header = ft.Row(
            [
                ft.Container(
                    content=ft.Text(
                        name,
                        size=12,
                        color=MUTED if index < 5 else ft.Colors.with_opacity(0.8, AWAY),
                        weight=ft.FontWeight.W_600,
                    ),
                    width=CELL,
                    alignment=ft.Alignment.CENTER,
                )
                for index, name in enumerate(WEEKDAYS_SHORT_RU)
            ],
            spacing=4,
        )
        rows: list[ft.Control] = [header]
        for week in month_grid(self.month):
            rows.append(ft.Row([self._cell(day) for day in week], spacing=4))
        self._grid.controls = rows

    def _sync_list(self) -> None:
        self._day_title.value = format_day_ru(self.day, self.today)
        count = len(self.matches)
        if count:
            self._count.value = f"{count} {_matches_word(count)}"
        else:
            self._count.value = "Загружаем…" if self.loading else "Матчей нет"
        self._spinner_box.visible = self.loading
        self._list.controls = [self._row(match) for match in self.matches]

    def _row(self, match: Match) -> ft.Control:
        comp = self._competitions.get(match.competition_code)
        played = match.is_played or match.status in LIVE_STATUSES
        lead = ft.Text(
            match.score_label
            if played and match.score_label
            else format_kickoff_time(match.utc_date).split(" ")[0],
            size=13,
            weight=ft.FontWeight.W_600,
            color=ACCENT if played else FG,
            width=44,
        )
        return ft.Container(
            content=ft.Row(
                [
                    lead,
                    ft.Column(
                        [
                            ft.Row(
                                [
                                    crest_image(
                                        match.home_crest,
                                        label=match.home_name,
                                        size=16,
                                        team_id=match.home_id,
                                    ),
                                    ft.Text(
                                        match.home_name,
                                        size=12,
                                        color=FG,
                                        max_lines=1,
                                        overflow=ft.TextOverflow.ELLIPSIS,
                                        expand=True,
                                    ),
                                ],
                                spacing=6,
                            ),
                            ft.Row(
                                [
                                    crest_image(
                                        match.away_crest,
                                        label=match.away_name,
                                        size=16,
                                        team_id=match.away_id,
                                    ),
                                    ft.Text(
                                        match.away_name,
                                        size=12,
                                        color=FG,
                                        max_lines=1,
                                        overflow=ft.TextOverflow.ELLIPSIS,
                                        expand=True,
                                    ),
                                ],
                                spacing=6,
                            ),
                        ],
                        spacing=2,
                        tight=True,
                        expand=True,
                    ),
                    ft.Text(comp.code if comp else match.competition_code, size=10, color=MUTED),
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=SURFACE,
            border_radius=8,
            padding=ft.Padding.symmetric(horizontal=8, vertical=6),
        )


def _matches_word(count: int) -> str:
    tail = count % 100
    if 11 <= tail <= 14:
        return "матчей"
    return {1: "матч", 2: "матча", 3: "матча", 4: "матча"}.get(count % 10, "матчей")
