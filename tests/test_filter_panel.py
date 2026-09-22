from __future__ import annotations

import flet as ft

from football_prognoz.ui.components.filter_panel import filter_panel
from football_prognoz.ui.components.pager import pager


def _walk(control: object):
    yield control
    content = getattr(control, "content", None)
    if content is not None:
        yield from _walk(content)
    controls = getattr(control, "controls", None)
    if controls:
        for child in controls:
            yield from _walk(child)


def _blob(control: object) -> str:
    parts = [str(control)]
    for node in _walk(control):
        for attr in ("value", "label", "hint_text", "text"):
            val = getattr(node, attr, None)
            if isinstance(val, str):
                parts.append(val)
        content = getattr(node, "content", None)
        if isinstance(content, str):
            parts.append(content)
    return " ".join(parts)


def _panel(**overrides: object) -> ft.Control:
    kwargs: dict[str, object] = {
        "team_query": "",
        "on_team_query": lambda _v: None,
        "status": "upcoming",
        "on_status": lambda _v: None,
        "date_window": "any",
        "on_date_window": lambda _v: None,
        "matchday": "",
        "on_matchday": lambda _v: None,
        "sort": "date_asc",
        "on_sort": lambda _v: None,
        "on_reset": lambda: None,
    }
    kwargs.update(overrides)
    return filter_panel(**kwargs)  # type: ignore[arg-type]


def test_filter_panel_blob_contains_russian_labels() -> None:
    blob = _blob(_panel())
    assert "Команда" in blob
    assert "Живые" in blob
    assert "Сбросить" in blob


def test_live_chip_calls_on_status() -> None:
    seen: list[str] = []
    panel = _panel(on_status=seen.append)
    live = next(
        node
        for node in _walk(panel)
        if isinstance(node, ft.Container)
        and isinstance(node.content, ft.Text)
        and node.content.value == "Живые"
    )
    live.on_click(None)
    assert seen == ["live"]


def test_pager_caption_range_and_empty() -> None:
    control = pager(page=0, page_count=13, total=312, page_size=25, on_page=lambda _p: None)
    assert "1–25 из 312" in _blob(control)
    empty = pager(page=0, page_count=1, total=0, page_size=25, on_page=lambda _p: None)
    assert "Нет матчей" in _blob(empty)
    assert "Назад" in _blob(control)
    assert "Вперёд" in _blob(control)
