from __future__ import annotations

from collections.abc import Callable

import flet as ft

from football_prognoz.config import (
    DEFAULT_OLLAMA_FALLBACK_MODEL,
    DEFAULT_OLLAMA_MODEL,
    KNOWN_OLLAMA_MODELS,
    OLLAMA_CLOUD_HOST,
)
from football_prognoz.domain.team import Competition, Team
from football_prognoz.services.leagues import LeagueInfo, group_teams_by_league
from football_prognoz.ui.components.crest import crest_image
from football_prognoz.ui.components.settings_panel import (
    SettingsForm,
    settings_aside,
    settings_switches,
)
from football_prognoz.ui.motion import apply_motion, with_cursor
from football_prognoz.ui.runtime import error_banner, info_banner
from football_prognoz.ui.theme import (
    ACCENT,
    BREAKPOINT_MEDIUM,
    CARD,
    FG,
    MUTED,
    PANE_BG,
    SURFACE,
    glass_border,
    scaled,
)
from football_prognoz.ui.theme import DRAW as DRAW_COLOR

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


MODEL_LABEL_SEP = " — "


def _model_dropdown(
    *, label: str, value: str, disabled: bool, window_width: int, hint_text: str | None = None
) -> ft.Control:
    """Editable dropdown: pick a known Ollama model (with tariff note) or type any name."""
    known = {key for key, _note in KNOWN_OLLAMA_MODELS}
    dropdown = ft.Dropdown(
        options=[
            ft.DropdownOption(key=key, text=f"{key}{MODEL_LABEL_SEP}{note}")
            for key, note in KNOWN_OLLAMA_MODELS
        ],
        value=value if value in known else None,
        text=None if value in known else value,
        editable=True,
        enable_filter=True,
        disabled=disabled,
        hint_text=hint_text,
        filled=True,
        fill_color=_FIELD_BG,
        bgcolor=_FIELD_BG,
        color=FG,
        border_color=ft.Colors.with_opacity(0.18, ft.Colors.WHITE),
        focused_border_color=ACCENT,
        text_size=scaled(14, window_width),
        border_radius=10,
        menu_height=360,
        expand=True,
        data={"typed": None},
    )

    def on_text_change(e: ft.ControlEvent) -> None:
        dropdown.data["typed"] = e.data if isinstance(e.data, str) else dropdown.text

    def on_select(_e: ft.ControlEvent) -> None:
        dropdown.data["typed"] = None

    dropdown.on_text_change = on_text_change
    dropdown.on_select = on_select
    return ft.Column(
        [ft.Text(label, size=scaled(12, window_width), color=MUTED), dropdown],
        spacing=6,
        tight=True,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        data=dropdown,
    )


def model_choice(dropdown: ft.Dropdown) -> str:
    """Model name from the editable dropdown: a typed name wins over the selected option."""
    state = dropdown.data if isinstance(dropdown.data, dict) else {}
    typed = (state.get("typed") or "").strip()
    if not typed and not dropdown.value:
        typed = (dropdown.text or "").strip()
    if typed:
        return typed.split(MODEL_LABEL_SEP)[0].strip()
    return (dropdown.value or "").strip()


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


def _parse_codes(raw: str) -> list[str]:
    seen: set[str] = set()
    codes: list[str] = []
    for part in raw.split(","):
        code = part.strip().upper()
        if code and code not in seen:
            seen.add(code)
            codes.append(code)
    return codes


HEADER_PREFIX = "__league__:"


def _picker_dropdown(*, hint: str, disabled: bool, window_width: int, on_select) -> ft.Dropdown:
    return ft.Dropdown(
        options=[],
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
        hint_text=hint,
        disabled=disabled,
        menu_height=360,
        on_select=on_select,
        expand=True,
    )


def _removable_chip(label: ft.Control, on_remove, *, window_width: int) -> ft.Control:
    return apply_motion(
        ft.Container(
            content=ft.Row(
                [
                    label,
                    ft.IconButton(
                        icon=ft.Icons.CLOSE,
                        icon_size=14,
                        tooltip="Убрать",
                        style=ft.ButtonStyle(padding=0),
                        on_click=lambda _e: on_remove(),
                    ),
                ],
                spacing=4,
                tight=True,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=SURFACE,
            padding=ft.Padding.only(left=10, right=2, top=2, bottom=2),
            border_radius=8,
        ),
        interactive=True,
    )


def league_options(infos: tuple[LeagueInfo, ...] | list[LeagueInfo]) -> list[ft.DropdownOption]:
    """All leagues with crest, name and upcoming-match note; idle leagues are disabled."""
    options: list[ft.DropdownOption] = []
    for info in infos:
        comp = info.competition
        options.append(
            ft.DropdownOption(
                key=comp.code,
                text=comp.name,
                disabled=info.disabled,
                content=ft.Row(
                    [
                        crest_image(comp.emblem, label=comp.name, size=20, code=comp.code),
                        ft.Text(comp.name, size=13, color=MUTED if info.disabled else FG),
                        ft.Text(info.note, size=11, color=MUTED),
                    ],
                    spacing=8,
                    tight=True,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            )
        )
    return options


def team_options(
    groups: tuple[tuple[Competition, tuple[Team, ...]], ...] | list,
    codes: list[str],
) -> list[ft.DropdownOption]:
    """Teams grouped under disabled league headers; only the chosen leagues when set."""
    grouped = group_teams_by_league(
        {comp.code: list(teams) for comp, teams in groups},
        [comp for comp, _teams in groups],
        codes if codes else (),
    )
    options: list[ft.DropdownOption] = []
    for comp, teams in grouped:
        options.append(
            ft.DropdownOption(
                key=f"{HEADER_PREFIX}{comp.code}",
                text=comp.name,
                disabled=True,
                content=ft.Row(
                    [
                        crest_image(comp.emblem, label=comp.name, size=16, code=comp.code),
                        ft.Text(comp.name, size=12, weight=ft.FontWeight.W_600, color=ACCENT),
                    ],
                    spacing=6,
                    tight=True,
                ),
            )
        )
        for team in teams:
            options.append(
                ft.DropdownOption(
                    key=str(team.id),
                    text=team.name,
                    content=ft.Row(
                        [
                            ft.Container(width=8),
                            crest_image(team.crest, label=team.name, size=18, team_id=team.id),
                            ft.Text(team.name, size=13, color=FG),
                        ],
                        spacing=6,
                        tight=True,
                    ),
                )
            )
    return options


def _favorites_block(
    form: SettingsForm,
    *,
    window_width: int,
    disabled: bool,
    on_refresh_counts: Callable[[], None] | None,
) -> tuple[ft.Control, Callable[[], str], Callable[[], str]]:
    """Favourite leagues combobox (crests, counts, idle leagues disabled) + teams by league."""
    leagues = _parse_codes(form.favorite_leagues)
    teams = _parse_team_ids(form.favorite_teams)
    infos = {info.code.upper(): info for info in form.league_infos}
    team_names = {str(team.id): team.name for team in form.team_choices}
    team_crests: dict[str, tuple[str | None, int]] = {}
    for _comp, members in form.teams_by_league:
        for team in members:
            team_names.setdefault(str(team.id), team.name)
            team_crests[str(team.id)] = (team.crest, team.id)
    league_chips = ft.Row([], wrap=True, spacing=8, run_spacing=8)
    team_chips = ft.Row([], wrap=True, spacing=8, run_spacing=8)

    def paint() -> None:
        chips: list[ft.Control] = []
        for code in leagues:
            info = infos.get(code)
            comp = info.competition if info else Competition(0, code, code)
            label = ft.Row(
                [
                    crest_image(comp.emblem, label=comp.name, size=16, code=comp.code),
                    ft.Text(comp.name, size=scaled(12, window_width), color=FG),
                ],
                spacing=6,
                tight=True,
            )
            chips.append(
                _removable_chip(label, lambda c=code: remove_league(c), window_width=window_width)
            )
        league_chips.controls = chips
        chips = []
        for team_id in teams:
            crest, numeric = team_crests.get(team_id, (None, int(team_id)))
            name = team_names.get(team_id, team_id)
            label = ft.Row(
                [
                    crest_image(crest, label=name, size=16, team_id=numeric),
                    ft.Text(name, size=scaled(12, window_width), color=FG),
                ],
                spacing=6,
                tight=True,
            )
            chips.append(
                _removable_chip(label, lambda t=team_id: remove_team(t), window_width=window_width)
            )
        team_chips.controls = chips
        team_dropdown.options = team_options(form.teams_by_league, leagues)
        if not team_dropdown.options and form.team_choices:
            team_dropdown.options = [
                ft.DropdownOption(key=str(team.id), text=team.name) for team in form.team_choices
            ]
        team_dropdown.disabled = disabled or not team_dropdown.options
        team_dropdown.hint_text = (
            "Выберите команду"
            if team_dropdown.options
            else "Команды появятся после загрузки календаря лиги"
        )
        for control in (league_chips, team_chips, team_dropdown):
            try:
                control.update()
            except Exception:  # noqa: BLE001 — first paint has no page
                pass

    def remove_league(code: str) -> None:
        if code in leagues:
            leagues.remove(code)
        paint()

    def remove_team(team_id: str) -> None:
        if team_id in teams:
            teams.remove(team_id)
        paint()

    def add_league(event: ft.ControlEvent | None = None) -> None:
        key = str(getattr(league_dropdown, "value", "") or "").upper()
        info = infos.get(key)
        if key and key not in leagues and (info is None or not info.disabled):
            leagues.append(key)
        league_dropdown.value = None
        paint()

    def add_team(event: ft.ControlEvent | None = None) -> None:
        key = str(getattr(team_dropdown, "value", "") or "")
        if key.isdigit() and key not in teams:
            teams.append(key)
        team_dropdown.value = None
        paint()

    league_dropdown = _picker_dropdown(
        hint="Выберите лигу",
        disabled=disabled or not form.league_infos,
        window_width=window_width,
        on_select=add_league,
    )
    league_dropdown.options = league_options(form.league_infos)
    team_dropdown = _picker_dropdown(
        hint="Выберите команду",
        disabled=disabled,
        window_width=window_width,
        on_select=add_team,
    )
    paint()
    refresh_row: list[ft.Control] = []
    if on_refresh_counts is not None:
        refresh_row.append(
            with_cursor(
                ft.TextButton(
                    "Обновить счётчики матчей",
                    icon=ft.Icons.REFRESH,
                    disabled=disabled or bool(form.counting),
                    on_click=lambda _e: on_refresh_counts(),
                ),
                interactive=True,
            )
        )
    if form.counting:
        refresh_row.append(ft.ProgressRing(width=14, height=14, stroke_width=2, color=ACCENT))
        refresh_row.append(ft.Text(form.counting, size=11, color=MUTED))
    caption = scaled(12, window_width)
    block = ft.Column(
        [
            ft.Text("Любимые лиги", size=caption, color=MUTED),
            ft.Text(
                "Серые лиги без матчей в ближайшие 6 месяцев выбрать нельзя.",
                size=11,
                color=MUTED,
            ),
            ft.Row([league_dropdown]),
            league_chips,
            ft.Row(refresh_row, spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Text("Любимые команды", size=caption, color=MUTED),
            ft.Row([team_dropdown]),
            team_chips,
        ],
        spacing=6,
        tight=True,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
    )
    return block, lambda: ",".join(leagues), lambda: ",".join(teams)


def _gate_banner(text: str) -> ft.Control:
    return ft.Container(
        content=ft.Row(
            [
                ft.Icon(ft.Icons.LOCK_OUTLINE, color=DRAW_COLOR, size=18),
                ft.Text(text, color=FG, size=13, expand=True),
            ],
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        bgcolor=ft.Colors.with_opacity(0.14, DRAW_COLOR),
        border=ft.Border.all(1, DRAW_COLOR),
        border_radius=10,
        padding=ft.Padding.symmetric(horizontal=12, vertical=10),
    )


SETTINGS_THREE_COLUMNS = 1500


def _section(title: str, controls: list[ft.Control]) -> ft.Control:
    return apply_motion(
        ft.Container(
            content=ft.Column(
                [
                    ft.Text(title, size=16, weight=ft.FontWeight.W_600, color=FG),
                    *controls,
                ],
                spacing=12,
                tight=True,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            ),
            bgcolor=CARD,
            border=glass_border(),
            border_radius=12,
            padding=14,
        )
    )


def settings_view(
    form: SettingsForm,
    *,
    on_save: Callable[[dict[str, str | bool]], None],
    on_test: Callable[[], None],
    on_clear_cache: Callable[[], None],
    window_width: int = 1440,
    training: ft.Control | None = None,
    on_refresh_counts: Callable[[], None] | None = None,
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
    ollama_key_wrap = _settings_field(
        label="OLLAMA_API_KEY · необязательный (для ollama.com)",
        value=form.ollama_api_key,
        disabled=saving,
        window_width=window_width,
        password=True,
        can_reveal_password=True,
    )
    host_wrap = _settings_field(
        label="OLLAMA_HOST",
        value=form.ollama_host,
        disabled=saving,
        window_width=window_width,
        hint_text=f"{OLLAMA_CLOUD_HOST} или http://127.0.0.1:11434",
    )
    model_wrap = _model_dropdown(
        label="OLLAMA_MODEL · выберите из списка или впишите своё",
        value=form.ollama_model,
        disabled=saving,
        window_width=window_width,
        hint_text=DEFAULT_OLLAMA_MODEL,
    )
    fallback_wrap = _model_dropdown(
        label="OLLAMA_FALLBACK_MODEL · запасная модель",
        value=form.ollama_fallback_model,
        disabled=saving,
        window_width=window_width,
        hint_text=DEFAULT_OLLAMA_FALLBACK_MODEL,
    )
    api_football_wrap = _settings_field(
        label="API_FOOTBALL_KEY · необязательный (травмы, карточки, составы)",
        value=form.api_football_key,
        disabled=saving,
        window_width=window_width,
        password=True,
        can_reveal_password=True,
    )
    gnews_wrap = _settings_field(
        label="GNEWS_API_KEY · необязательный (новости команд)",
        value=form.gnews_api_key,
        disabled=saving,
        window_width=window_width,
        password=True,
        can_reveal_password=True,
    )
    rss_sw = ft.Switch(
        label="Новости из RSS (BBC, Guardian, Sky, ESPN) без ключа",
        value=form.news_rss_enabled,
        active_color=ACCENT,
        disabled=saving,
        label_text_style=ft.TextStyle(color=FG, size=13),
    )
    favorites_wrap, leagues_value, teams_value = _favorites_block(
        form, window_width=window_width, disabled=saving, on_refresh_counts=on_refresh_counts
    )
    football_field = _field_value(football_wrap)
    ollama_key_field = _field_value(ollama_key_wrap)
    host_field = _field_value(host_wrap)
    model_field = _field_value(model_wrap)
    fallback_field = _field_value(fallback_wrap)
    api_football_field = _field_value(api_football_wrap)
    gnews_field = _field_value(gnews_wrap)
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
                "ollama_api_key": ollama_key_field.value or "",
                "ollama_host": host_field.value or OLLAMA_CLOUD_HOST,
                "ollama_model": model_choice(model_field) or DEFAULT_OLLAMA_MODEL,
                "ollama_fallback_model": (
                    model_choice(fallback_field) or DEFAULT_OLLAMA_FALLBACK_MODEL
                ),
                "api_football_key": api_football_field.value or "",
                "gnews_api_key": gnews_field.value or "",
                "news_rss_enabled": bool(rss_sw.value),
                "favorite_leagues": leagues_value(),
                "favorite_teams": teams_value(),
                "prefetch_wait_on_start": bool(prefetch_sw.value),
                "show_ai_block": bool(ai_sw.value),
                "compact_fixtures": bool(compact_sw.value),
                "system_notifications": bool(system_sw.value),
            }
        )

    buttons = ft.Row(
        [
            with_cursor(
                ft.FilledButton(
                    "Сохранить",
                    icon=ft.Icons.SAVE,
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
    )
    keys_card = _section(
        "Ключи и подключения",
        [
            football_wrap,
            ollama_key_wrap,
            host_wrap,
            model_wrap,
            fallback_wrap,
            api_football_wrap,
            gnews_wrap,
            _switch_row(rss_sw, window_width=window_width),
        ],
    )
    favorites_card = _section("Избранное", [favorites_wrap])
    interface_card = _section(
        "Запуск и интерфейс",
        [
            _switch_row(prefetch_sw, window_width=window_width),
            _switch_row(ai_sw, window_width=window_width),
            _switch_row(compact_sw, window_width=window_width),
            _switch_row(system_sw, window_width=window_width),
        ],
    )
    extra = [training] if training is not None else []
    aside = settings_aside(form.database_path, window_width=window_width)

    def column(items: list[ft.Control]) -> ft.Control:
        return ft.Container(
            content=ft.ListView(items, expand=True, spacing=16, padding=0),
            expand=True,
        )

    if window_width >= SETTINGS_THREE_COLUMNS:
        # Wide windows: keys | favourites + interface + training | notes. No empty half.
        layout: ft.Control = ft.Row(
            [
                column([keys_card]),
                column([favorites_card, interface_card, *extra]),
                aside,
            ],
            spacing=20,
            expand=True,
            vertical_alignment=ft.CrossAxisAlignment.STRETCH,
        )
    elif window_width >= BREAKPOINT_MEDIUM:
        layout = ft.Row(
            [
                column([keys_card, favorites_card, interface_card, *extra]),
                aside,
            ],
            spacing=20,
            expand=True,
            vertical_alignment=ft.CrossAxisAlignment.STRETCH,
        )
    else:
        layout = column([keys_card, favorites_card, interface_card, *extra, aside])
    # The action bar stays visible below the scrolling columns.
    action_bar = ft.Container(
        content=buttons,
        padding=ft.Padding.only(top=8),
        border=ft.Border.only(top=ft.BorderSide(1, ft.Colors.with_opacity(0.12, FG))),
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
                *([_gate_banner(form.gate_notice)] if form.gate_notice else []),
                layout,
                *banners,
                action_bar,
            ],
            spacing=16,
            expand=True,
        ),
        expand=True,
        bgcolor=PANE_BG,
    )
