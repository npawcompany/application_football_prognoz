from __future__ import annotations

from collections.abc import Callable

import flet as ft

from football_prognoz.ui.runtime import error_banner, info_banner


def settings_view(
    football_key: str,
    openai_key: str,
    openai_model: str,
    openai_base_url: str,
    *,
    status: str | None,
    error: str | None,
    saving: bool,
    on_save: Callable[[str, str, str, str], None],
    on_test: Callable[[], None],
) -> ft.Control:
    football_field = ft.TextField(
        label="FOOTBALL_DATA_API_KEY",
        value=football_key,
        password=True,
        can_reveal_password=True,
    )
    openai_field = ft.TextField(
        label="OPENAI_API_KEY (необязательно)",
        value=openai_key,
        password=True,
        can_reveal_password=True,
    )
    model_field = ft.TextField(label="OPENAI_MODEL", value=openai_model)
    base_field = ft.TextField(label="OPENAI_BASE_URL", value=openai_base_url)

    body: list[ft.Control] = [
        ft.Text("Настройки", size=24, weight=ft.FontWeight.BOLD),
        ft.Text("Ключи хранятся только в локальном файле .env и не попадают в git."),
        football_field,
        openai_field,
        model_field,
        base_field,
        ft.Row(
            [
                ft.FilledButton(
                    "Сохранить",
                    disabled=saving,
                    on_click=lambda _e: on_save(
                        football_field.value or "",
                        openai_field.value or "",
                        model_field.value or "gpt-4o-mini",
                        base_field.value or "https://api.openai.com/v1",
                    ),
                ),
                ft.OutlinedButton("Проверить football-data.org", on_click=lambda _e: on_test()),
            ]
        ),
    ]
    if saving:
        body.append(ft.ProgressRing())
    if error:
        body.append(error_banner(error))
    if status:
        body.append(info_banner(status))
    return ft.Column(body, spacing=12, expand=True, scroll=ft.ScrollMode.AUTO)
