"""Settings screen follows the mockup: title, form column, aside card."""

from __future__ import annotations

import flet as ft

from football_prognoz.domain.team import Team
from football_prognoz.ui.components.settings_panel import SettingsForm
from football_prognoz.ui.theme import BREAKPOINT_MEDIUM
from football_prognoz.ui.views.settings import settings_view


def _walk(control: object):
    yield control
    content = getattr(control, "content", None)
    if content is not None:
        yield from _walk(content)
    controls = getattr(control, "controls", None)
    if controls:
        for child in controls:
            yield from _walk(child)
    options = getattr(control, "options", None)
    if options:
        for child in options:
            yield from _walk(child)


def _texts(control: object) -> list[str]:
    found: list[str] = []
    for node in _walk(control):
        for attr in ("value", "text", "label", "hint_text"):
            value = getattr(node, attr, None)
            if isinstance(value, str):
                found.append(value)
    return found


def _blob(control: object) -> str:
    return " ".join(_texts(control))


def _build(window_width: int = 1440) -> ft.Control:
    return settings_view(
        SettingsForm(),
        on_save=lambda _payload: None,
        on_test=lambda: None,
        on_clear_cache=lambda: None,
        window_width=window_width,
    )


def _column(view: object) -> ft.Column:
    if isinstance(view, ft.Container) and isinstance(view.content, ft.Column):
        return view.content
    assert isinstance(view, ft.Column)
    return view


def _aside(view: object) -> ft.Container:
    for node in _walk(view):
        if not isinstance(node, ft.Container):
            continue
        content = node.content
        if not isinstance(content, ft.Column) or not content.controls:
            continue
        first = content.controls[0]
        if isinstance(first, ft.Text) and first.value == "Локальное хранение ключей":
            return node
    raise AssertionError("settings aside not found")


def test_settings_view_blob_keeps_core_copy() -> None:
    view = _build()
    blob = _blob(view)
    assert "Настройки" in blob
    assert "Любимые лиги" in blob
    assert "Любимые команды" in blob
    assert "Разрешить системные уведомления" in blob
    assert "Локальное хранение ключей" in blob
    kinds = [type(node).__name__ for node in _walk(view)]
    assert "FilledButton" in kinds
    assert "Dropdown" in kinds
    assert kinds.count("OutlinedButton") >= 2


def test_aside_width_wide_is_360() -> None:
    aside = _aside(_build(1440))
    assert aside.width == 360


def test_aside_width_narrow_is_absent() -> None:
    aside = _aside(_build(800))
    assert aside.width in (None, 0)


def test_wide_layout_is_row_with_aside() -> None:
    view = _column(_build(BREAKPOINT_MEDIUM))
    assert isinstance(view, ft.Column)
    layout = view.controls[1]
    assert isinstance(layout, ft.Row)
    assert _aside(view) in list(_walk(layout))


def test_narrow_layout_is_column_form_then_aside() -> None:
    root = _column(_build(BREAKPOINT_MEDIUM - 1))
    layout = root.controls[1]
    assert isinstance(layout, ft.Column)
    assert layout.controls[1] is _aside(root)


def test_labels_are_separate_from_fields() -> None:
    view = _build()
    labels = [
        node.value
        for node in _walk(view)
        if isinstance(node, ft.Text) and node.value and "FOOTBALL_DATA_API_KEY" in node.value
    ]
    assert labels
    fields = [node for node in _walk(view) if isinstance(node, ft.TextField)]
    assert fields
    assert fields[0].label in (None, "")


def test_favorite_teams_combobox_lists_cached_clubs() -> None:
    view = settings_view(
        SettingsForm(
            favorite_teams="57",
            team_choices=(
                Team(id=57, name="Arsenal"),
                Team(id=64, name="Liverpool"),
            ),
        ),
        on_save=lambda _payload: None,
        on_test=lambda: None,
        on_clear_cache=lambda: None,
    )
    blob = _blob(view)
    assert "Arsenal" in blob
    assert "Liverpool" in blob
    assert any(type(node).__name__ == "Dropdown" for node in _walk(view))
