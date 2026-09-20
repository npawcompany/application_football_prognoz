from __future__ import annotations

import flet as ft

from football_prognoz.ai.explainer import Explainer, OpenAICompatClient
from football_prognoz.config import Settings, load_settings, write_env_value
from football_prognoz.data.football_data_org import FootballDataOrgClient
from football_prognoz.data.store import SQLiteStore
from football_prognoz.domain.match import Match
from football_prognoz.domain.prediction import MatchForecast
from football_prognoz.domain.team import Competition
from football_prognoz.models.predictor import Predictor
from football_prognoz.services.features import FeatureService
from football_prognoz.services.matches import MatchService
from football_prognoz.ui.runtime import info_banner, run_background
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
        self.body = ft.Container(expand=True, padding=0, bgcolor=BG)
        self._build_shell()
        if settings.has_football_key:
            self._load_leagues()
        else:
            self.section = "settings"
            self.status = "Введите ключ football-data.org, чтобы загрузить лиги."
            self._render()

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
        page.add(self.body)
        self._render()

    def _on_resized(self, _event: ft.ControlEvent) -> None:
        self._render()

    def _on_nav(self, event: ft.ControlEvent) -> None:
        index = int(event.control.selected_index)
        self.section = SECTIONS[index] if 0 <= index < len(SECTIONS) else "leagues"
        self.error = None
        if self.section == "leagues" and not self.competitions:
            self._load_leagues()
            return
        self._render()

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
        return ft.Row(
            [
                ft.Container(content=master, expand=master_flex, padding=ft.padding.only(right=8)),
                ft.VerticalDivider(
                    width=1,
                    color=ft.Colors.with_opacity(0.18, ft.Colors.WHITE),
                ),
                ft.Container(content=detail, expand=2, padding=ft.padding.only(left=8)),
            ],
            expand=True,
            spacing=0,
            vertical_alignment=ft.CrossAxisAlignment.STRETCH,
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

    def _leagues_pane(self, width: int) -> ft.Control:
        return leagues_view(
            self.competitions,
            loading=self.loading and self.busy == "leagues",
            error=self._error_for("leagues"),
            on_select=self._select_league,
            on_refresh=lambda: self._load_leagues(force=True),
            window_width=width,
            selected_code=self.league.code if self.league else None,
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
        return fixtures_view(
            name,
            self.matches,
            loading=self.loading and self.busy == "fixtures",
            error=self._error_for("fixtures"),
            on_open=self._open_match,
            on_back=lambda: self._goto("leagues"),
            on_refresh=lambda: self._load_fixtures(force=True),
            league_emblem=self.league.emblem if self.league else None,
            league_code=self.league.code if self.league else None,
            window_width=width,
            embedded=embedded,
            compact_grid=compact_grid,
            selected_match_id=self.selected_match_id,
            show_disclaimer=show_disclaimer,
        )

    def _forecast_pane(self, width: int, *, embedded: bool) -> ft.Control:
        return match_detail_view(
            self.forecast,
            loading=self.loading and self.busy == "forecast",
            error=self._error_for("forecast"),
            on_back=lambda: self._goto("fixtures"),
            window_width=width,
            embedded=embedded,
        )

    def _settings_pane(self, width: int) -> ft.Control:
        return settings_view(
            self.settings.football_data_api_key,
            self.settings.openai_api_key,
            self.settings.openai_model,
            self.settings.openai_base_url,
            status=self.status,
            error=self._error_for("settings"),
            saving=self.loading and self.busy == "settings",
            on_save=self._save_settings,
            on_test=self._test_connection,
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
        split = use_split(width)
        rail = use_rail(width)
        content = ft.Container(
            content=self._section_body(width, split),
            expand=True,
            padding=BODY_PADDING,
            bgcolor=BG,
        )
        if rail:
            self.page.navigation_bar = None
            self.body.content = ft.Row(
                [
                    self._navigation_rail(),
                    ft.VerticalDivider(
                        width=1,
                        color=ft.Colors.with_opacity(0.18, ft.Colors.WHITE),
                    ),
                    content,
                ],
                expand=True,
                spacing=0,
            )
        else:
            self.page.navigation_bar = self._navigation_bar()
            self.body.content = content
        self.page.update()

    def _goto(self, section: str) -> None:
        self.error = None
        self._set_nav(section)
        self._render()

    def _load_leagues(self, force: bool = False) -> None:
        self.loading = True
        self.busy = "leagues"
        self.error = None
        self._set_nav("leagues")
        self._render()

        def work() -> list[Competition]:
            return self.service.list_competitions(force=force)

        run_background(self.page, work, self._on_leagues, self._on_fail)

    def _on_leagues(self, items: list[Competition]) -> None:
        self.competitions = items
        self.loading = False
        self.busy = None
        self._render()

    def _select_league(self, competition: Competition) -> None:
        self.league = competition
        self.matches = []
        self.forecast = None
        self.selected_match_id = None
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
        self._render()
        code = self.league.code

        def work() -> list[Match]:
            return self.service.upcoming(code, force=force)

        run_background(self.page, work, self._on_fixtures, self._on_fail)

    def _on_fixtures(self, matches: list[Match]) -> None:
        self.matches = matches
        self.loading = False
        self.busy = None
        self._render()

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
        self._render()

        def work() -> MatchForecast:
            return self.service.forecast(match)

        run_background(self.page, work, self._on_forecast, self._on_fail)

    def _on_forecast(self, forecast: MatchForecast) -> None:
        self.forecast = forecast
        self.loading = False
        self.busy = None
        self._render()

    def _on_fail(self, message: str) -> None:
        self.loading = False
        self.error = message
        self._render()

    def _save_settings(self, football_key: str, openai_key: str, model: str, base_url: str) -> None:
        self.loading = True
        self.busy = "settings"
        self.error = None
        self.status = None
        self._render()

        def work() -> Settings:
            write_env_value("FOOTBALL_DATA_API_KEY", football_key.strip())
            write_env_value("OPENAI_API_KEY", openai_key.strip())
            write_env_value("OPENAI_MODEL", model.strip() or "gpt-4o-mini")
            write_env_value("OPENAI_BASE_URL", base_url.strip() or "https://api.openai.com/v1")
            settings = load_settings()
            return settings

        def ok(settings: Settings) -> None:
            self.settings = settings
            self.service = build_service(settings)
            self.loading = False
            self.busy = None
            self.status = "Ключи сохранены в .env."
            self._render()

        run_background(self.page, work, ok, self._on_fail)

    def _test_connection(self) -> None:
        self.loading = True
        self.busy = "settings"
        self.error = None
        self.status = None
        self._render()

        def work() -> str:
            items = self.service.ping()
            return f"Соединение успешно. Доступно лиг: {len(items)}."

        def ok(message: str) -> None:
            self.loading = False
            self.busy = None
            self.status = message
            self._render()

        run_background(self.page, work, ok, self._on_fail)


def start_ui(
    page: ft.Page,
    service: MatchService | None = None,
    settings: Settings | None = None,
) -> FootballApp:
    settings = settings or load_settings()
    service = service or build_service(settings)
    return FootballApp(page, service, settings)
