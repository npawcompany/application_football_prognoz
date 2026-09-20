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
from football_prognoz.ui.runtime import run_background
from football_prognoz.ui.views.fixtures import fixtures_view
from football_prognoz.ui.views.leagues import leagues_view
from football_prognoz.ui.views.match_detail import match_detail_view
from football_prognoz.ui.views.settings import settings_view


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
        self.loading = False
        self.error: str | None = None
        self.status: str | None = None
        self.body = ft.Container(expand=True, padding=20)
        self._build_shell()
        if settings.has_football_key:
            self._load_leagues()
        else:
            self.section = "settings"
            self.status = "Введите ключ football-data.org, чтобы загрузить лиги."
            self._render()

    def _build_shell(self) -> None:
        page = self.page
        page.title = "Football Prognoz"
        page.theme_mode = ft.ThemeMode.DARK
        page.padding = 0
        page.appbar = ft.AppBar(title=ft.Text("Football Prognoz"), center_title=False)
        page.navigation_bar = ft.NavigationBar(
            destinations=[
                ft.NavigationBarDestination(icon=ft.Icons.SPORTS_SOCCER, label="Лиги"),
                ft.NavigationBarDestination(icon=ft.Icons.CALENDAR_MONTH, label="Календарь"),
                ft.NavigationBarDestination(icon=ft.Icons.QUERY_STATS, label="Прогноз"),
                ft.NavigationBarDestination(icon=ft.Icons.SETTINGS, label="Настройки"),
            ],
            on_change=self._on_nav,
        )
        page.add(self.body)
        self._render()

    def _on_nav(self, event: ft.ControlEvent) -> None:
        index = int(event.control.selected_index)
        mapping = {0: "leagues", 1: "fixtures", 2: "match", 3: "settings"}
        self.section = mapping.get(index, "leagues")
        self.error = None
        if self.section == "leagues" and not self.competitions:
            self._load_leagues()
            return
        self._render()

    def _set_nav(self, section: str) -> None:
        self.section = section
        index = {"leagues": 0, "fixtures": 1, "match": 2, "settings": 3}[section]
        if self.page.navigation_bar is not None:
            self.page.navigation_bar.selected_index = index

    def _render(self) -> None:
        if self.section == "leagues":
            content = leagues_view(
                self.competitions,
                loading=self.loading,
                error=self.error,
                on_select=self._select_league,
                on_refresh=lambda: self._load_leagues(force=True),
            )
        elif self.section == "fixtures":
            name = self.league.name if self.league else "Календарь"
            content = fixtures_view(
                name,
                self.matches,
                loading=self.loading,
                error=self.error,
                on_open=self._open_match,
                on_back=lambda: self._goto("leagues"),
                on_refresh=lambda: self._load_fixtures(force=True),
            )
        elif self.section == "match":
            content = match_detail_view(
                self.forecast,
                loading=self.loading,
                error=self.error,
                on_back=lambda: self._goto("fixtures"),
            )
        else:
            content = settings_view(
                self.settings.football_data_api_key,
                self.settings.openai_api_key,
                self.settings.openai_model,
                self.settings.openai_base_url,
                status=self.status,
                error=self.error,
                saving=self.loading,
                on_save=self._save_settings,
                on_test=self._test_connection,
            )
        self.body.content = content
        self.page.update()

    def _goto(self, section: str) -> None:
        self.error = None
        self._set_nav(section)
        self._render()

    def _load_leagues(self, force: bool = False) -> None:
        self.loading = True
        self.error = None
        self._set_nav("leagues")
        self._render()

        def work() -> list[Competition]:
            return self.service.list_competitions(force=force)

        run_background(self.page, work, self._on_leagues, self._on_fail)

    def _on_leagues(self, items: list[Competition]) -> None:
        self.competitions = items
        self.loading = False
        self._render()

    def _select_league(self, competition: Competition) -> None:
        self.league = competition
        self.matches = []
        self._load_fixtures()

    def _load_fixtures(self, force: bool = False) -> None:
        if self.league is None:
            self.error = "Сначала выберите лигу."
            self._goto("leagues")
            return
        self.loading = True
        self.error = None
        self._set_nav("fixtures")
        self._render()
        code = self.league.code

        def work() -> list[Match]:
            return self.service.upcoming(code, force=force)

        run_background(self.page, work, self._on_fixtures, self._on_fail)

    def _on_fixtures(self, matches: list[Match]) -> None:
        self.matches = matches
        self.loading = False
        self._render()

    def _open_match(self, match: Match) -> None:
        self.loading = True
        self.error = None
        self.forecast = None
        self._set_nav("match")
        self._render()

        def work() -> MatchForecast:
            return self.service.forecast(match)

        run_background(self.page, work, self._on_forecast, self._on_fail)

    def _on_forecast(self, forecast: MatchForecast) -> None:
        self.forecast = forecast
        self.loading = False
        self._render()

    def _on_fail(self, message: str) -> None:
        self.loading = False
        self.error = message
        self._render()

    def _save_settings(self, football_key: str, openai_key: str, model: str, base_url: str) -> None:
        self.loading = True
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
            self.status = "Ключи сохранены в .env."
            self._render()

        run_background(self.page, work, ok, self._on_fail)

    def _test_connection(self) -> None:
        self.loading = True
        self.error = None
        self.status = None
        self._render()

        def work() -> str:
            items = self.service.ping()
            return f"Соединение успешно. Доступно лиг: {len(items)}."

        def ok(message: str) -> None:
            self.loading = False
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
