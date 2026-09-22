from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import flet as ft

from football_prognoz.ai.explainer import Explainer, OpenAICompatClient
from football_prognoz.config import Settings, load_settings, write_env_value
from football_prognoz.data.football_data_org import FootballDataOrgClient
from football_prognoz.data.store import SQLiteStore
from football_prognoz.domain.match import Match
from football_prognoz.domain.prediction import MatchForecast
from football_prognoz.domain.team import Competition, Team
from football_prognoz.models.predictor import Predictor
from football_prognoz.services.features import FeatureService
from football_prognoz.services.filters import (
    FixtureQuery,
    MatchStatusFilter,
    apply_fixture_query,
    filter_competitions,
)
from football_prognoz.services.matches import MatchService
from football_prognoz.ui.components.settings_panel import SettingsForm
from football_prognoz.ui.components.splash import splash_view
from football_prognoz.ui.motion import PAGE_CURSOR, with_cursor
from football_prognoz.ui.notify import notify_user
from football_prognoz.ui.runtime import debounce, info_banner, run_background
from football_prognoz.ui.theme import (
    BG,
    BODY_PADDING,
    configure_window,
    use_rail,
    use_split,
    window_width,
)
from football_prognoz.ui.views.fixtures import fixtures_view
from football_prognoz.ui.views.leagues import leagues_view
from football_prognoz.ui.views.match_detail import match_detail_view
from football_prognoz.ui.views.settings import settings_view

SECTIONS = ("leagues", "fixtures", "match", "settings")
NAV_INDEX = {name: index for index, name in enumerate(SECTIONS)}

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


def build_service(settings: Settings) -> MatchService:
    store = SQLiteStore(settings.db_path)
    client = FootballDataOrgClient(settings.football_data_api_key)
    llm = None
    if settings.has_openai_key:
        llm = OpenAICompatClient(
            settings.openai_api_key,
            settings.openai_model,
            settings.openai_base_url,
        )
    return MatchService(
        client=client,
        store=store,
        features=FeatureService(store),
        predictor=Predictor(),
        explainer=Explainer(llm, settings.openai_model),
    )


class FootballApp:
    def __init__(self, page: ft.Page, service: MatchService, settings: Settings) -> None:
        self.page = page
        self.service = service
        self.settings = settings
        self.section = "leagues"
        self.competitions: list[Competition] = []
        self.matches: list[Match] = []
        self.forecast: MatchForecast | None = None
        self.league: Competition | None = None
        self.selected_match_id: int | None = None
        self.loading = False
        self.busy: str | None = None
        self.error: str | None = None
        self.status: str | None = None
        self.booting = False
        self.league_query = ""
        self.favorites_only = False
        self.fixture_query = FixtureQuery()
        self._splash_message = "Загружаем данные…"
        self._splash_fraction: float | None = None
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
        if not settings.has_football_key:
            self.section = "settings"
            self.status = "Введите ключ football-data.org, чтобы загрузить лиги."
            self._render_panes()
            return
        self._start_boot()

    @property
    def team_query(self) -> str:
        return self.fixture_query.team_query

    @team_query.setter
    def team_query(self, value: str) -> None:
        self.fixture_query = replace(self.fixture_query, team_query=value, page=0)

    @property
    def upcoming_only(self) -> bool:
        return self.fixture_query.status is MatchStatusFilter.UPCOMING

    @upcoming_only.setter
    def upcoming_only(self, value: bool) -> None:
        status = MatchStatusFilter.UPCOMING if value else MatchStatusFilter.ALL
        self.fixture_query = replace(self.fixture_query, status=status, page=0)

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
        index = self._nav_index()
        if self._rail is not None:
            self._rail.selected_index = index
        if self._nav_bar is not None:
            self._nav_bar.selected_index = index

    def _on_nav(self, event: ft.ControlEvent) -> None:
        index = self._nav_event_index(event)
        self.section = SECTIONS[index] if 0 <= index < len(SECTIONS) else "leagues"
        self.error = None
        if self.section == "leagues" and not self.competitions and not self.booting:
            self._load_leagues()
            return
        self._render_panes()

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

    def _set_nav(self, section: str) -> None:
        self.section = section

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

    def _split(self, master: ft.Control, detail: ft.Control, *, master_flex: int = 3) -> ft.Control:
        self._left_slot.expand = master_flex
        self._right_slot.expand = 2
        self._left_slot.content = master
        self._right_slot.content = detail
        return self._split_row

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

    def _render_panes(self, *, parts: str = "all") -> None:
        width = window_width(self.page)
        split = use_split(width)
        if self.booting and self.section != "settings":
            splash = splash_view(
                self._splash_message,
                fraction=self._splash_fraction,
            )
            self._pane.content = splash
            self._pane_kind = "splash"
            self._sync_nav_selection()
            self._paint(self._pane)
            return
        if self.section == "settings" or self.section == "match" or not split:
            self._pane.content = self._section_body(width, split=False)
            self._pane_kind = "single"
            self._sync_nav_selection()
            self._paint(self._pane)
            return
        left: ft.Control | None = None
        right: ft.Control | None = None
        if self.section == "leagues":
            if parts in {"all", "left"}:
                left = self._leagues_pane(width)
            if parts in {"all", "right"}:
                right = self._fixtures_pane(
                    width,
                    embedded=True,
                    compact_grid=False,
                    show_disclaimer=True,
                )
            self._left_slot.expand = 3
        else:
            if parts in {"all", "left"}:
                left = self._fixtures_pane(
                    width,
                    embedded=True,
                    compact_grid=True,
                    show_disclaimer=False,
                )
            if parts in {"all", "right"}:
                right = self._forecast_pane(width, embedded=True)
            self._left_slot.expand = 2
        self._right_slot.expand = 2
        if left is not None:
            self._left_slot.content = left
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

    def _team_choices(self) -> tuple[Team, ...]:
        getter = getattr(self.service, "cached_teams", None)
        if not callable(getter):
            return ()
        try:
            return tuple(getter())
        except Exception:  # noqa: BLE001 — settings must open even if cache is empty
            return ()

    def _notify(
        self,
        message: str,
        *,
        kind: str = "info",
        alert: bool = False,
    ) -> None:
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

    def _filtered_competitions(self) -> list[Competition]:
        items = filter_competitions(self.competitions, self.league_query)
        favorites = {code.upper() for code in self.settings.favorite_codes()}
        if self.favorites_only:
            items = [item for item in items if item.code.upper() in favorites]
        items.sort(key=lambda item: 0 if item.code.upper() in favorites else 1)
        return items

    def _fixture_page(self):
        return apply_fixture_query(
            self.matches,
            self.fixture_query,
            now=datetime.now(UTC),
        )

    def _filtered_matches(self) -> list[Match]:
        return list(self._fixture_page().items)

    def _on_league_query(self, query: str) -> None:
        self.league_query = query
        debounce(self.page, "league_query", 0.2, self._render_panes)

    def _on_favorites_only(self, value: bool) -> None:
        self.favorites_only = value
        self._render_panes()

    def _on_fixture_query(self, query: FixtureQuery) -> None:
        self.fixture_query = query
        if self._pane_kind == "split" and self.section == "leagues":
            debounce(self.page, "fixture_query", 0.2, lambda: self._render_panes(parts="right"))
            return
        if self._pane_kind == "split" and self.section == "fixtures":
            debounce(self.page, "fixture_query", 0.2, lambda: self._render_panes(parts="left"))
            return
        debounce(self.page, "fixture_query", 0.2, self._render_panes)

    def _leagues_pane(self, width: int) -> ft.Control:
        return leagues_view(
            self._filtered_competitions(),
            loading=self.loading and self.busy == "leagues",
            error=self._error_for("leagues"),
            on_select=self._select_league,
            on_refresh=lambda: self._load_leagues(force=True),
            window_width=width,
            selected_code=self.league.code if self.league else None,
            query=self.league_query,
            on_query=self._on_league_query,
            favorites_only=self.favorites_only,
            on_favorites_only=self._on_favorites_only,
            has_favorites=bool(self.settings.favorite_codes()),
        )

    def _fixtures_pane(
        self,
        width: int,
        *,
        embedded: bool,
        compact_grid: bool,
        show_disclaimer: bool,
    ) -> ft.Control:
        if self.league is None and not (self.loading and self.busy == "fixtures"):
            return info_banner(
                "Выберите лигу, чтобы открыть календарь.",
                action_hint="Откройте вкладку Лиги",
            )
        name = self.league.name if self.league else "Календарь"
        page = self._fixture_page()
        return fixtures_view(
            name,
            page.items,
            loading=self.loading and self.busy == "fixtures",
            error=self._error_for("fixtures"),
            on_open=self._open_match,
            on_back=lambda: self._goto("leagues"),
            on_refresh=lambda: self._load_fixtures(force=True),
            league_emblem=self.league.emblem if self.league else None,
            league_code=self.league.code if self.league else None,
            window_width=width,
            embedded=embedded,
            compact_grid=self.settings.compact_fixtures or compact_grid,
            selected_match_id=self.selected_match_id,
            show_disclaimer=show_disclaimer,
            query=self.fixture_query,
            page_result=page,
            on_query=self._on_fixture_query,
        )

    def _forecast_pane(self, width: int, *, embedded: bool) -> ft.Control:
        return match_detail_view(
            self.forecast,
            loading=self.loading and self.busy == "forecast",
            error=self._error_for("forecast"),
            on_back=lambda: self._goto("fixtures"),
            window_width=width,
            embedded=embedded,
            show_ai_block=self.settings.show_ai_block,
        )

    def _settings_pane(self, width: int) -> ft.Control:
        return settings_view(
            SettingsForm.from_settings(
                self.settings,
                team_choices=self._team_choices(),
                status=self.status,
                error=self._error_for("settings"),
                saving=self.loading and self.busy == "settings",
            ),
            on_save=self._save_settings,
            on_test=self._test_connection,
            on_clear_cache=self._clear_cache,
            window_width=width,
        )

    def _section_body(self, width: int, split: bool) -> ft.Control:
        if self.section == "leagues":
            if split:
                return self._split(
                    self._leagues_pane(width),
                    self._fixtures_pane(
                        width,
                        embedded=True,
                        compact_grid=False,
                        show_disclaimer=True,
                    ),
                )
            return self._leagues_pane(width)
        if self.section == "fixtures":
            if split:
                return self._split(
                    self._fixtures_pane(
                        width,
                        embedded=True,
                        compact_grid=True,
                        show_disclaimer=False,
                    ),
                    self._forecast_pane(width, embedded=True),
                    master_flex=2,
                )
            return self._fixtures_pane(
                width,
                embedded=False,
                compact_grid=False,
                show_disclaimer=True,
            )
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
        self._set_nav(section)
        self._render_panes()

    def _set_splash(self, message: str, fraction: float | None = None) -> None:
        self._splash_message = message
        self._splash_fraction = fraction
        if self.booting:
            self._render_panes()

    def _post_splash(self, message: str, fraction: float | None = None) -> None:
        def apply() -> None:
            self._set_splash(message, fraction)

        runner = getattr(self.page, "run_task", None)
        if callable(runner):
            async def tick() -> None:
                apply()

            runner(tick)
            return
        apply()

    def _start_boot(self) -> None:
        self.booting = True
        self._set_splash("Загружаем данные…")
        self.competitions = self.service.cached_competitions()
        self._set_splash("Обновляем список лиг…")
        run_background(
            self.page,
            self.service.bootstrap,
            self._on_bootstrap,
            self._on_fail,
            message=None,
            cancel_previous=False,
        )

    def _finish_boot(self) -> None:
        self.booting = False
        self.loading = False
        self.busy = None
        self._render_panes()
        self._notify("Приложение готово.", kind="success")

    def _on_bootstrap(self, items: list[Competition]) -> None:
        self.competitions = list(items)
        if self.settings.prefetch_wait_on_start and items:
            self._prefetch_all(items)
            return
        self._finish_boot()

    def _prefetch_all(self, items: list[Competition]) -> None:
        total = len(items)
        self._set_splash(f"Лига 1/{total}: {items[0].code}", 0.0)

        def work() -> None:
            for index, competition in enumerate(items, start=1):
                self._post_splash(
                    f"Лига {index}/{total}: {competition.code}",
                    (index - 1) / total if total else None,
                )
                self.service.prefetch_competition(competition.code)

        run_background(
            self.page,
            work,
            lambda _result: self._finish_boot(),
            self._on_fail,
            message=None,
            cancel_previous=False,
        )

    def _load_leagues(self, force: bool = False) -> None:
        self.loading = True
        self.busy = "leagues"
        self.error = None
        self._set_nav("leagues")
        self._render_panes()

        def work() -> list[Competition]:
            return self.service.list_competitions(force=force)

        run_background(
            self.page,
            work,
            self._on_leagues,
            self._on_fail,
            message="Обновляем список лиг…",
            cancel_previous=True,
        )

    def _on_leagues(self, items: list[Competition]) -> None:
        self.competitions = items
        self.loading = False
        self.busy = None
        self._render_panes()

    def _select_league(self, competition: Competition) -> None:
        self.league = competition
        self.matches = []
        self.forecast = None
        self.selected_match_id = None
        self.fixture_query = replace(self.fixture_query, page=0)
        stay = use_split(window_width(self.page)) and self.section == "leagues"
        self._load_fixtures(stay_on_section=stay)

    def _load_fixtures(self, force: bool = False, stay_on_section: bool = False) -> None:
        if self.league is None:
            self.error = "Сначала выберите лигу."
            self._goto("leagues")
            return
        self.loading = True
        self.busy = "fixtures"
        self.error = None
        if not stay_on_section:
            self._set_nav("fixtures")
        self._render_panes()
        code = self.league.code

        def work() -> list[Match]:
            return self.service.competition_matches(code, force=force)

        run_background(
            self.page,
            work,
            self._on_fixtures,
            self._on_fail,
            message="Загрузка календаря…",
            cancel_previous=True,
        )

    def _on_fixtures(self, matches: list[Match]) -> None:
        self.matches = matches
        self.loading = False
        self.busy = None
        self._render_panes()

    def _open_match(self, match: Match) -> None:
        self.loading = True
        self.busy = "forecast"
        self.error = None
        self.forecast = None
        self.selected_match_id = match.id
        width = window_width(self.page)
        if use_split(width):
            self._set_nav("fixtures")
        else:
            self._set_nav("match")

        def work() -> MatchForecast:
            return self.service.forecast(match, explain=False)

        run_background(
            self.page,
            work,
            self._on_forecast,
            self._on_fail,
            message="Считаем прогноз…",
            cancel_previous=True,
        )
        self._render_panes()

    def _on_forecast(self, forecast: MatchForecast) -> None:
        self.forecast = forecast
        self.loading = False
        self.busy = None
        self._render_panes(parts="right" if self._pane_kind == "split" else "all")
        match = forecast.match
        self._notify(
            f"Прогноз готов: {match.home_name} — {match.away_name}",
            kind="success",
        )
        if not (self.settings.show_ai_block and self.settings.has_openai_key):
            return
        current = self.forecast

        def explain_work() -> MatchForecast:
            return self.service.explain_forecast(current)

        run_background(
            self.page,
            explain_work,
            self._on_explain,
            self._on_explain_fail,
            message=None,
            cancel_previous=False,
        )

    def _on_explain(self, forecast: MatchForecast) -> None:
        self.forecast = forecast
        self._render_panes(parts="right" if self._pane_kind == "split" else "all")

    def _on_explain_fail(self, _message: str) -> None:
        self._render_panes()

    def _on_fail(self, message: str) -> None:
        self.loading = False
        self.busy = None
        self.booting = False
        self.error = message
        self._render_panes()
        self._notify(message, kind="error", alert=True)

    def _save_settings(self, payload: dict[str, str | bool]) -> None:
        self.loading = True
        self.busy = "settings"
        self.error = None
        self.status = None
        self._render_panes()

        def work() -> Settings:
            write_env_value(
                "FOOTBALL_DATA_API_KEY",
                _env_text(payload.get("football_data_api_key")),
            )
            write_env_value("OPENAI_API_KEY", _env_text(payload.get("openai_api_key")))
            write_env_value(
                "OPENAI_MODEL",
                _env_text(payload.get("openai_model"), "gpt-4o-mini"),
            )
            write_env_value(
                "OPENAI_BASE_URL",
                _env_text(payload.get("openai_base_url"), "https://api.openai.com/v1"),
            )
            write_env_value("FAVORITE_LEAGUES", _env_text(payload.get("favorite_leagues")))
            write_env_value("FAVORITE_TEAMS", _env_text(payload.get("favorite_teams")))
            write_env_value(
                "PREFETCH_WAIT_ON_START",
                _env_flag(payload.get("prefetch_wait_on_start", False)),
            )
            write_env_value(
                "SHOW_AI_BLOCK",
                _env_flag(payload.get("show_ai_block", True)),
            )
            write_env_value(
                "COMPACT_FIXTURES",
                _env_flag(payload.get("compact_fixtures", False)),
            )
            write_env_value(
                "SYSTEM_NOTIFICATIONS",
                _env_flag(payload.get("system_notifications", False)),
            )
            return load_settings()

        def ok(settings: Settings) -> None:
            self.settings = settings
            self.service = build_service(settings)
            self.loading = False
            self.busy = None
            self.status = "Настройки сохранены."
            self._render_panes()
            self._notify("Настройки сохранены.", kind="success")

        run_background(
            self.page,
            work,
            ok,
            self._on_fail,
            message="Сохраняем настройки…",
            cancel_previous=True,
        )

    def _clear_cache(self) -> None:
        self.loading = True
        self.busy = "settings"
        self.error = None
        self.status = None
        self._render_panes()

        def work() -> list[Competition]:
            self.service.clear_cache()
            return self.service.cached_competitions()

        def ok(items: list[Competition]) -> None:
            self.competitions = items
            self.matches = []
            self.forecast = None
            self.selected_match_id = None
            self.loading = False
            self.busy = None
            self.status = "Кэш очищен."
            self._render_panes()
            self._notify("Кэш очищен.", kind="info")

        run_background(
            self.page,
            work,
            ok,
            self._on_fail,
            message="Очищаем кэш…",
            cancel_previous=True,
        )

    def _test_connection(self) -> None:
        self.loading = True
        self.busy = "settings"
        self.error = None
        self.status = None
        self._render_panes()

        def work() -> str:
            items = self.service.ping()
            return f"Соединение успешно. Доступно лиг: {len(items)}."

        def ok(message: str) -> None:
            self.loading = False
            self.busy = None
            self.status = message
            self._render_panes()
            self._notify(message, kind="success")

        run_background(
            self.page,
            work,
            ok,
            self._on_fail,
            message="Проверяем соединение…",
            cancel_previous=True,
        )


def start_ui(
    page: ft.Page,
    service: MatchService | None = None,
    settings: Settings | None = None,
) -> FootballApp:
    configure_window(page)
    page.title = "Football Prognoz"
    cleaner = getattr(page, "clean", None)
    if callable(cleaner):
        cleaner()
    else:
        controls = getattr(page, "controls", None)
        if isinstance(controls, list):
            controls.clear()
    page.add(splash_view("Запуск приложения…"))
    updater = getattr(page, "update", None)
    if callable(updater):
        updater()
    settings = settings or load_settings()
    service = service or build_service(settings)
    if callable(cleaner):
        cleaner()
    else:
        controls = getattr(page, "controls", None)
        if isinstance(controls, list):
            controls.clear()
    return FootballApp(page, service, settings)
