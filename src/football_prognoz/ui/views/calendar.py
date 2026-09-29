"""Day calendar: date picker, day paging, league filter with match-day jumps, grouping.

A persistent panel: the app keeps one instance, feeds it data and only the list block
(or the header) is repainted. Filters (grouping, team search) are applied locally, so
typing in the search box never re-creates the field and never waits for the network.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime, timedelta

import flet as ft

from football_prognoz.domain.match import Match
from football_prognoz.domain.team import Competition
from football_prognoz.services.calendar import (
    GroupMode,
    MatchGroup,
    format_day_ru,
    group_day_matches,
)
from football_prognoz.ui.components.crest import crest_image
from football_prognoz.ui.components.day_picker import DayLoader, MatchDayPicker, MonthLoader
from football_prognoz.ui.components.filter_bar import chip
from football_prognoz.ui.components.match_card import match_card
from football_prognoz.ui.motion import with_cursor
from football_prognoz.ui.runtime import (
    disclaimer,
    error_banner,
    info_banner,
    is_mounted,
    safe_update,
)
from football_prognoz.ui.theme import (
    ACCENT,
    BORDER,
    FG,
    MUTED,
    PANE_BG,
    SURFACE,
    glass_border,
    use_stacked_match,
)

FIRST_DAY = date(2000, 1, 1)
LAST_DAY = date(2100, 12, 31)


class CalendarPanel:
    """Matches of one day. Callbacks go to the app; grouping/search stay local."""

    def __init__(
        self,
        *,
        on_day: Callable[[date], None],
        on_open: Callable[[Match], None],
        on_refresh: Callable[[], None],
        on_clear_league: Callable[[], None],
        on_jump: Callable[[int], None],
        on_collapse: Callable[[], None] | None = None,
        today: Callable[[], date] = date.today,
        load_picker_day: DayLoader | None = None,
        load_picker_month: MonthLoader | None = None,
    ) -> None:
        self._on_day = on_day
        self._on_open = on_open
        self._on_refresh = on_refresh
        self._on_clear_league = on_clear_league
        self._on_jump = on_jump
        self._on_collapse = on_collapse
        self._today = today
        self._load_picker_day = load_picker_day
        self._load_picker_month = load_picker_month
        self.picker: MatchDayPicker | None = None
        self.day: date = today()
        self.mode = GroupMode.LEAGUE
        self.team_query = ""
        self.matches: list[Match] = []
        self.competitions: Mapping[str, Competition] = {}
        self.favorite_codes: tuple[str, ...] = ()
        self.favorite_team_ids: tuple[int, ...] = ()
        self.league: Competition | None = None
        self.league_days: tuple[date, ...] = ()
        self.selected_match_id: int | None = None
        self.loading = False
        self.error: str | None = None
        self.notice: str | None = None
        self.window_width = 1440
        self.compact = False
        self.embedded = True
        self.show_disclaimer = True
        self.collapsible = False  # the hide button makes sense only next to the forecast

        self._title = ft.Text("", size=18, weight=ft.FontWeight.BOLD, color=FG, max_lines=1)
        self._spinner = ft.ProgressRing(width=16, height=16, stroke_width=2, color=ACCENT)
        self._spinner_box = ft.Container(content=self._spinner, visible=False, tooltip="Обновляем")
        self._date_button = ft.OutlinedButton(
            content=ft.Row(
                [ft.Icon(ft.Icons.CALENDAR_MONTH, size=16, color=ACCENT), self._title_small()],
                spacing=6,
                tight=True,
            ),
            tooltip="Выбрать дату",
            on_click=self._open_picker,
        )
        self._league_row = ft.Row([], spacing=6, run_spacing=6, visible=False, wrap=True)
        self._mode_row = ft.Row([], spacing=6)
        self._search = ft.TextField(
            value="",
            hint_text="Команда",
            prefix_icon=ft.Icons.SEARCH,
            dense=True,
            filled=True,
            bgcolor=SURFACE,
            fill_color=SURFACE,
            color=FG,
            border_color=BORDER,
            focused_border_color=ACCENT,
            cursor_color=ACCENT,
            text_size=13,
            content_padding=ft.Padding.symmetric(horizontal=10, vertical=6),
            border_radius=8,
            expand=True,
            on_change=self._on_search,
        )
        self._banner = ft.Column([], spacing=6)
        self._list = ft.ListView(controls=[], expand=True, spacing=8, padding=0)
        self._disclaimer = ft.Container(content=disclaimer())
        self.control = ft.Container(expand=True, bgcolor=PANE_BG, content=self._layout())
        self._sync_header()
        self._sync_list()

    # --- building blocks -----------------------------------------------------------

    def _title_small(self) -> ft.Text:
        self._day_label = ft.Text("", size=13, color=FG, weight=ft.FontWeight.W_600)
        return self._day_label

    def _layout(self) -> ft.Control:
        nav = ft.Row(
            [
                with_cursor(
                    ft.IconButton(
                        icon=ft.Icons.CHEVRON_LEFT,
                        tooltip="Предыдущий день",
                        on_click=lambda _e: self.shift_day(-1),
                    ),
                    interactive=True,
                ),
                with_cursor(self._date_button, interactive=True),
                with_cursor(
                    ft.IconButton(
                        icon=ft.Icons.CHEVRON_RIGHT,
                        tooltip="Следующий день",
                        on_click=lambda _e: self.shift_day(1),
                    ),
                    interactive=True,
                ),
                with_cursor(
                    ft.TextButton("Сегодня", on_click=lambda _e: self.go_to(self._today())),
                    interactive=True,
                ),
            ],
            spacing=2,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        trailing: list[ft.Control] = [
            self._spinner_box,
            with_cursor(
                ft.IconButton(
                    icon=ft.Icons.REFRESH,
                    tooltip="Обновить день",
                    on_click=lambda _e: self._on_refresh(),
                ),
                interactive=True,
            ),
        ]
        self._collapse_box = ft.Container(visible=False)
        if self._on_collapse is not None:
            self._collapse_box.content = with_cursor(
                ft.IconButton(
                    icon=ft.Icons.KEYBOARD_DOUBLE_ARROW_LEFT,
                    tooltip="Скрыть список матчей",
                    on_click=lambda _e: self._on_collapse and self._on_collapse(),
                ),
                interactive=True,
            )
        trailing.append(self._collapse_box)
        header = ft.Row(
            [
                ft.Column(
                    [ft.Text("Календарь", size=12, color=MUTED), self._title],
                    spacing=0,
                    expand=True,
                ),
                *trailing,
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        return ft.Column(
            [
                header,
                nav,
                self._league_row,
                ft.Row([self._search], spacing=8),
                self._mode_row,
                self._disclaimer,
                self._banner,
                ft.Container(content=self._list, expand=True),
            ],
            spacing=10,
            expand=True,
        )

    # --- state changes from the app ------------------------------------------------

    def set_data(
        self,
        matches: Sequence[Match],
        *,
        loading: bool | None = None,
        error: str | None = None,
        notice: str | None = None,
    ) -> None:
        self.matches = list(matches)
        if loading is not None:
            self.loading = loading
        self.error = error
        self.notice = notice
        self.refresh()

    def set_loading(self, loading: bool) -> None:
        self.loading = loading
        self._spinner_box.visible = loading
        safe_update(self._spinner_box)

    def set_league(self, league: Competition | None, days: Sequence[date] = ()) -> None:
        self.league = league
        self.league_days = tuple(days)
        self._sync_header()
        safe_update(self._league_row)

    def refresh(self) -> None:
        """Repaint header + list (never the search field, so typing keeps focus)."""
        self._sync_header()
        self._sync_list()
        safe_update(
            self._title,
            self._day_label,
            self._spinner_box,
            self._league_row,
            self._mode_row,
            self._banner,
            self._list,
            self._disclaimer,
            self._collapse_box,
        )

    # --- user actions --------------------------------------------------------------

    def go_to(self, day: date) -> None:
        if day == self.day:
            self._on_day(day)  # same day: still refresh from cache/network
            return
        self.day = day
        self.matches = []
        self.error = None
        self.notice = None
        self._sync_header()
        safe_update(self._title, self._day_label, self._league_row)
        self._on_day(day)

    def shift_day(self, step: int) -> None:
        self.go_to(self.day + timedelta(days=step))

    def set_mode(self, mode: GroupMode) -> None:
        self.mode = mode
        self._sync_header()
        self._sync_list()
        safe_update(self._mode_row, self._list)

    def set_team_query(self, text: str) -> None:
        self.team_query = text
        self._sync_list()
        safe_update(self._banner, self._list)

    def _on_search(self, event: ft.ControlEvent) -> None:
        self.set_team_query(str(event.control.value or ""))

    def _open_picker(self, _event: ft.ControlEvent | None = None) -> None:
        if not is_mounted(self.control):
            return
        page = self.control.page
        if self._load_picker_day is not None:
            # Russian month grid + the plain list of that day's matches (see day_picker).
            self.picker = MatchDayPicker(
                day=self.day,
                today=self._today(),
                on_pick=self.go_to,
                load_day=self._load_picker_day,
                load_month=self._load_picker_month,
                competitions=self.competitions,
            )
            self.picker.open(page)
            return
        picker = ft.DatePicker(
            locale=ft.Locale("ru", "RU"),
            value=datetime.combine(self.day, datetime.min.time()),
            first_date=datetime.combine(FIRST_DAY, datetime.min.time()),
            last_date=datetime.combine(LAST_DAY, datetime.min.time()),
            help_text="Дата матчей",
            cancel_text="Отмена",
            confirm_text="Показать",
            on_change=self._on_picked,
        )
        page.show_dialog(picker)

    def _on_picked(self, event: ft.ControlEvent) -> None:
        value = getattr(event.control, "value", None)
        if isinstance(value, datetime):
            # Flet sends the picked day as local midnight (sometimes in UTC); keep the
            # calendar date the user tapped.
            picked = value.astimezone().date() if value.tzinfo else value.date()
            self.go_to(picked)
        elif isinstance(value, date):
            self.go_to(value)

    # --- rendering -----------------------------------------------------------------

    def _sync_header(self) -> None:
        label = format_day_ru(self.day, self._today())
        self._title.value = self.league.name if self.league else label
        self._day_label.value = label
        self._spinner_box.visible = self.loading
        self._disclaimer.visible = self.show_disclaimer
        self._collapse_box.visible = self.collapsible and self._on_collapse is not None
        self._mode_row.controls = [
            chip(
                "По лигам", self.mode is GroupMode.LEAGUE, lambda: self.set_mode(GroupMode.LEAGUE)
            ),
            chip("По командам", self.mode is GroupMode.TEAM, lambda: self.set_mode(GroupMode.TEAM)),
        ]
        if self.league is None:
            self._league_row.visible = False
            self._league_row.controls = []
            return
        league = self.league
        self._league_row.visible = True
        prev_day = max((d for d in self.league_days if d < self.day), default=None)
        next_day = min((d for d in self.league_days if d > self.day), default=None)
        self._league_row.controls = [
            ft.Container(
                content=ft.Row(
                    [
                        crest_image(league.emblem, label=league.name, size=16, code=league.code),
                        ft.Text(league.name, size=12, color=FG, max_lines=1),
                        ft.IconButton(
                            icon=ft.Icons.CLOSE,
                            icon_size=14,
                            tooltip="Все лиги",
                            style=ft.ButtonStyle(padding=0),
                            on_click=lambda _e: self._on_clear_league(),
                        ),
                    ],
                    spacing=6,
                    tight=True,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                bgcolor=SURFACE,
                border=glass_border(),
                border_radius=8,
                padding=ft.Padding.only(left=8, right=2),
            ),
            with_cursor(
                ft.TextButton(
                    "← Пред. игровой день",
                    disabled=prev_day is None,
                    tooltip=format_day_ru(prev_day, self._today()) if prev_day else None,
                    on_click=lambda _e: self._on_jump(-1),
                ),
                interactive=True,
            ),
            with_cursor(
                ft.TextButton(
                    "След. игровой день →",
                    disabled=next_day is None,
                    tooltip=format_day_ru(next_day, self._today()) if next_day else None,
                    on_click=lambda _e: self._on_jump(1),
                ),
                interactive=True,
            ),
        ]

    def groups(self) -> list[MatchGroup]:
        return group_day_matches(
            self.matches,
            self.competitions,
            mode=self.mode,
            favorite_team_ids=self.favorite_team_ids,
            favorite_codes=self.favorite_codes,
            team_query=self.team_query,
        )

    def _sync_list(self) -> None:
        banners: list[ft.Control] = []
        if self.error:
            banners.append(error_banner(self.error))
        if self.notice:
            banners.append(info_banner(self.notice))
        groups = self.groups()
        if not groups:
            if self.loading:
                text = "Загружаем матчи дня…"
            elif self.team_query.strip() and self.matches:
                text = "Нет матчей с такой командой в этот день."
            elif self.league is not None:
                text = "В этот день у лиги нет матчей. Перейдите к ближайшему игровому дню."
            else:
                text = "В этот день матчей нет."
            banners.append(info_banner(text))
        self._banner.controls = banners
        narrow = use_stacked_match(self.window_width)
        rows: list[ft.Control] = []
        for group in groups:
            rows.append(self._group_header(group))
            rows.extend(
                with_cursor(
                    match_card(
                        item,
                        self._on_open,
                        compact=self.compact or self.embedded,
                        selected=item.id == self.selected_match_id,
                        narrow=narrow,
                        window_width=self.window_width,
                    ),
                    interactive=True,
                )
                for item in group.matches
            )
        self._list.controls = rows

    def _group_header(self, group: MatchGroup) -> ft.Control:
        if group.code:
            mark: ft.Control = crest_image(
                group.emblem, label=group.title, size=18, code=group.code
            )
        elif group.key.startswith("team:"):
            team_id = int(group.key.split(":", 1)[1])
            mark = crest_image(group.crest, label=group.title, size=18, team_id=team_id)
        else:
            mark = ft.Icon(ft.Icons.STAR, size=16, color=ACCENT)
        count = len(group.matches)
        return ft.Container(
            content=ft.Row(
                [
                    mark,
                    ft.Text(
                        group.title,
                        size=13,
                        weight=ft.FontWeight.W_600,
                        color=ACCENT if group.favorite else FG,
                        expand=True,
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                    ft.Text(str(count), size=12, color=MUTED),
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.only(top=6, bottom=2),
        )

    def select_match(self, match_id: int | None) -> None:
        if match_id == self.selected_match_id:
            return
        self.selected_match_id = match_id
        self._sync_list()
        safe_update(self._list)
