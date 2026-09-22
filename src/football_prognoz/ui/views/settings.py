from __future__ import annotations

from collections.abc import Callable

import flet as ft

from football_prognoz.ui.components.settings_panel import (
    SettingsForm,
    settings_aside,
    settings_switches,
)
from football_prognoz.ui.motion import apply_motion, with_cursor
from football_prognoz.ui.runtime import error_banner, info_banner
from football_prognoz.ui.theme import (
    ACCENT,
    BG,
    BREAKPOINT_MEDIUM,
    FG,
    MUTED,
    SURFACE,
    scaled,
)

__all__ = ["SettingsForm", "settings_view"]

_FIELD_BG = "#121A2B"


def _settings_field(
    *,
    label: str,
    value: str,
    disabled: bool,
    window_width: int,
    password: bool = False,
    can_reveal_password: bool = False,
    hint_text: str | None = None,
) -> ft.Control:
    field = ft.TextField(
        value=value,
        disabled=disabled,
        password=password,
        can_reveal_password=can_reveal_password,
        hint_text=hint_text,
        filled=True,
        bgcolor=_FIELD_BG,
        fill_color=_FIELD_BG,
        focused_bgcolor=_FIELD_BG,
        color=FG,
        border_color=ft.Colors.with_opacity(0.18, ft.Colors.WHITE),
        focused_border_color=ACCENT,
        cursor_color=ACCENT,
        text_size=scaled(14, window_width),
        content_padding=ft.Padding.symmetric(horizontal=14, vertical=12),
        border_radius=10,
        mouse_cursor=ft.MouseCursor.TEXT,
    )
    return ft.Column(
        [
            ft.Text(label, size=scaled(12, window_width), color=MUTED),
            field,
        ],
        spacing=6,
        tight=True,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        data=field,
    )


def _field_value(wrapped: ft.Control) -> ft.TextField:
    return wrapped.data  # type: ignore[return-value]


def _switch_row(switch: ft.Switch, *, window_width: int) -> ft.Control:
    caption = switch.label or ""
    switch.label = None
    return ft.Container(
        content=ft.Row(
            [
                ft.Text(caption, size=scaled(13, window_width), color=FG, expand=True),
                switch,
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding.symmetric(vertical=6),
    )


def _parse_team_ids(raw: str) -> list[str]:
    seen: set[str] = set()
    ids: list[str] = []
    for part in raw.split(","):
        text = part.strip()
        if not text.isdigit() or text in seen:
            continue
        seen.add(text)
        ids.append(text)
    return ids


def _favorite_teams_picker(
    form: SettingsForm,
    *,
    window_width: int,
    disabled: bool,
) -> tuple[ft.Control, Callable[[], str]]:
    selected = _parse_team_ids(form.favorite_teams)
    names = {str(team.id): team.name for team in form.team_choices}
    chip_row = ft.Row([], wrap=True, spacing=8, run_spacing=8)

    def _rebuild_chips() -> None:
        chips: list[ft.Control] = []
        for team_id in selected:
            label = names.get(team_id, team_id)
            chips.append(
                apply_motion(
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Text(label, size=scaled(12, window_width), color=FG),
                                ft.IconButton(
                                    icon=ft.Icons.CLOSE,
                                    icon_size=14,
                                    tooltip="Убрать",
                                    style=ft.ButtonStyle(padding=0),
                                    on_click=lambda _e, current=team_id: _remove(current),
                                ),
                            ],
                            spacing=4,
                            tight=True,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        bgcolor=SURFACE,
                        padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                        border_radius=8,
                    ),
                    interactive=True,
                )
            )
        chip_row.controls = chips
        try:
            chip_row.update()
        except Exception:  # noqa: BLE001 — first paint has no page
            pass

    def _remove(team_id: str) -> None:
        if team_id in selected:
            selected.remove(team_id)
        _rebuild_chips()

    def _add(event: ft.ControlEvent | None = None) -> None:
        control = event.control if event is not None else dropdown
        key = str(getattr(control, "value", "") or "")
        if key and key != "__none__" and key not in selected:
            selected.append(key)
        dropdown.value = None
        _rebuild_chips()

    options = [
        ft.DropdownOption(key=str(team.id), text=team.name) for team in form.team_choices
    ]
    dropdown = ft.Dropdown(
        options=options,
        enable_filter=True,
        editable=True,
        filled=True,
        fill_color=_FIELD_BG,
        bgcolor=_FIELD_BG,
        color=FG,
        border_color=ft.Colors.with_opacity(0.18, ft.Colors.WHITE),
        focused_border_color=ACCENT,
        border_radius=10,
        text_size=scaled(14, window_width),
        content_padding=ft.Padding.symmetric(horizontal=14, vertical=12),
        hint_text="Выберите команду"
        if options
        else "Команды появятся после загрузки календаря",
        disabled=disabled or not options,
        menu_height=320,
        on_select=_add,
    )
    _rebuild_chips()
    block = ft.Column(
        [
            ft.Text("Любимые команды", size=scaled(12, window_width), color=MUTED),
            dropdown,
            chip_row,
        ],
        spacing=6,
        tight=True,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
    )
    return block, lambda: ",".join(selected)


def settings_view(
    form: SettingsForm,
    *,
    on_save: Callable[[dict[str, str | bool]], None],
    on_test: Callable[[], None],
    on_clear_cache: Callable[[], None],
    window_width: int = 1440,
) -> ft.Control:
    saving = form.saving
    football_wrap = _settings_field(
        label="FOOTBALL_DATA_API_KEY · обязательный",
        value=form.football_data_api_key,
        disabled=saving,
        window_width=window_width,
        password=True,
        can_reveal_password=True,
    )
    openai_wrap = _settings_field(
        label="OPENAI_API_KEY · необязательный",
        value=form.openai_api_key,
        disabled=saving,
        window_width=window_width,
        password=True,
        can_reveal_password=True,
    )
    model_wrap = _settings_field(
        label="OPENAI_MODEL",
        value=form.openai_model,
        disabled=saving,
        window_width=window_width,
    )
    base_wrap = _settings_field(
        label="OPENAI_BASE_URL",
        value=form.openai_base_url,
        disabled=saving,
        window_width=window_width,
    )
    leagues_wrap = _settings_field(
        label="Любимые лиги",
        value=form.favorite_leagues,
        disabled=saving,
        window_width=window_width,
        hint_text="PL,PD,SA",
    )
    teams_wrap, teams_value = _favorite_teams_picker(
        form, window_width=window_width, disabled=saving
    )
    football_field = _field_value(football_wrap)
    openai_field = _field_value(openai_wrap)
    model_field = _field_value(model_wrap)
    base_field = _field_value(base_wrap)
    leagues_field = _field_value(leagues_wrap)
    prefetch_sw, ai_sw, compact_sw, system_sw = settings_switches(
        form.prefetch_wait_on_start,
        form.show_ai_block,
        form.compact_fixtures,
        form.system_notifications,
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
                "favorite_teams": teams_value(),
                "prefetch_wait_on_start": bool(prefetch_sw.value),
                "show_ai_block": bool(ai_sw.value),
                "compact_fixtures": bool(compact_sw.value),
                "system_notifications": bool(system_sw.value),
            }
        )

    form_body = ft.Column(
        [
            football_wrap,
            openai_wrap,
            model_wrap,
            base_wrap,
            leagues_wrap,
            teams_wrap,
            _switch_row(prefetch_sw, window_width=window_width),
            _switch_row(ai_sw, window_width=window_width),
            _switch_row(compact_sw, window_width=window_width),
            _switch_row(system_sw, window_width=window_width),
            ft.Row(
                [
                    with_cursor(
                        ft.FilledButton(
                            "Сохранить",
                            bgcolor=ACCENT,
                            color="#0F172A",
                            disabled=saving,
                            on_click=_submit,
                        ),
                        interactive=True,
                    ),
                    with_cursor(
                        ft.OutlinedButton(
                            "Проверить football-data.org",
                            disabled=saving,
                            on_click=lambda _e: on_test(),
                        ),
                        interactive=True,
                    ),
                    with_cursor(
                        ft.OutlinedButton(
                            "Очистить кэш",
                            disabled=saving,
                            on_click=lambda _e: on_clear_cache(),
                        ),
                        interactive=True,
                    ),
                ],
                wrap=True,
                spacing=8,
                run_spacing=8,
            ),
        ],
        spacing=12,
        tight=True,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
    )
    form_card = apply_motion(ft.Container(content=form_body, padding=4))
    form_scroll = ft.ListView(
        [form_card],
        expand=True,
        spacing=0,
        padding=0,
    )
    aside = settings_aside(form.database_path, window_width=window_width)
    if window_width >= BREAKPOINT_MEDIUM:
        layout: ft.Control = ft.Row(
            [
                ft.Container(content=form_scroll, expand=True),
                aside,
            ],
            spacing=24,
            expand=True,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )
    else:
        layout = ft.Column(
            [form_scroll, aside],
            spacing=16,
            expand=True,
        )
    banners: list[ft.Control] = []
    if saving:
        banners.append(ft.ProgressRing(color=ACCENT))
    if form.error:
        banners.append(error_banner(form.error))
    if form.status:
        banners.append(info_banner(form.status))
    return ft.Container(
        content=ft.Column(
            [
                ft.Text(
                    "Настройки",
                    size=scaled(28, window_width),
                    weight=ft.FontWeight.BOLD,
                    color=FG,
                ),
                layout,
                *banners,
            ],
            spacing=16,
            expand=True,
        ),
        expand=True,
        bgcolor=BG,
    )
