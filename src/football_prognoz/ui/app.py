from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime
from pathlib import Path

import flet as ft

from football_prognoz.config import (
    DEFAULT_OLLAMA_FALLBACK_MODEL,
    DEFAULT_OLLAMA_MODEL,
    EXPORTS_DIR,
    OLLAMA_CLOUD_HOST,
    Settings,
    load_settings,
    write_env_value,
)
from football_prognoz.domain.match import Match
from football_prognoz.domain.prediction import MatchForecast
from football_prognoz.domain.team import Competition, Team
from football_prognoz.services.calendar import local_tz, match_days, nearest_day
from football_prognoz.services.factory import build_service
from football_prognoz.services.leagues import LeagueInfo, league_infos
from football_prognoz.services.matches import Cancelled, MatchService
from football_prognoz.services.startup import SPLASH_MIN_SECONDS, GateState, KeyGate, SplashTimer
from football_prognoz.ui.components.ai_analysis import (
    AI_ERROR,
    AI_LOADING,
    AI_NOT_CONFIGURED,
    AI_READY,
)
from football_prognoz.ui.components.crest import load_crest_manifest
from football_prognoz.ui.components.settings_panel import SettingsForm
from football_prognoz.ui.components.splash import splash_view, start_spin
from football_prognoz.ui.components.training_panel import (
    TrainingState,
    calibration_lines,
    training_panel,
)
from football_prognoz.ui.motion import PAGE_CURSOR, with_cursor
from football_prognoz.ui.notify import notify_user
from football_prognoz.ui.runtime import (
    Job,
    debounce,
    info_banner,
    is_mounted,
    post_to_ui,
    run_background,
    run_detached,
    safe_update,
)
from football_prognoz.ui.save_dialog import (
    DIALOG_TIMEOUT_S,
    SaveDialogUnavailable,
    choose_save_path_macos,
    dialog_kind,
)
from football_prognoz.ui.theme import (
    BG,
    BODY_PADDING,
    configure_window,
    use_rail,
    use_split,
    window_width,
)
from football_prognoz.ui.views.calendar import CalendarPanel
from football_prognoz.ui.views.leagues import LeaguesPanel
from football_prognoz.ui.views.match_detail import match_detail_view
from football_prognoz.ui.views.settings import settings_view

SECTIONS = ("leagues", "fixtures", "match", "settings")
NAV_INDEX = {name: index for index, name in enumerate(SECTIONS)}
FORECAST_SECTIONS = frozenset({"fixtures", "match"})

EXPORT_DIALOG_TITLE = "Куда сохранить историю прогнозов"

_TRUE = frozenset({"1", "true", "yes", "on"})


def _env_flag(value: str | bool) -> str:
    if isinstance(value, str):
        return "true" if value.strip().lower() in _TRUE else "false"
    return "true" if value else "false"


def _env_text(value: str | bool | None, default: str = "") -> str:
    if value is None or isinstance(value, bool):
        return default
    text = str(value).strip()
    return text if text else default


@dataclass(frozen=True)
class SettingsChoices:
    teams: tuple[Team, ...] = ()
    by_league: tuple[tuple[Competition, tuple[Team, ...]], ...] = ()


@dataclass
class BootResult:
    competitions: list[Competition]
    infos: list[LeagueInfo] = field(default_factory=list)
    rejected: bool = False
    error: str | None = None
    choices: SettingsChoices | None = None


__all__ = ["FootballApp", "build_service", "start_ui"]


class FootballApp:
    def __init__(
        self,
        page: ft.Page,
        service: MatchService,
        settings: Settings,
        *,
        splash_min_seconds: float = SPLASH_MIN_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        today: Callable[[], date] = date.today,
    ) -> None:
        self.page = page
        self.service = service
        self.settings = settings
        self.section = "fixtures"
        self.competitions: list[Competition] = []
        self.league_infos: list[LeagueInfo] = []
        self.forecast: MatchForecast | None = None
        self.league: Competition | None = None
        self.selected_match_id: int | None = None
        self.loading = False
        self.busy: str | None = None
        self.error: str | None = None
        self.status: str | None = None
        self.booting = False
        self.ai_state: str | None = None
        self.ai_error: str | None = None
        self.training = TrainingState()
        self.counting: str | None = None
        self.calendar_collapsed = False
        self.gate = KeyGate.from_settings(settings)
        self._splash_min = splash_min_seconds
        self._clock = clock
        self._today = today
        self.splash = SplashTimer(splash_min_seconds, clock)
        self._boot_result: BootResult | None = None
        self._ai_job = Job()
        self._day_job = Job()
        self._league_job = Job()
        self._ai_interrupted = False
        self._training_cancel: threading.Event | None = None
        self._training_painted_at = 0.0
        self._teams_by_league: list[tuple[Competition, list[Team]]] = []
        self._teams: tuple[Team, ...] = ()
        self._choices: SettingsChoices | None = None
        self._calendar_key: tuple[date, tuple[str, ...]] | None = None
        self._picker: ft.FilePicker | None = None
        self._mac_chooser = choose_save_path_macos
        self._splash_message = "Загружаем данные…"
        self._splash_fraction: float | None = None
        self._splash_control: ft.Control | None = None
        self._training_slot = ft.Container()
        self.leagues_panel = LeaguesPanel(
            on_select=self._select_league,
            on_refresh=lambda: self._load_leagues(force=True),
        )
        self.calendar = CalendarPanel(
            on_day=lambda _day: self._load_day(),
            on_open=self._open_match,
            on_refresh=lambda: self._load_day(force=True),
            on_clear_league=self._clear_league,
            on_jump=self._jump_league_day,
            on_collapse=self._toggle_calendar,
            today=today,
        )
        self._pane = ft.Container(expand=True, padding=BODY_PADDING, bgcolor=BG)
        self.body = with_cursor(
            ft.Container(expand=True, padding=0, bgcolor=BG),
            PAGE_CURSOR,
        )
        self.body.expand = True
        self._left_slot = ft.Container(expand=3, bgcolor=BG, padding=ft.Padding.only(right=8))
        self._right_slot = ft.Container(expand=2, bgcolor=BG, padding=ft.Padding.only(left=8))
        self._split_row = ft.Row(
            [
                self._left_slot,
                ft.VerticalDivider(
                    width=1,
                    color=ft.Colors.with_opacity(0.18, ft.Colors.WHITE),
                ),
                self._right_slot,
            ],
            expand=True,
            spacing=0,
            vertical_alignment=ft.CrossAxisAlignment.STRETCH,
        )
        self._pane_kind: str | None = None
        self._rail: ft.NavigationRail | None = None
        self._nav_bar: ft.NavigationBar | None = None
        self._rail_mode: bool | None = None
        self._split_mode: bool | None = None
        self._build_shell()
        self._start_boot()

    # --- compatibility helpers --------------------------------------------------------

    @property
    def matches(self) -> list[Match]:
        """Matches of the calendar day currently shown."""
        return self.calendar.matches

    # --- shell / navigation ------------------------------------------------------------

    def _build_shell(self) -> None:
        page = self.page
        configure_window(page)
        page.title = "Football Prognoz"
        page.appbar = ft.AppBar(
            title=ft.Text("Football Prognoz", size=16, weight=ft.FontWeight.W_600),
            center_title=False,
            bgcolor=BG,
            toolbar_height=44,
        )
        page.on_resize = self._on_resized
        page.on_resized = self._on_resized
        self._rebuild_chrome()
        page.add(self.body)

    def _rebuild_chrome(self) -> None:
        width = window_width(self.page)
        rail = use_rail(width)
        self._rail_mode = rail
        self._split_mode = use_split(width)
        if rail:
            self._rail = self._navigation_rail()
            self._nav_bar = None
            self.page.navigation_bar = None
            self.body.content = ft.Row(
                [
                    self._rail,
                    ft.VerticalDivider(
                        width=1,
                        color=ft.Colors.with_opacity(0.18, ft.Colors.WHITE),
                    ),
                    self._pane,
                ],
                expand=True,
                spacing=0,
            )
            return
        self._rail = None
        self._nav_bar = self._navigation_bar()
        self.page.navigation_bar = self._nav_bar
        self.body.content = self._pane

    def _on_resized(self, _event: object | None = None) -> None:
        debounce(self.page, "resize", 0.15, self._on_resized_apply)

    def _on_resized_apply(self) -> None:
        width = window_width(self.page)
        rail = use_rail(width)
        split = use_split(width)
        if rail != self._rail_mode or split != self._split_mode:
            self._rebuild_chrome()
        self._render_panes()

    def _sync_nav_selection(self) -> None:
        """Keep the rail/bar highlight in sync, also for programmatic navigation."""
        index = self._nav_index()
        for nav in (self._rail, self._nav_bar):
            if nav is None or nav.selected_index == index:
                continue
            nav.selected_index = index
            safe_update(nav)

    def _on_nav(self, event: ft.ControlEvent) -> None:
        index = self._nav_event_index(event)
        wanted = SECTIONS[index] if 0 <= index < len(SECTIONS) else "fixtures"
        if self.booting:
            # The splash stays until loading is done; the gate decides afterwards.
            self._sync_nav_selection()
            self._paint_nav()
            return
        self.error = None
        self._set_section(wanted)
        if self.section == "leagues" and not self.league_infos:
            self._load_leagues()
            return
        self._render_panes()

    def _paint_nav(self) -> None:
        safe_update(*(c for c in (self._rail, self._nav_bar) if c is not None))

    def _nav_event_index(self, event: ft.ControlEvent) -> int:
        data = getattr(event, "data", None)
        if data is not None and str(data).strip() != "":
            try:
                return int(data)
            except (TypeError, ValueError):
                pass
        control = getattr(event, "control", None)
        selected = getattr(control, "selected_index", None)
        if selected is not None:
            try:
                return int(selected)
            except (TypeError, ValueError):
                pass
        return self._nav_index()

    def _set_section(self, section: str) -> None:
        """Every navigation goes through the key gate and the AI-job lifecycle."""
        target = self.gate.target(section)
        if target != section:
            self._notify(self.gate.notice(), kind="info")
        leaving_forecast = self.section in FORECAST_SECTIONS and target not in FORECAST_SECTIONS
        self.section = target
        if leaving_forecast and self._ai_job.running:
            self._ai_job.stop()
            self._ai_interrupted = True
            if self.ai_state == AI_LOADING:
                self.ai_state = None
        if target in FORECAST_SECTIONS and self._ai_interrupted and self.forecast is not None:
            self._ai_interrupted = False
            self._start_enrichment(self.forecast, repaint=False)
        if target == "settings":
            self._load_settings_choices()

    def _set_nav(self, section: str) -> None:
        self._set_section(section)

    def _nav_index(self) -> int:
        return NAV_INDEX.get(self.section, 0)

    def _destinations(self) -> list[tuple[str, str]]:
        return [
            (ft.Icons.SPORTS_SOCCER, "Лиги"),
            (ft.Icons.CALENDAR_MONTH, "Календарь"),
            (ft.Icons.QUERY_STATS, "Прогноз"),
            (ft.Icons.SETTINGS, "Настройки"),
        ]

    def _navigation_rail(self) -> ft.NavigationRail:
        label_type = getattr(ft, "NavigationRailLabelType", None)
        kwargs: dict[str, object] = {}
        if label_type is not None:
            kwargs["label_type"] = label_type.ALL
        return ft.NavigationRail(
            selected_index=self._nav_index(),
            min_width=88,
            bgcolor=BG,
            destinations=[
                ft.NavigationRailDestination(icon=icon, label=label)
                for icon, label in self._destinations()
            ],
            on_change=self._on_nav,
            **kwargs,
        )

    def _navigation_bar(self) -> ft.NavigationBar:
        return ft.NavigationBar(
            selected_index=self._nav_index(),
            destinations=[
                ft.NavigationBarDestination(icon=icon, label=label)
                for icon, label in self._destinations()
            ],
            on_change=self._on_nav,
        )

    # --- painting ----------------------------------------------------------------------

    def _paint(self, *controls: ft.Control) -> None:
        """Update only the given blocks when they are already on the page."""
        try:
            mounted = self._pane.page is not None
        except RuntimeError:
            mounted = False
        if not mounted:
            self.page.update()
            return
        try:
            for control in controls:
                control.update()
        except Exception:  # noqa: BLE001 — first mount still needs a full page update
            self.page.update()

    def _sync_panels(self, width: int) -> None:
        favorites = tuple(self.settings.favorite_codes())
        self.calendar.window_width = width
        self.calendar.compact = self.settings.compact_fixtures
        self.calendar.favorite_codes = favorites
        self.calendar.favorite_team_ids = tuple(self.settings.favorite_team_ids())
        self.calendar.competitions = {item.code: item for item in self.competitions}
        self.leagues_panel.window_width = width

    def _render_panes(self, *, parts: str = "all") -> None:
        width = window_width(self.page)
        split = use_split(width)
        self._sync_panels(width)
        if self.booting:
            splash = splash_view(self._splash_message, fraction=self._splash_fraction)
            self._splash_control = splash
            self._pane.content = splash
            self._pane_kind = "splash"
            self._sync_nav_selection()
            self._paint(self._pane)
            start_spin(splash)
            return
        if self.section in ("settings", "match") or not split:
            self._pane.content = self._section_body(width, split=False)
            self._pane_kind = "single"
            self._sync_nav_selection()
            self._paint(self._pane)
            return
        left: ft.Control | None = None
        right: ft.Control | None = None
        if self.section == "leagues":
            self.calendar.embedded = True
            self.calendar.show_disclaimer = True
            self.calendar.collapsible = False
            if parts in {"all", "left"}:
                left = self.leagues_panel.control
            if parts in {"all", "right"}:
                right = self.calendar.control
            self._left_slot.expand = 3
            self._right_slot.expand = 2
        else:
            self.calendar.embedded = True
            self.calendar.show_disclaimer = False
            self.calendar.collapsible = True
            if parts in {"all", "left"}:
                left = self._collapsed_rail() if self.calendar_collapsed else self.calendar.control
            if parts in {"all", "right"}:
                right = self._forecast_pane(width, embedded=True)
            self._left_slot.expand = None if self.calendar_collapsed else 1
            self._right_slot.expand = 1
        if left is not None:
            self._left_slot.content = left
            self.calendar.refresh()
        if right is not None:
            self._right_slot.content = right
        switched = self._pane.content is not self._split_row
        if switched:
            self._pane.content = self._split_row
        self._pane_kind = "split"
        self._sync_nav_selection()
        if switched:
            self._paint(self._pane)
            return
        dirty = [
            slot
            for slot, block in ((self._left_slot, left), (self._right_slot, right))
            if block is not None
        ]
        self._paint(*dirty)

    def _collapsed_rail(self) -> ft.Control:
        return ft.Container(
            content=ft.Column(
                [
                    with_cursor(
                        ft.IconButton(
                            icon=ft.Icons.KEYBOARD_DOUBLE_ARROW_RIGHT,
                            tooltip="Показать список матчей",
                            on_click=lambda _e: self._toggle_calendar(),
                        ),
                        interactive=True,
                    ),
                    ft.Icon(ft.Icons.CALENDAR_MONTH, size=18),
                ],
                spacing=8,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            width=48,
        )

    def _toggle_calendar(self) -> None:
        self.calendar_collapsed = not self.calendar_collapsed
        self._render_panes()

    def _notify(self, message: str, *, kind: str = "info", alert: bool = False) -> None:
        notify_user(
            self.page,
            message,
            kind=kind,
            alert=alert,
            system=self.settings.system_notifications,
        )

    def _error_for(self, kind: str) -> str | None:
        if not self.error:
            return None
        if self.busy:
            return self.error if self.busy == kind else None
        section_kind = {
            "leagues": "leagues",
            "fixtures": "fixtures",
            "match": "forecast",
            "settings": "settings",
        }.get(self.section)
        return self.error if section_kind == kind else None

    def _forecast_pane(self, width: int, *, embedded: bool) -> ft.Control:
        if self.forecast is None and not (self.loading and self.busy == "forecast"):
            return ft.Container(
                content=info_banner(
                    "Выберите матч в календаре, чтобы увидеть прогноз.",
                    action_hint="Календарь слева" if embedded else "Откройте вкладку Календарь",
                ),
                alignment=ft.Alignment.TOP_CENTER,
                expand=True,
            )
        return match_detail_view(
            self.forecast,
            loading=self.loading and self.busy == "forecast",
            error=self._error_for("forecast"),
            on_back=lambda: self._goto("fixtures"),
            window_width=width,
            embedded=embedded,
            show_ai_block=self.settings.show_ai_block,
            ai_state=self.ai_state,
            ai_error=self.ai_error,
        )

    def _settings_pane(self, width: int) -> ft.Control:
        self._training_slot.content = self._training_block(width)
        gate_notice = self.gate.notice() if self.gate.locked else None
        return settings_view(
            SettingsForm.from_settings(
                self.settings,
                team_choices=self._team_choices(),
                status=self.status,
                error=self._error_for("settings"),
                saving=self.loading and self.busy == "settings",
                league_infos=self.league_infos,
                teams_by_league=self._teams_by_league,
                gate_notice=gate_notice,
                counting=self.counting,
            ),
            on_save=self._save_settings,
            on_test=self._test_connection,
            on_clear_cache=self._clear_cache,
            window_width=width,
            training=self._training_slot,
            on_refresh_counts=self._refresh_counts,
        )

    def _training_block(self, width: int) -> ft.Control:
        return training_panel(
            self.training,
            on_collect=self._start_training,
            on_cancel=self._cancel_training,
            on_export=self._export_history,
            window_width=width,
        )

    def _section_body(self, width: int, split: bool) -> ft.Control:
        if self.section == "leagues":
            return self.leagues_panel.control
        if self.section == "fixtures":
            self.calendar.embedded = False
            self.calendar.show_disclaimer = True
            self.calendar.collapsible = False
            self.calendar.refresh()
            return self.calendar.control
        if self.section == "match":
            return self._forecast_pane(width, embedded=False)
        return self._settings_pane(width)

    def _render(self) -> None:
        width = window_width(self.page)
        rail = use_rail(width)
        split = use_split(width)
        if rail != self._rail_mode or split != self._split_mode:
            self._rebuild_chrome()
        self._render_panes()

    def _goto(self, section: str) -> None:
        self.error = None
        self._set_section(section)
        self._render_panes()

    def _after(self, delay_s: float, callback: Callable[[], None]) -> None:
        runner = getattr(self.page, "run_task", None)
        if callable(runner):

            async def later() -> None:
                await asyncio.sleep(delay_s)
                callback()
                self.page.update()

            runner(later)
            return
        timer = threading.Timer(delay_s, callback)
        timer.daemon = True
        timer.start()

    # --- boot: splash (>= 3 s and until loading ends) -> key gate ------------------------

    def _set_splash(self, message: str, fraction: float | None = None) -> None:
        self._splash_message = message
        self._splash_fraction = fraction
        if self.booting:
            self._render_panes()

    def _post_splash(self, message: str, fraction: float | None = None) -> None:
        post_to_ui(self.page, lambda: self._set_splash(message, fraction))

    def _start_boot(self) -> None:
        self.booting = True
        self.splash = SplashTimer(self._splash_min, self._clock)
        self._set_splash("Загружаем данные…")
        service = self.service
        has_key = not self.gate.missing
        prefetch = self.settings.prefetch_wait_on_start

        def work() -> BootResult:
            # Everything here is I/O (SQLite, HTTP, asset manifest): never on the UI loop.
            load_crest_manifest()
            items = service.cached_competitions()
            if not has_key:
                # No network without the required key: cached data only.
                return self._boot_result_for(service, items)
            try:
                items = service.bootstrap()
            except Exception as exc:  # noqa: BLE001 — start with the cache, show the error
                return self._boot_result_for(service, items, error=str(exc))
            if prefetch and items:
                total = len(items)
                for index, competition in enumerate(items, start=1):
                    self._post_splash(
                        f"Лига {index}/{total}: {competition.code}", (index - 1) / total
                    )
                    service.prefetch_competition(competition.code)
            return self._boot_result_for(
                service, items, rejected=bool(getattr(service, "key_rejected", False))
            )

        run_background(
            self.page,
            work,
            self._on_bootstrap,
            self._on_boot_fail,
            message=None,
            cancel_previous=False,
            key="boot",
        )

    def _boot_result_for(
        self,
        service: MatchService,
        items: list[Competition],
        *,
        rejected: bool = False,
        error: str | None = None,
    ) -> BootResult:
        return BootResult(
            list(items),
            self._infos_for(service, items),
            rejected=rejected,
            error=error,
            choices=self._read_choices(service, items),
        )

    @staticmethod
    def _infos_for(service: MatchService, items: list[Competition]) -> list[LeagueInfo]:
        getter = getattr(service, "league_infos", None)
        if callable(getter):
            try:
                return list(getter())
            except Exception:  # noqa: BLE001 — availability notes are optional
                pass
        return league_infos(items, {}, (), today=date.today())

    def _on_bootstrap(self, result: BootResult) -> None:
        self._boot_result = result
        if result.competitions or not self.competitions:
            self.competitions = list(result.competitions)
        if result.infos or not self.league_infos:
            self.league_infos = list(result.infos)
        if result.choices is not None:
            self._apply_choices(result.choices)
        self.splash.mark_loaded()
        remaining = self.splash.remaining()
        if remaining > 0:
            self._after(remaining, self._finish_boot)
            return
        self._finish_boot()

    def _on_boot_fail(self, message: str) -> None:
        self._on_bootstrap(BootResult(list(self.competitions), self.league_infos, error=message))

    def _finish_boot(self) -> None:
        if not self.booting:
            return
        self.booting = False
        self.loading = False
        self.busy = None
        result = self._boot_result
        rejected = bool(result and result.rejected)
        self.gate.evaluate(self.settings, key_rejected=rejected)
        self._refresh_leagues_panel()
        if self.gate.locked:
            self.section = "settings"
            self.status = None  # the lock banner on top of Settings explains it
            self._load_settings_choices()
            self._render_panes()
            self._notify(self.gate.notice(), kind="info")
            return
        if result and result.error:
            self.error = result.error
        self._render_panes()
        self._notify("Приложение готово.", kind="success")
        self._load_day()

    # --- leagues -------------------------------------------------------------------------

    def _refresh_leagues_panel(self) -> None:
        self.leagues_panel.set_data(
            self.league_infos,
            favorite_codes=self.settings.favorite_codes(),
            selected_code=self.league.code if self.league else None,
            loading=self.loading and self.busy == "leagues",
            error=self._error_for("leagues"),
        )

    def _load_leagues(self, force: bool = False) -> None:
        self.loading = True
        self.busy = "leagues"
        self.error = None
        self._set_section("leagues")
        self._refresh_leagues_panel()
        self._render_panes()
        service = self.service

        def work() -> tuple[list[Competition], list[LeagueInfo]]:
            items = service.list_competitions(force=force)
            return items, self._infos_for(service, items)

        run_background(
            self.page, work, self._on_leagues, self._on_fail, cancel_previous=True, key="leagues"
        )

    def _on_leagues(self, outcome: tuple[list[Competition], list[LeagueInfo]]) -> None:
        items, infos = outcome
        self.competitions = list(items)
        self.league_infos = list(infos)
        self.loading = False
        self.busy = None
        self._refresh_leagues_panel()
        self._render_panes()

    def _select_league(self, competition: Competition) -> None:
        self.league = competition
        self.forecast = None
        self.selected_match_id = None
        split = use_split(window_width(self.page))
        if not (split and self.section == "leagues"):
            self._set_section("fixtures")
        self.leagues_panel.selected_code = competition.code
        self.leagues_panel.repaint()
        # Days of the league come from SQLite in the background (then the season fetch).
        self._apply_league_days(competition, [], jump=False)
        self._render_panes()
        self._load_day()
        self._refresh_league_calendar(competition)

    @staticmethod
    def _league_days(service: MatchService, code: str) -> list[date]:
        """Worker thread only (SQLite read)."""
        getter = getattr(service, "cached_league_matches", None)
        if not callable(getter):
            return []
        try:
            return match_days(getter(code), local_tz())
        except Exception:  # noqa: BLE001 — jumps are a convenience
            return []

    def _apply_league_days(self, competition: Competition, days: list[date], *, jump: bool) -> None:
        self.calendar.set_league(competition, days)
        if not jump or not days:
            return
        today = self._today()
        target = today if today in days else nearest_day(days, today, 1)
        if target is None:
            target = nearest_day(days, today, -1)
        if target is not None:
            self.calendar.day = target

    def _refresh_league_calendar(self, competition: Competition) -> None:
        """Season calendar of the league in the background, for the match-day jumps."""
        generation, _cancel = self._league_job.start()
        service = self.service
        code = competition.code

        competitions = list(self.competitions)

        def cached_ready(days: list[date]) -> None:
            if not self._league_job.is_current(generation) or self.league is None:
                return
            if self.league.code != code or not days:
                return
            before = self.calendar.day
            self._apply_league_days(competition, days, jump=True)
            if self.calendar.day != before:
                self.calendar.refresh()
                self._load_day()

        def work() -> tuple[list[date], list[LeagueInfo]]:
            cached = self._league_days(service, code)
            if cached:
                post_to_ui(self.page, lambda: cached_ready(cached))
            service.competition_matches(code)
            return self._league_days(service, code), self._infos_for(service, competitions)

        def ok(outcome: tuple[list[date], list[LeagueInfo]]) -> None:
            days, infos = outcome
            if not self._league_job.is_current(generation) or self.league is None:
                return
            self._league_job.finish(generation)
            if self.league.code != code:
                return
            before = self.calendar.day
            self._apply_league_days(competition, days, jump=not self.calendar.league_days)
            self.league_infos = infos
            self._refresh_leagues_panel()
            if self.calendar.day != before:
                self.calendar.refresh()
                self._load_day()

        def fail(_message: str) -> None:
            self._league_job.finish(generation)

        run_background(self.page, work, ok, fail, cancel_previous=True, key="league")

    def _clear_league(self) -> None:
        self.league = None
        self._league_job.stop()
        self.leagues_panel.selected_code = None
        self.leagues_panel.repaint()
        self.calendar.set_league(None)
        self._load_day()

    def _jump_league_day(self, step: int) -> None:
        target = nearest_day(self.calendar.league_days, self.calendar.day, step)
        if target is not None:
            self.calendar.go_to(target)

    # --- calendar day ----------------------------------------------------------------------

    def _load_day(self, force: bool = False) -> None:
        """Paint the day from SQLite now, refresh it from the API in the background."""
        if self.gate.locked:
            return
        generation, cancel = self._day_job.start()
        day = self.calendar.day
        codes = [self.league.code] if self.league is not None else None
        tz = local_tz()
        service = self.service
        cached: list[Match] = []
        key = (day, tuple(codes or ()))
        self.calendar.set_data(self._keep_same_day(key), loading=True)

        def paint_cached(rows: list[Match]) -> None:
            if self._day_job.is_current(generation) and self.calendar.loading:
                self._calendar_key = key
                self.calendar.set_data(rows, loading=True)

        def work() -> list[Match] | None:
            if cancel.is_set():
                return None
            getter = getattr(service, "cached_day_matches", None)
            if callable(getter):
                try:
                    cached[:] = list(getter(day, codes=codes, tz=tz))
                except Exception:  # noqa: BLE001 — the network refresh follows anyway
                    cached.clear()
                rows = list(cached)
                post_to_ui(self.page, lambda: paint_cached(rows))
            if cancel.is_set():
                return None
            return service.day_matches(day, codes=codes, tz=tz, force=force)

        def ok(matches: list[Match] | None) -> None:
            if matches is None or not self._day_job.is_current(generation):
                return
            self._day_job.finish(generation)
            self._calendar_key = key
            self.calendar.set_data(matches, loading=False)

        def fail(message: str) -> None:
            if not self._day_job.is_current(generation):
                return
            self._day_job.finish(generation)
            self.calendar.set_data(cached, loading=False, error=message)

        run_background(self.page, work, ok, fail, cancel_previous=True, key="calendar")

    def _keep_same_day(self, key: tuple[date, tuple[str, ...]]) -> list[Match]:
        """While the day reloads, keep its rows on screen (refresh), else start empty."""
        return list(self.calendar.matches) if key == self._calendar_key else []

    # --- forecast + background enrichment ----------------------------------------------

    def _open_match(self, match: Match) -> None:
        self._ai_job.stop()
        self._ai_interrupted = False
        self.loading = True
        self.busy = "forecast"
        self.error = None
        self.forecast = None
        self.ai_state = None
        self.ai_error = None
        self.selected_match_id = match.id
        self.calendar.select_match(match.id)
        self._set_section("fixtures" if use_split(window_width(self.page)) else "match")
        service = self.service

        def work() -> MatchForecast:
            # No HTTP here: numbers from local data, details come in the enrichment.
            return service.forecast(match, explain=False, details=False)

        def fail(message: str) -> None:
            if self.selected_match_id != match.id:
                return
            self._on_fail(message)

        run_background(
            self.page, work, self._on_forecast, fail, cancel_previous=True, key="forecast"
        )
        self._render_panes(parts="right" if self._pane_kind == "split" else "all")

    def _on_forecast(self, forecast: MatchForecast) -> None:
        if not self._is_current(forecast):
            return
        self.forecast = forecast
        self.loading = False
        self.busy = None
        match = forecast.match
        self._notify(f"Прогноз готов: {match.home_name} — {match.away_name}", kind="success")
        self._start_enrichment(forecast)

    def _repaint_forecast(self) -> None:
        if self.section not in FORECAST_SECTIONS:
            return
        self._render_panes(parts="right" if self._pane_kind == "split" else "all")

    def _start_enrichment(self, forecast: MatchForecast, *, repaint: bool = True) -> None:
        """Background: club cards/lineup, player status, news, then the LLM analysis.

        One job at a time: opening another match or leaving the forecast screens sets the
        cancel Event; results of an old generation are dropped.
        """
        wants_llm = self.settings.show_ai_block and bool(
            getattr(self.service, "llm_enabled", False)
        )
        self.ai_error = None
        self.ai_state = AI_LOADING if wants_llm else AI_NOT_CONFIGURED
        if repaint:
            self._repaint_forecast()
        generation, cancel = self._ai_job.start()
        service = self.service

        def on_step(partial: MatchForecast) -> None:
            post_to_ui(self.page, lambda: self._on_enrich_step(generation, partial))

        def work() -> MatchForecast | None:
            try:
                return service.enrich(forecast, explain=wants_llm, cancel=cancel, on_step=on_step)
            except Cancelled:
                return None

        run_background(
            self.page,
            work,
            lambda result: self._on_explain(generation, result),
            lambda message: self._on_explain_fail(generation, message),
            cancel_previous=True,
            key="enrich",
        )

    def _is_current(self, forecast: MatchForecast) -> bool:
        return self.selected_match_id is None or forecast.match.id == self.selected_match_id

    def _on_enrich_step(self, generation: int, forecast: MatchForecast) -> None:
        if not self._ai_job.is_current(generation) or not self._is_current(forecast):
            return
        self.forecast = forecast
        self._repaint_forecast()

    def _on_explain(self, generation: int, forecast: MatchForecast | None) -> None:
        if forecast is None or not self._ai_job.is_current(generation):
            return  # cancelled or superseded by another match
        if not self._is_current(forecast):
            return
        self._ai_job.finish(generation)
        self.forecast = forecast
        if forecast.explanation is not None:
            self.ai_state = AI_READY
        elif forecast.explanation_error:
            self.ai_state = AI_ERROR
            self.ai_error = forecast.explanation_error
            self._notify(f"AI-разбор не получен: {forecast.explanation_error}", kind="error")
        elif self.ai_state == AI_LOADING:
            self.ai_state = AI_NOT_CONFIGURED
        self._repaint_forecast()

    def _on_explain_fail(self, generation: int, message: str) -> None:
        if not self._ai_job.is_current(generation):
            return
        self._ai_job.finish(generation)
        self.ai_state = AI_ERROR
        self.ai_error = message or "неизвестная ошибка"
        self._repaint_forecast()
        self._notify(f"AI-разбор не получен: {self.ai_error}", kind="error")

    def _on_fail(self, message: str) -> None:
        self.loading = False
        self.busy = None
        self.error = message
        self._render_panes()
        self._notify(message, kind="error", alert=True)

    # --- settings + key gate ---------------------------------------------------------------

    def _team_choices(self) -> tuple[Team, ...]:
        return self._teams

    @staticmethod
    def _read_choices(service: MatchService, competitions: list[Competition]) -> SettingsChoices:
        """Worker thread only: favourite-team choices from SQLite."""
        teams: tuple[Team, ...] = ()
        getter = getattr(service, "cached_teams", None)
        if callable(getter):
            try:
                teams = tuple(getter())
            except Exception:  # noqa: BLE001 — settings must open even if cache is empty
                teams = ()
        grouped: dict[str, list[Team]] = {}
        by_league = getattr(service, "teams_by_league", None)
        if callable(by_league):
            try:
                grouped = dict(by_league())
            except Exception:  # noqa: BLE001
                grouped = {}
        known = {item.code: item for item in competitions}
        pairs = tuple(
            (known.get(code, Competition(0, code, code)), tuple(members))
            for code, members in grouped.items()
        )
        return SettingsChoices(teams=teams, by_league=pairs)

    def _apply_choices(self, choices: SettingsChoices) -> bool:
        changed = choices != self._choices
        self._choices = choices
        self._teams = choices.teams
        self._teams_by_league = [(comp, list(members)) for comp, members in choices.by_league]
        return changed

    def _load_settings_choices(self) -> None:
        """Refresh favourite-team choices in the background; repaint only if they changed."""
        service = self.service
        competitions = list(self.competitions)

        def work() -> SettingsChoices:
            return self._read_choices(service, competitions)

        def ok(choices: SettingsChoices) -> None:
            if self._apply_choices(choices) and self.section == "settings":
                self._render_panes()

        run_background(self.page, work, ok, lambda _m: None, key="choices")

    def _save_settings(self, payload: dict[str, str | bool]) -> None:
        self.loading = True
        self.busy = "settings"
        self.error = None
        self.status = None
        self._render_panes()

        def work() -> Settings:
            text_values = (
                ("FOOTBALL_DATA_API_KEY", "football_data_api_key", ""),
                ("OLLAMA_API_KEY", "ollama_api_key", ""),
                ("OLLAMA_HOST", "ollama_host", OLLAMA_CLOUD_HOST),
                ("OLLAMA_MODEL", "ollama_model", DEFAULT_OLLAMA_MODEL),
                ("OLLAMA_FALLBACK_MODEL", "ollama_fallback_model", DEFAULT_OLLAMA_FALLBACK_MODEL),
                ("API_FOOTBALL_KEY", "api_football_key", ""),
                ("GNEWS_API_KEY", "gnews_api_key", ""),
                ("FAVORITE_LEAGUES", "favorite_leagues", ""),
                ("FAVORITE_TEAMS", "favorite_teams", ""),
            )
            for env_key, name, default in text_values:
                write_env_value(env_key, _env_text(payload.get(name), default))
            flags = (
                ("PREFETCH_WAIT_ON_START", "prefetch_wait_on_start", False),
                ("SHOW_AI_BLOCK", "show_ai_block", True),
                ("COMPACT_FIXTURES", "compact_fixtures", False),
                ("SYSTEM_NOTIFICATIONS", "system_notifications", False),
                ("NEWS_RSS_ENABLED", "news_rss_enabled", True),
            )
            for env_key, name, default in flags:
                write_env_value(env_key, _env_flag(payload.get(name, default)))
            settings = load_settings()
            # Rate limiters are process-wide (services.factory), so the rebuild keeps
            # the football-data.org 10 req/min window. Building opens SQLite: worker only.
            return settings, build_service(settings)

        def ok(outcome: tuple[Settings, MatchService]) -> None:
            settings, service = outcome
            old_key = self.settings.football_data_api_key.strip()
            was_locked = self.gate.locked
            old_service = self.service
            self.settings = settings
            self.service = service
            if old_service is not self.service:
                closer = getattr(old_service, "close", None)
                if callable(closer):
                    # Closing HTTP clients may wait for sockets: off the UI loop too.
                    threading.Thread(target=closer, daemon=True).start()
            self.loading = False
            self.busy = None
            self.status = "Настройки сохранены и применены."
            key_changed = settings.football_data_api_key.strip() != old_key
            self.gate.evaluate(settings)
            if self.gate.state is GateState.MISSING:
                self.status = None
                self._render_panes()
                self._notify(self.gate.notice(), kind="info")
                return
            self._refresh_leagues_panel()
            self._notify("Настройки сохранены и применены.", kind="success")
            if key_changed or was_locked:
                self._check_key()
                return
            self._render_panes()
            if self.forecast is not None and self.forecast.explanation is None:
                self._start_enrichment(self.forecast)

        run_background(self.page, work, ok, self._on_fail, cancel_previous=True, key="settings")

    def _check_key(self) -> None:
        """Validate the football-data.org key with one request; unlock on success."""
        self.gate.start_check()
        self.status = None
        self._render_panes()
        service = self.service

        def work():
            return service.check_key()

        run_background(self.page, work, self._on_key_checked, self._on_key_check_error, key="gate")

    def _on_key_checked(self, result) -> None:
        was_locked = True
        if result.ok:
            self.gate.check_passed()
            self.status = f"Ключ принят. Доступно лиг: {result.leagues}."
            self._notify(self.status, kind="success")
        else:
            self.gate.check_failed(result.message, rejected=result.rejected)
            if self.gate.locked:
                self.status = None
                self._notify(self.gate.notice(), kind="error")
            else:
                self.status = f"Ключ сохранён, но проверить его сейчас нельзя: {result.message}"
                self._notify(self.status, kind="info")
        self._render_panes()
        if was_locked and not self.gate.locked:
            self._after_unlock()

    def _on_key_check_error(self, message: str) -> None:
        self.gate.check_failed(message, rejected=False)
        self.status = f"Ключ сохранён, но проверить его сейчас нельзя: {message}"
        self._render_panes()
        self._after_unlock()

    def _after_unlock(self) -> None:
        """Load what the locked app skipped, without a restart."""
        service = self.service

        def work() -> tuple[list[Competition], list[LeagueInfo]]:
            items = service.bootstrap()
            return items, self._infos_for(service, items)

        def ok(outcome: tuple[list[Competition], list[LeagueInfo]]) -> None:
            items, infos = outcome
            self.competitions = list(items)
            self.league_infos = list(infos)
            self._refresh_leagues_panel()
            self._load_settings_choices()
            if self.section == "settings":
                self._render_panes()
            self._load_day()

        run_background(self.page, work, ok, lambda _m: self._load_day(), key="leagues")

    def _test_connection(self) -> None:
        self._check_key()

    def _refresh_counts(self) -> None:
        """Load season calendars of every league to count upcoming matches (detached)."""
        if self.counting:
            return
        codes = [item.code for item in self.competitions]
        if not codes:
            return
        self.counting = "Считаем матчи лиг…"
        self._render_panes()
        service = self.service

        def work() -> list[LeagueInfo]:
            return list(service.refresh_league_counts(codes))

        def ok(infos: list[LeagueInfo]) -> None:
            self.counting = None
            self.league_infos = infos
            self._refresh_leagues_panel()
            self._load_settings_choices()
            if self.section == "settings":
                self._render_panes()
            self._notify("Счётчики матчей обновлены.", kind="success")

        def fail(message: str) -> None:
            self.counting = None
            if self.section == "settings":
                self._render_panes()
            self._notify(f"Не удалось обновить счётчики: {message}", kind="error")

        run_detached(self.page, work, ok, fail)

    # --- training data collection (background, cancellable) -----------------------------

    def _training_codes(self) -> list[str]:
        codes = self.settings.favorite_codes()
        if not codes and self.league is not None:
            codes = [self.league.code]
        return codes

    def _repaint_training(self, *, force: bool = False) -> None:
        """Repaint only the training card: unsaved Settings fields keep their text."""
        if self.section != "settings":
            return
        now = time.monotonic()
        if not force and now - self._training_painted_at < 0.25:
            return
        self._training_painted_at = now
        self._training_slot.content = self._training_block(window_width(self.page))
        if not safe_update(self._training_slot):
            self.page.update()

    def _start_training(self) -> None:
        if self.training.running:
            return
        codes = self._training_codes()
        if not codes:
            self.training = replace(
                self.training,
                error="Выберите лигу или задайте любимые лиги в Настройках.",
                result=None,
            )
            self._repaint_training(force=True)
            return
        cancel = threading.Event()
        self._training_cancel = cancel
        self.training = TrainingState(
            running=True, codes=tuple(codes), message="Подготовка…", stats=self.training.stats
        )
        self._repaint_training(force=True)
        service = self.service

        def progress(done: int, total: int, message: str) -> None:
            def apply() -> None:
                if not self.training.running:
                    return
                self.training = replace(self.training, done=done, total=total, message=message)
                self._repaint_training(force=done == total)

            post_to_ui(self.page, apply)

        def work():
            result = service.collect_training_data(codes, progress=progress, cancel=cancel)
            return result, service.calibration_report()

        run_detached(self.page, work, self._on_training_done, self._on_training_fail)

    def _cancel_training(self) -> None:
        if self._training_cancel is not None and self.training.running:
            self._training_cancel.set()
            self.training = replace(self.training, cancelling=True)
            self._repaint_training(force=True)

    def _on_training_done(self, outcome) -> None:
        result, report = outcome
        self._training_cancel = None
        self.training = replace(
            self.training,
            running=False,
            cancelling=False,
            result=result.summary,
            error=None,
            errors=tuple(result.errors),
            stats=calibration_lines(report),
        )
        self._repaint_training(force=True)
        self._notify(result.summary, kind="info" if result.cancelled else "success")

    def _on_training_fail(self, message: str) -> None:
        self._training_cancel = None
        self.training = replace(
            self.training,
            running=False,
            cancelling=False,
            error=f"Сбор данных не удался: {message}",
        )
        self._repaint_training(force=True)
        self._notify(f"Сбор данных не удался: {message}", kind="error")

    # --- CSV export: save dialog, data/exports as the fallback ---------------------------
    #
    # The click handler only flips the button to "busy" and returns. The dialog and
    # the CSV write happen off the UI event loop (see ui/save_dialog.py for why the
    # macOS dialog is an osascript process and not the Flet FilePicker).

    def _dialog_kind(self) -> str:
        page = self.page
        return dialog_kind(
            web=bool(getattr(page, "web", False)),
            real_page=isinstance(page, ft.Page),
        )

    def _file_picker(self) -> ft.FilePicker | None:
        """Flet FilePicker service (Windows/Linux desktop); None when unavailable."""
        if self._picker is None:
            try:
                picker = ft.FilePicker()  # a Service: registers itself on the page
                if not is_mounted(picker):
                    self.page._services.register_service(picker)  # noqa: SLF001
                self._picker = picker
            except Exception:  # noqa: BLE001 — fall back to data/exports
                return None
        return self._picker

    def _set_exporting(self, label: str | None) -> None:
        self.training = replace(self.training, exporting=label)
        self._repaint_training(force=True)

    def _export_history(self) -> None:
        if self.training.running or self.training.exporting:
            return  # one dialog / export at a time; repeated clicks are ignored
        self.training = replace(self.training, error=None, result=None)
        stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        file_name = f"forecast_history_{stamp}.csv"
        kind = self._dialog_kind()
        if kind == "macos":
            self._set_exporting("Выберите файл…")
            chooser = self._mac_chooser

            def pick() -> Path | None:
                EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
                return chooser(EXPORT_DIALOG_TITLE, EXPORTS_DIR, file_name)

            self._run_export(None, choose=pick)
            return
        picker = self._file_picker() if kind == "flet" else None
        runner = getattr(self.page, "run_task", None)
        if picker is None or not callable(runner):
            self._set_exporting("Сохраняем CSV…")
            self._run_export(None)
            return
        self._set_exporting("Выберите файл…")

        async def ask() -> None:
            try:
                await asyncio.to_thread(EXPORTS_DIR.mkdir, parents=True, exist_ok=True)
                chosen = await asyncio.wait_for(
                    picker.save_file(
                        dialog_title=EXPORT_DIALOG_TITLE,
                        file_name=file_name,
                        initial_directory=str(EXPORTS_DIR),
                        file_type=ft.FilePickerFileType.CUSTOM,
                        allowed_extensions=["csv"],
                    ),
                    timeout=DIALOG_TIMEOUT_S,
                )
            except Exception as exc:  # noqa: BLE001 — no dialog: save to data/exports
                self._set_exporting("Сохраняем CSV…")
                self._run_export(None, note=f"Окно выбора недоступно ({exc or 'таймаут'}).")
                return
            if not chosen:
                self._export_cancelled()
                return
            self._set_exporting("Сохраняем CSV…")
            self._run_export(Path(chosen))

        runner(ask)

    def _export_cancelled(self) -> None:
        self.training = replace(
            self.training, exporting=None, error=None, result="Экспорт отменён."
        )
        self._repaint_training(force=True)

    def _run_export(
        self,
        target: Path | None,
        *,
        note: str | None = None,
        choose: Callable[[], Path | None] | None = None,
    ) -> None:
        service = self.service
        cancelled = object()

        def work():
            path, prefix = target, note
            if choose is not None:
                try:
                    path = choose()
                except SaveDialogUnavailable as exc:
                    path, prefix = None, f"Окно выбора недоступно ({exc})."
                else:
                    if path is None:
                        return cancelled
                post_to_ui(self.page, lambda: self._set_exporting("Сохраняем CSV…"))
            if path is None:
                records_path, summary_path, rows = service.export_history(EXPORTS_DIR)
            else:
                records_path, summary_path, rows = service.export_history(records_path=path)
            return records_path, summary_path, rows, service.calibration_report(), prefix

        def ok(outcome) -> None:
            if outcome is cancelled:
                self._export_cancelled()
                return
            records_path, summary_path, rows, report, prefix = outcome
            lead = f"{prefix} " if prefix else ""
            self.training = replace(
                self.training,
                exporting=None,
                export_path=f"{lead}{records_path} ({rows} строк); сводка: {summary_path}",
                stats=calibration_lines(report),
                error=None,
            )
            self._repaint_training(force=True)
            self._notify(f"История прогнозов выгружена: {rows} строк.", kind="success")

        def fail(message: str) -> None:
            self.training = replace(
                self.training, exporting=None, error=f"Экспорт не удался: {message}"
            )
            self._repaint_training(force=True)

        run_detached(self.page, work, ok, fail)

    # --- cache -----------------------------------------------------------------------------

    def _clear_cache(self) -> None:
        self.loading = True
        self.busy = "settings"
        self.error = None
        self.status = None
        self._render_panes()
        service = self.service

        def work() -> list[Competition]:
            service.clear_cache()
            return service.cached_competitions()

        def ok(items: list[Competition]) -> None:
            self.competitions = items
            self.league_infos = self._infos_for(service, items)
            self.calendar.set_data([])
            self.forecast = None
            self.selected_match_id = None
            self.loading = False
            self.busy = None
            self.status = "Кэш очищен."
            self._refresh_leagues_panel()
            self._render_panes()
            self._notify("Кэш очищен.", kind="info")

        run_background(
            self.page,
            work,
            ok,
            self._on_fail,
            message="Очищаем кэш…",
            cancel_previous=True,
            key="settings",
        )


def _clear_page(page: ft.Page) -> None:
    cleaner = getattr(page, "clean", None)
    if callable(cleaner):
        cleaner()
        return
    controls = getattr(page, "controls", None)
    if isinstance(controls, list):
        controls.clear()


def start_ui(
    page: ft.Page,
    service: MatchService | None = None,
    settings: Settings | None = None,
) -> FootballApp | None:
    """Show the splash at once; read .env and open SQLite in the background.

    Flet runs a synchronous `main(page)` on its event loop, so building the service
    here (settings file, SQLite schema, HTTP clients) would keep the window blank.
    Returns the app when `service` and `settings` are given (tests, screenshot
    scripts); otherwise the app is created when the background build finishes.
    """
    configure_window(page)
    page.title = "Football Prognoz"
    _clear_page(page)
    first = splash_view("Запуск приложения…")
    page.add(first)
    updater = getattr(page, "update", None)
    if callable(updater):
        updater()
    start_spin(first)
    if service is not None and settings is not None:
        _clear_page(page)
        return FootballApp(page, service, settings)

    def work() -> tuple[Settings, MatchService]:
        ready = settings or load_settings()
        return ready, service or build_service(ready)

    def ok(outcome: tuple[Settings, MatchService]) -> None:
        ready, built = outcome
        _clear_page(page)
        FootballApp(page, built, ready)

    def fail(message: str) -> None:
        _clear_page(page)
        page.add(
            ft.Container(
                content=info_banner(f"Не удалось запустить приложение: {message}"),
                padding=24,
            )
        )

    run_background(page, work, ok, fail, cancel_previous=False, key="startup")
    return None
