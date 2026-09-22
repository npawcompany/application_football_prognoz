from __future__ import annotations

import threading

import flet as ft

from football_prognoz.domain.prediction import Probabilities
from football_prognoz.ui.components.probability_bar import probability_bar
from football_prognoz.ui.motion import play_after


def _walk(control: object):
    yield control
    content = getattr(control, "content", None)
    if content is not None:
        yield from _walk(content)
    controls = getattr(control, "controls", None)
    if controls:
        for child in controls:
            yield from _walk(child)


def test_play_after_runs_callback() -> None:
    done = threading.Event()
    play_after(0.01, done.set)
    assert done.wait(timeout=1)


def test_probability_tiles_fill_width_matches_percent() -> None:
    view = probability_bar(Probabilities(0.75, 0.13, 0.12), compact=True)
    fills = [
        node
        for node in _walk(view)
        if isinstance(node, ft.Container)
        and isinstance(node.data, dict)
        and "fill" in node.data
    ]
    assert [round(node.data["fill"], 2) for node in fills] == [0.75, 0.13, 0.12]
    bars = [node for node in _walk(view) if isinstance(node, ft.ProgressBar)]
    assert len(bars) == 3
    assert [round(float(node.value), 2) for node in bars] == [0.75, 0.13, 0.12]
    weights = [
        tuple(child.expand for child in node.controls)
        for node in _walk(view)
        if isinstance(node, ft.Row) and node.spacing == 0 and len(node.controls) == 2
    ]
    assert (75, 25) in weights
    assert (13, 87) in weights
    assert (12, 88) in weights
