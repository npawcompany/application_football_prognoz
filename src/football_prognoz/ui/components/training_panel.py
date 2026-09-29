"""'Данные для обучения' card: background forecast-history collection with progress."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import flet as ft

from football_prognoz.ui.motion import apply_motion, with_cursor
from football_prognoz.ui.theme import ACCENT, CARD, FG, MUTED, glass_border, scaled


@dataclass(frozen=True)
class TrainingState:
    running: bool = False
    cancelling: bool = False
    done: int = 0
    total: int = 0
    message: str | None = None
    codes: tuple[str, ...] = ()
    result: str | None = None
    error: str | None = None
    errors: tuple[str, ...] = field(default_factory=tuple)
    stats: tuple[str, ...] = ()  # short quality lines (filled when history exists)
    export_path: str | None = None

    @property
    def fraction(self) -> float | None:
        if not self.running or self.total <= 0:
            return None
        return min(1.0, self.done / self.total)


def training_panel(
    state: TrainingState,
    *,
    on_collect: Callable[[], None],
    on_cancel: Callable[[], None],
    on_export: Callable[[], None] | None = None,
    window_width: int = 1440,
) -> ft.Control:
    size = scaled(12, window_width)
    body: list[ft.Control] = [
        ft.Text(
            "Данные для обучения",
            size=scaled(16, window_width),
            weight=ft.FontWeight.W_600,
            color=FG,
        ),
        ft.Text(
            "Сохраняет в SQLite прогноз каждого матча за ±14 дней в выбранных лигах "
            "(любимые лиги или открытая лига): 1X2, счёт, факты, источники, версия модели. "
            "Повторный запуск обновляет записи без дублей и проставляет реальные счета. "
            "Прогноз, сделанный до матча, после начала не перезаписывается.",
            size=size,
            color=MUTED,
        ),
    ]
    if state.codes:
        body.append(ft.Text(f"Лиги: {', '.join(state.codes)}", size=size, color=FG))
    buttons: list[ft.Control] = [
        with_cursor(
            ft.FilledButton(
                "Собрать данные для обучения",
                bgcolor=ACCENT,
                color="#0F172A",
                disabled=state.running,
                on_click=lambda _e: on_collect(),
            ),
            interactive=True,
        )
    ]
    if state.running:
        buttons.append(
            with_cursor(
                ft.OutlinedButton(
                    "Отменяем…" if state.cancelling else "Отменить",
                    disabled=state.cancelling,
                    on_click=lambda _e: on_cancel(),
                ),
                interactive=True,
            )
        )
    if on_export is not None:
        buttons.append(
            with_cursor(
                ft.OutlinedButton(
                    "Экспорт в CSV (ВКР §3.3)",
                    disabled=state.running,
                    on_click=lambda _e: on_export(),
                ),
                interactive=True,
            )
        )
    body.append(ft.Row(buttons, wrap=True, spacing=8, run_spacing=8))
    if state.running:
        body.append(ft.ProgressBar(value=state.fraction, color=ACCENT))
        progress = f"{state.done} / {state.total}" if state.total else "подготовка"
        body.append(
            ft.Text(
                f"{progress} · {state.message or ''}".strip(" ·"),
                size=size,
                color=MUTED,
            )
        )
    if state.result:
        body.append(ft.Text(state.result, size=size, color=FG))
    if state.error:
        body.append(ft.Text(state.error, size=size, color="#F87171"))
    for line in state.errors[:5]:
        body.append(ft.Text(f"• {line}", size=scaled(11, window_width), color=MUTED))
    for line in state.stats:
        body.append(ft.Text(line, size=size, color=FG))
    if state.export_path:
        body.append(
            ft.Text(f"CSV сохранён: {state.export_path}", size=size, color=FG, selectable=True)
        )
    return apply_motion(
        ft.Container(
            content=ft.Column(body, spacing=10, tight=True),
            bgcolor=CARD,
            border=glass_border(),
            border_radius=12,
            padding=12,
        )
    )
