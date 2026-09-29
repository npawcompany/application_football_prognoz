"""Leagues screen: search, area/type/activity filters and grouping, with greyed idle leagues.

Uses services.leagues — the same availability rules as the favourite-league combobox in
Settings. Persistent panel: filter controls are built once, only the list is repainted.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import flet as ft

from football_prognoz.domain.team import Competition
from football_prognoz.services.leagues import (
    LeagueFilter,
    LeagueGrouping,
    LeagueInfo,
    LeagueType,
    areas,
    filter_leagues,
    group_leagues,
)
from football_prognoz.ui.components.filter_bar import chip
from football_prognoz.ui.components.league_card import league_card
from football_prognoz.ui.components.section_header import section_header
from football_prognoz.ui.motion import with_cursor
from football_prognoz.ui.runtime import error_banner, info_banner, safe_update
from football_prognoz.ui.theme import (
    ACCENT,
    BG,
    BORDER,
    FG,
    LEAGUE_ASPECT_RATIO,
    MUTED,
    SURFACE,
    grid_extent,
)

ALL_AREAS = "__all__"


class LeaguesPanel:
    def __init__(
        self,
        *,
        on_select: Callable[[Competition], None],
        on_refresh: Callable[[], None],
    ) -> None:
        self._on_select = on_select
        self._on_refresh = on_refresh
        self.infos: list[LeagueInfo] = []
        self.favorite_codes: tuple[str, ...] = ()
        self.selected_code: str | None = None
        self.flt = LeagueFilter()
        self.grouping = LeagueGrouping.NONE
        self.loading = False
        self.error: str | None = None
        self.window_width = 1440

        self._search = ft.TextField(
            value="",
            hint_text="Название, код или страна",
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
            on_change=lambda e: self.update_filter(query=str(e.control.value or "")),
        )
        self._area = ft.Dropdown(
            value=ALL_AREAS,
            options=[ft.DropdownOption(key=ALL_AREAS, text="Все страны")],
            dense=True,
            filled=True,
            fill_color=SURFACE,
            bgcolor=SURFACE,
            color=FG,
            border_color=BORDER,
            focused_border_color=ACCENT,
            border_radius=8,
            text_size=13,
            width=200,
            menu_height=360,
            label="Страна / регион",
            on_select=self._on_area,
        )
        self._active = ft.Switch(
            label="Только с матчами",
            value=False,
            active_color=ACCENT,
            label_text_style=ft.TextStyle(color=FG, size=12),
            on_change=lambda e: self.update_filter(active_only=bool(e.control.value)),
        )
        self._type_row = ft.Row([], spacing=6, run_spacing=6, wrap=True)
        self._group_row = ft.Row([], spacing=6, run_spacing=6, wrap=True)
        self._summary = ft.Text("", size=11, color=MUTED)
        self._banner = ft.Column([], spacing=6)
        self._list = ft.ListView(controls=[], expand=True, spacing=10, padding=0)
        header = section_header(
            "Лиги",
            "Бесплатный план football-data.org: 12 соревнований.",
            trailing=with_cursor(
                ft.IconButton(
                    icon=ft.Icons.REFRESH,
                    tooltip="Обновить",
                    on_click=lambda _e: self._on_refresh(),
                ),
                interactive=True,
            ),
        )
        self.control = ft.Container(
            content=ft.Column(
                [
                    header,
                    ft.Row([self._search], spacing=8),
                    ft.Row(
                        [self._area, self._active],
                        spacing=12,
                        run_spacing=8,
                        wrap=True,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    self._type_row,
                    self._group_row,
                    self._summary,
                    self._banner,
                    ft.Container(content=self._list, expand=True),
                ],
                spacing=10,
                expand=True,
            ),
            expand=True,
            bgcolor=BG,
        )
        self._sync()

    # --- data from the app ---------------------------------------------------------

    def set_data(
        self,
        infos: Sequence[LeagueInfo],
        *,
        favorite_codes: Sequence[str] = (),
        selected_code: str | None = None,
        loading: bool = False,
        error: str | None = None,
    ) -> None:
        self.infos = list(infos)
        self.favorite_codes = tuple(code.upper() for code in favorite_codes)
        self.selected_code = selected_code
        self.loading = loading
        self.error = error
        known = areas(self.infos)
        if self.flt.area and self.flt.area not in known:
            self.flt = LeagueFilter(**{**self.flt.__dict__, "area": ""})
        self._area.options = [ft.DropdownOption(key=ALL_AREAS, text="Все страны")] + [
            ft.DropdownOption(key=name, text=name) for name in known
        ]
        self._area.value = self.flt.area or ALL_AREAS
        self.repaint()

    def update_filter(self, **changes: object) -> None:
        values = {**self.flt.__dict__, **changes}
        self.flt = LeagueFilter(**values)  # type: ignore[arg-type]
        self.repaint()

    def set_grouping(self, grouping: LeagueGrouping) -> None:
        self.grouping = grouping
        self.repaint()

    def _on_area(self, event: ft.ControlEvent) -> None:
        value = str(getattr(event.control, "value", "") or "")
        self.update_filter(area="" if value in ("", ALL_AREAS) else value)

    # --- rendering -----------------------------------------------------------------

    def visible_groups(self) -> list[tuple[str, list[LeagueInfo]]]:
        picked = filter_leagues(self.infos, self.flt, self.favorite_codes)
        return group_leagues(picked, self.grouping, self.favorite_codes)

    def repaint(self) -> None:
        self._sync()
        safe_update(self._area, self._type_row, self._group_row, self._summary, self._banner)
        safe_update(self._list)

    def _sync(self) -> None:
        flt = self.flt
        type_chips = [
            chip(
                "Все",
                flt.league_type is LeagueType.ALL,
                lambda: self.update_filter(league_type=LeagueType.ALL),
            ),
            chip(
                "Лиги",
                flt.league_type is LeagueType.LEAGUE,
                lambda: self.update_filter(league_type=LeagueType.LEAGUE),
            ),
            chip(
                "Кубки",
                flt.league_type is LeagueType.CUP,
                lambda: self.update_filter(league_type=LeagueType.CUP),
            ),
        ]
        if self.favorite_codes:
            type_chips.append(
                chip(
                    "★ Любимые",
                    flt.favorites_only,
                    lambda: self.update_filter(favorites_only=not self.flt.favorites_only),
                )
            )
        self._type_row.controls = type_chips
        self._group_row.controls = [
            ft.Text("Группировать:", size=12, color=MUTED),
            chip(
                "Без групп",
                self.grouping is LeagueGrouping.NONE,
                lambda: self.set_grouping(LeagueGrouping.NONE),
            ),
            chip(
                "По стране",
                self.grouping is LeagueGrouping.AREA,
                lambda: self.set_grouping(LeagueGrouping.AREA),
            ),
            chip(
                "По типу",
                self.grouping is LeagueGrouping.TYPE,
                lambda: self.set_grouping(LeagueGrouping.TYPE),
            ),
        ]
        self._active.value = flt.active_only
        groups = self.visible_groups()
        shown = sum(len(items) for _title, items in groups)
        self._summary.value = f"Показано {shown} из {len(self.infos)}"
        banners: list[ft.Control] = []
        if self.error:
            banners.append(error_banner(self.error))
        if self.loading:
            banners.append(
                ft.Row(
                    [
                        ft.ProgressRing(width=16, height=16, stroke_width=2, color=ACCENT),
                        ft.Text("Обновляем список лиг…", size=12, color=MUTED),
                    ],
                    spacing=8,
                )
            )
        if not self.infos and not self.loading:
            banners.append(
                info_banner("Нет лиг. Проверьте ключ API в Настройках.", "Откройте Настройки")
            )
        elif self.infos and not groups:
            banners.append(info_banner("Под фильтр не подходит ни одна лига."))
        self._banner.controls = banners
        rows: list[ft.Control] = []
        for title, items in groups:
            if title:
                rows.append(
                    ft.Text(
                        f"{title} · {len(items)}", size=13, weight=ft.FontWeight.W_600, color=FG
                    )
                )
            rows.append(self._grid(items))
        self._list.controls = rows

    def _grid(self, items: list[LeagueInfo]) -> ft.Control:
        extent = grid_extent(self.window_width)
        cards = [
            ft.Container(
                content=with_cursor(
                    league_card(
                        info.competition,
                        self._on_select,
                        selected=info.code == self.selected_code,
                        note=info.note,
                        dimmed=info.disabled,
                        favorite=info.code.upper() in self.favorite_codes,
                    ),
                    interactive=True,
                ),
                width=extent,
                height=round(extent / LEAGUE_ASPECT_RATIO),
            )
            for info in items
        ]
        # A wrapping Row of fixed-size tiles (no expand children — see ui_check).
        return ft.Row(cards, wrap=True, spacing=10, run_spacing=10)
