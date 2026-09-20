from __future__ import annotations

from collections.abc import Callable

import flet as ft

from football_prognoz.ui.components.settings_panel import (
    SettingsForm,
    settings_aside,
    settings_switches,
)
from football_prognoz.ui.runtime import error_banner, info_banner
from football_prognoz.ui.theme import ACCENT, FG, MUTED

__all__ = ["SettingsForm", "settings_view"]


def settings_view(
    form: SettingsForm,
    *,
    on_save: Callable[[dict[str, str | bool]], None],
    on_test: Callable[[], None],
    on_clear_cache: Callable[[], None],
    window_width: int = 1440,
) -> ft.Control:
    """Settings screen (Настройки).

    ``on_save`` receives every editable value as a single dict (Wave 2 should persist
    these keys to ``.env`` via ``write_env_value``):

        football_data_api_key: str
        openai_api_key: str
        openai_model: str
        openai_base_url: str
        favorite_leagues: str
        prefetch_wait_on_start: bool
        show_ai_block: bool
        compact_fixtures: bool

    ``on_test`` pings football-data.org (wired by the app).
    ``on_clear_cache`` is invoked with no arguments; this view does not touch SQLite.
    """
    saving = form.saving
    football_field = ft.TextField(
        label="FOOTBALL_DATA_API_KEY · обязательный",
        value=form.football_data_api_key,
        password=True,
        can_reveal_password=True,
        border_color=MUTED,
        disabled=saving,
    )
    openai_field = ft.TextField(
        label="OPENAI_API_KEY · необязательный",
        value=form.openai_api_key,
        password=True,
        can_reveal_password=True,
        border_color=MUTED,
        disabled=saving,
    )
    model_field = ft.TextField(
        label="OPENAI_MODEL",
        value=form.openai_model,
        border_color=MUTED,
        disabled=saving,
    )
    base_field = ft.TextField(
        label="OPENAI_BASE_URL",
        value=form.openai_base_url,
        border_color=MUTED,
        disabled=saving,
    )
    leagues_field = ft.TextField(
        label="Любимые лиги",
        value=form.favorite_leagues,
        hint_text="PL,PD,SA",
        border_color=MUTED,
        disabled=saving,
    )
    prefetch_sw, ai_sw, compact_sw = settings_switches(
        form.prefetch_wait_on_start,
        form.show_ai_block,
        form.compact_fixtures,
        disabled=saving,
    )

    def _submit(_e: ft.ControlEvent | None = None) -> None:
        on_save(
            {
                "football_data_api_key": football_field.value or "",
                "openai_api_key": openai_field.value or "",
                "openai_model": model_field.value or "gpt-4o-mini",
                "openai_base_url": base_field.value or "https://api.openai.com/v1",
                "favorite_leagues": leagues_field.value or "",
                "prefetch_wait_on_start": bool(prefetch_sw.value),
                "show_ai_block": bool(ai_sw.value),
                "compact_fixtures": bool(compact_sw.value),
            }
        )

    form_column = ft.Column(
        [
            football_field,
            openai_field,
            model_field,
            base_field,
            leagues_field,
            prefetch_sw,
            ai_sw,
            compact_sw,
            ft.Row(
                [
                    ft.FilledButton(
                        "Сохранить",
                        bgcolor=ACCENT,
                        color="#0F172A",
                        disabled=saving,
                        on_click=_submit,
                    ),
                    ft.OutlinedButton(
                        "Проверить football-data.org",
                        disabled=saving,
                        on_click=lambda _e: on_test(),
                    ),
                    ft.OutlinedButton(
                        "Очистить кэш",
                        disabled=saving,
                        on_click=lambda _e: on_clear_cache(),
                    ),
                ],
                wrap=True,
                spacing=8,
            ),
        ],
        spacing=12,
        expand=True,
    )
    aside = settings_aside(form.database_path, window_width=window_width)
    body: list[ft.Control] = [
        ft.Text("Настройки", size=22, weight=ft.FontWeight.BOLD, color=FG, font_family="Fira Code"),
        ft.Row(
            [form_column, aside],
            spacing=16,
            vertical_alignment=ft.CrossAxisAlignment.START,
            wrap=True,
        ),
    ]
    if saving:
        body.append(ft.ProgressRing(color=ACCENT))
    if form.error:
        body.append(error_banner(form.error))
    if form.status:
        body.append(info_banner(form.status))
    return ft.Column(body, spacing=12, expand=True, scroll=ft.ScrollMode.AUTO)
