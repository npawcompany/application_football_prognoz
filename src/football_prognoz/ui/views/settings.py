from __future__ import annotations

from collections.abc import Callable

import flet as ft

from football_prognoz.ui.runtime import error_banner, info_banner
from football_prognoz.ui.theme import ACCENT, BREAKPOINT_MEDIUM, CARD, FG, MUTED, glass_border


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
    window_width: int = 1440,
) -> ft.Control:
    football_field = ft.TextField(
        label="FOOTBALL_DATA_API_KEY · обязательный",
        value=football_key,
        password=True,
        can_reveal_password=True,
        border_color=MUTED,
    )
    openai_field = ft.TextField(
        label="OPENAI_API_KEY · необязательный",
        value=openai_key,
        password=True,
        can_reveal_password=True,
        border_color=MUTED,
    )
    model_field = ft.TextField(label="OPENAI_MODEL", value=openai_model, border_color=MUTED)
    base_field = ft.TextField(label="OPENAI_BASE_URL", value=openai_base_url, border_color=MUTED)

    form = ft.Column(
        [
            football_field,
            openai_field,
            model_field,
            base_field,
            ft.Row(
                [
                    ft.FilledButton(
                        "Сохранить",
                        bgcolor=ACCENT,
                        color="#0F172A",
                        disabled=saving,
                        on_click=lambda _e: on_save(
                            football_field.value or "",
                            openai_field.value or "",
                            model_field.value or "gpt-4o-mini",
                            base_field.value or "https://api.openai.com/v1",
                        ),
                    ),
                    ft.OutlinedButton(
                        "Проверить football-data.org",
                        on_click=lambda _e: on_test(),
                    ),
                ]
            ),
        ],
        spacing=12,
        expand=True,
    )
    aside = ft.Container(
        content=ft.Column(
            [
                ft.Text("Локальное хранение ключей", size=16, weight=ft.FontWeight.W_600, color=FG),
                ft.Text(
                    "Ключи хранятся только в локальном .env и не попадают в git. "
                    "Модель Elo + Poisson считает вероятности 1X2 на этом компьютере. "
                    "Это не совет ставить деньги.",
                    size=12,
                    color=MUTED,
                ),
                ft.Divider(color=ft.Colors.with_opacity(0.12, ft.Colors.WHITE)),
                ft.Text("football-data.org · лимит 10 запросов/мин", size=12, color=MUTED),
                ft.Text(
                    "OpenAI опционален для пояснения, не для выбора исхода",
                    size=12,
                    color=MUTED,
                ),
            ],
            spacing=10,
        ),
        bgcolor=CARD,
        border=glass_border(),
        border_radius=12,
        padding=16,
        width=360 if window_width >= BREAKPOINT_MEDIUM else None,
        expand=window_width < BREAKPOINT_MEDIUM,
    )
    body: list[ft.Control] = [
        ft.Text("Настройки", size=22, weight=ft.FontWeight.BOLD, color=FG, font_family="Fira Code"),
        ft.Row(
            [form, aside],
            spacing=16,
            vertical_alignment=ft.CrossAxisAlignment.START,
            wrap=True,
        ),
    ]
    if saving:
        body.append(ft.ProgressRing(color=ACCENT))
    if error:
        body.append(error_banner(error))
    if status:
        body.append(info_banner(status))
    return ft.Column(body, spacing=12, expand=True, scroll=ft.ScrollMode.AUTO)
