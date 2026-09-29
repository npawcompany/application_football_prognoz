"""Headless checks for Flet control trees (no Flutter client needed).

`serialize` runs the same diff + msgpack encoding Flet uses to send a tree to the
client, so unsupported values or failing `before_update` validation surface in tests.
`layout_problems` flags layouts that Flutter rejects at paint time (in release builds
the offending widget is painted as a grey box, i.e. the "grey screen").
"""

from __future__ import annotations

from collections.abc import Iterator

import flet as ft
import msgpack
from flet.controls.base_control import BaseControl
from flet.controls.object_patch import ObjectPatch
from flet.messaging.protocol import configure_encode_object_for_msgpack

_encode = configure_encode_object_for_msgpack(BaseControl)


def serialize(control: ft.Control) -> bytes:
    patch, _added, _removed = ObjectPatch.from_diff(None, control, control_cls=BaseControl)
    return msgpack.packb(patch.to_message(), default=_encode)


def children(control: object) -> Iterator[object]:
    for attr in ("content", "leading", "title", "subtitle", "trailing", "label"):
        value = getattr(control, attr, None)
        if isinstance(value, BaseControl):
            yield value
    for attr in ("controls", "options", "actions"):
        value = getattr(control, attr, None)
        if isinstance(value, list):
            yield from (item for item in value if isinstance(item, BaseControl))


def walk(control: object) -> Iterator[object]:
    yield control
    for child in children(control):
        yield from walk(child)


def layout_problems(control: object) -> list[str]:
    problems: list[str] = []
    for node in walk(control):
        if isinstance(node, ft.Row) and node.wrap:
            for child in node.controls:
                if getattr(child, "expand", None):
                    problems.append(f"expand child {type(child).__name__} inside Row(wrap=True)")
    return problems


def texts(control: object) -> list[str]:
    found: list[str] = []
    for node in walk(control):
        for attr in ("value", "text"):
            value = getattr(node, attr, None)
            if isinstance(value, str):
                found.append(value)
    return found
