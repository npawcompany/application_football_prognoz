"""Reusable Settings screen chunks. Wave 2 wires these; do not import from app.py here."""

from __future__ import annotations

from dataclasses import dataclass, field

import flet as ft

from football_prognoz.config import Settings
from football_prognoz.domain.team import Team
from football_prognoz.ui.theme import ACCENT, BREAKPOINT_MEDIUM, CARD, FG, MUTED, glass_border


@dataclass(frozen=True)
class SettingsForm:
    """Immutable snapshot of the Settings screen: config fields plus UI status."""

    football_data_api_key: str = ""
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = "https://api.openai.com/v1"
    database_path: str = "data/cache/prognoz.db"
    favorite_leagues: str = ""
    favorite_teams: str = ""
    team_choices: tuple[Team, ...] = field(default_factory=tuple)
    prefetch_wait_on_start: bool = False
    show_ai_block: bool = True
    compact_fixtures: bool = False
    system_notifications: bool = False
    status: str | None = None
    error: str | None = None
    saving: bool = False

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        *,
        team_choices: tuple[Team, ...] | list[Team] = (),
        status: str | None = None,
        error: str | None = None,
        saving: bool = False,
    ) -> SettingsForm:
        return cls(
            football_data_api_key=settings.football_data_api_key,
            openai_api_key=settings.openai_api_key,
            openai_model=settings.openai_model,
            openai_base_url=settings.openai_base_url,
            database_path=settings.database_path,
            favorite_leagues=settings.favorite_leagues,
            favorite_teams=settings.favorite_teams,
            team_choices=tuple(team_choices),
            prefetch_wait_on_start=settings.prefetch_wait_on_start,
            show_ai_block=settings.show_ai_block,
            compact_fixtures=settings.compact_fixtures,
            system_notifications=settings.system_notifications,
            status=status,
            error=error,
            saving=saving,
        )


def settings_aside(database_path: str, *, window_width: int = 1440) -> ft.Control:
    """Read-only helper column: .env keys, DB path, rate limit, not betting advice."""
    wide = window_width >= BREAKPOINT_MEDIUM
    return ft.Container(
        content=ft.Column(
            [
                ft.Text("Локальное хранение ключей", size=16, weight=ft.FontWeight.W_600, color=FG),
                ft.Text(
                    "Ключи хранятся только в локальном .env и не попадают в git. "
                    "Модель Elo + Poisson считает вероятности 1X2 на этом компьютере. "
                    "Это не совет ставить деньги.",
                    size=12,
                    color=MUTED,
                    max_lines=8,
                    overflow=ft.TextOverflow.ELLIPSIS,
                ),
                ft.Divider(color=ft.Colors.with_opacity(0.12, ft.Colors.WHITE)),
                ft.Text("База данных", size=13, weight=ft.FontWeight.W_600, color=FG),
                ft.Text(database_path, size=12, color=MUTED, selectable=True, max_lines=3),
                ft.Divider(color=ft.Colors.with_opacity(0.12, ft.Colors.WHITE)),
                ft.Text(
                    "football-data.org · лимит 10 запросов/мин",
                    size=12,
                    color=MUTED,
                    max_lines=2,
                ),
                ft.Text(
                    "OpenAI опционален для пояснения, не для выбора исхода",
                    size=12,
                    color=MUTED,
                    max_lines=3,
                ),
                ft.Text(
                    "Системные уведомления: macOS запросит разрешение при первой отправке.",
                    size=12,
                    color=MUTED,
                    max_lines=3,
                ),
            ],
            spacing=10,
        ),
        bgcolor=CARD,
        border=glass_border(),
        border_radius=12,
        padding=24,
        width=360 if wide else None,
        expand=False,
    )


def settings_switches(
    prefetch_wait_on_start: bool,
    show_ai_block: bool,
    compact_fixtures: bool,
    system_notifications: bool,
    *,
    disabled: bool = False,
) -> tuple[ft.Switch, ft.Switch, ft.Switch, ft.Switch]:
    """App option toggles. Order: prefetch, AI block, compact fixtures, system notify."""
    style = ft.TextStyle(color=FG, size=13)
    prefetch = ft.Switch(
        label="Ждать обновление всех лиг при старте",
        value=prefetch_wait_on_start,
        active_color=ACCENT,
        disabled=disabled,
        label_text_style=style,
    )
    show_ai = ft.Switch(
        label="Показывать AI-пояснение",
        value=show_ai_block,
        active_color=ACCENT,
        disabled=disabled,
        label_text_style=style,
    )
    compact = ft.Switch(
        label="Компактный календарь",
        value=compact_fixtures,
        active_color=ACCENT,
        disabled=disabled,
        label_text_style=style,
    )
    system = ft.Switch(
        label="Разрешить системные уведомления",
        value=system_notifications,
        active_color=ACCENT,
        disabled=disabled,
        label_text_style=style,
    )
    return prefetch, show_ai, compact, system
