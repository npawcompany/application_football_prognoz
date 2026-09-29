"""Colour audit: text reaches WCAG AA on every surface; the gradient covers the whole window."""

from __future__ import annotations

from pathlib import Path

import flet as ft
import pytest

from football_prognoz.config import ASSETS_DIR
from football_prognoz.ui import theme


@pytest.mark.parametrize("text_name", sorted(theme.TEXT_COLORS))
@pytest.mark.parametrize("surface_name", sorted(theme.CARD_SURFACES))
def test_text_colours_reach_aa_on_cards(text_name: str, surface_name: str) -> None:
    ratio = theme.contrast_ratio(theme.TEXT_COLORS[text_name], theme.CARD_SURFACES[surface_name])
    assert ratio >= 4.5, f"{text_name} on {surface_name}: {ratio:.2f}"


@pytest.mark.parametrize("text_name", theme.BACKGROUND_TEXT)
@pytest.mark.parametrize("surface_name", sorted(theme.BACKGROUND_SURFACES))
def test_text_on_the_bare_gradient_reaches_aa(text_name: str, surface_name: str) -> None:
    color = theme.TEXT_COLORS[text_name]
    ratio = theme.contrast_ratio(color, theme.BACKGROUND_SURFACES[surface_name])
    assert ratio >= 4.5, f"{text_name} on {surface_name}: {ratio:.2f}"


def test_filled_controls_keep_readable_text() -> None:
    assert theme.contrast_ratio(theme.ON_ACCENT, theme.ACCENT) >= 4.5  # chips, buttons
    assert theme.contrast_ratio(theme.ON_ACCENT, theme.DRAW) >= 4.5  # form pill D
    assert theme.contrast_ratio(theme.ON_ACCENT, theme.AWAY) >= 4.5  # form pill L
    assert theme.contrast_ratio(theme.FG, theme.ERROR_BG) >= 4.5  # error banner / toast
    assert theme.contrast_ratio(theme.BORDER, theme.CARD) >= 3.0  # input outline (1.4.11)


def test_contrast_ratio_reference_values() -> None:
    assert theme.contrast_ratio("#FFFFFF", "#000000") == pytest.approx(21.0)
    assert theme.contrast_ratio("#777777", "#777777") == pytest.approx(1.0)


def test_background_is_gradient_with_pattern_on_root_view() -> None:
    class _View:
        decoration = None

    class _Page:
        bgcolor = None
        views = [_View()]

    page = _Page()
    theme.apply_background(page)  # type: ignore[arg-type]
    decoration = page.views[0].decoration
    assert isinstance(decoration, ft.BoxDecoration)
    assert list(decoration.gradient.colors) == list(theme.BG_GRADIENT)
    assert decoration.image.src == theme.BG_PATTERN
    assert page.bgcolor == ft.Colors.TRANSPARENT


def test_background_falls_back_to_solid_colour_without_views() -> None:
    class _Page:
        bgcolor = None

    page = _Page()
    theme.apply_background(page)  # type: ignore[arg-type]
    assert page.bgcolor == theme.BG


def test_generated_assets_exist() -> None:
    for name in ("icon.png", "icon_macos.png", "icon_android.png", "splash.png", theme.BG_PATTERN):
        path = Path(ASSETS_DIR) / name
        assert path.is_file(), name
        assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    header = (Path(ASSETS_DIR) / "icon.png").read_bytes()[16:24]
    assert int.from_bytes(header[:4], "big") == 1024 and int.from_bytes(header[4:], "big") == 1024
