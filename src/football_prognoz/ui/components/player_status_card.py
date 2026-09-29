"""'Состав и доступность' card: API-Football absences, red cards, transfers, lineups."""

from __future__ import annotations

import flet as ft

from football_prognoz.domain.player_status import PlayerStatusReport, TeamStatus
from football_prognoz.ui.motion import apply_motion
from football_prognoz.ui.theme import CARD, FG, MUTED, glass_border, scaled


def _line(label: str, value: str, width: int) -> ft.Control:
    return ft.Column(
        [
            ft.Text(label, size=scaled(11, width), color=MUTED),
            ft.Text(value, size=scaled(12, width), color=FG),
        ],
        spacing=2,
        tight=True,
    )


def _absence_text(status: TeamStatus) -> str:
    parts = []
    for item in status.absences:
        state = "не сыграет" if item.is_certain else "под вопросом"
        extra = ", ключевой" if item.key_player else ""
        back = f", до {item.expected_return}" if item.expected_return else ""
        parts.append(f"{item.player_name} ({item.reason}, {state}{extra}{back})")
    return "; ".join(parts)


def _team_block(status: TeamStatus, title: str, width: int) -> ft.Control:
    rows: list[ft.Control] = [
        ft.Text(
            f"{title} · {status.team_name}",
            size=scaled(13, width),
            weight=ft.FontWeight.W_600,
            color=FG,
        )
    ]
    if status.absences:
        rows.append(_line("Отсутствуют", _absence_text(status), width))
    else:
        rows.append(_line("Отсутствуют", "нет данных о потерях", width))
    if status.red_cards:
        reds = "; ".join(
            f"{card.player_name} ({card.detail}, {card.fixture_date})" for card in status.red_cards
        )
        rows.append(_line("Красные карточки в последних матчах", reds, width))
    if status.lineup is not None and status.lineup.start_xi:
        names = ", ".join(p.name for p in status.lineup.start_xi)
        formation = status.lineup.formation or "схема не указана"
        rows.append(_line(f"Стартовый состав ({formation})", names, width))
    if status.top_ratings:
        best = ", ".join(f"{r.player_name} {r.rating:.1f}" for r in status.top_ratings)
        rows.append(_line("Лучшие рейтинги прошлого матча", best, width))
    if status.transfers:
        moves = "; ".join(
            f"{'+' if t.direction == 'in' else '−'} {t.player_name} "
            f"({'из' if t.direction == 'in' else 'в'} {t.other_team}, {t.date})"
            for t in status.transfers
        )
        rows.append(_line("Трансферы за 90 дней", moves, width))
    return ft.Column(rows, spacing=6, tight=True)


def player_status_card(report: PlayerStatusReport, *, window_width: int) -> ft.Control:
    body: list[ft.Control] = [
        ft.Text("Состав и доступность", size=scaled(13, window_width), color=MUTED),
    ]
    if report.has_data():
        body.append(_team_block(report.home, "Хозяева", window_width))
        body.append(_team_block(report.away, "Гости", window_width))
    for note in report.notes:
        body.append(ft.Text(note, size=scaled(11, window_width), color=MUTED))
    body.append(
        ft.Text(
            "Источник: API-Football. Данные о составах не влияют на вероятности 1X2.",
            size=scaled(11, window_width),
            color=MUTED,
        )
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
