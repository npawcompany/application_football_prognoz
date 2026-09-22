"""Club squad and coach from football-data.org Team resource."""

from __future__ import annotations

from datetime import UTC, date, datetime

import flet as ft

from football_prognoz.domain.match import MatchLineup
from football_prognoz.domain.team import Person, TeamRoster
from football_prognoz.ui.components.crest import crest_image
from football_prognoz.ui.components.flag import country_label
from football_prognoz.ui.components.team_label import team_label
from football_prognoz.ui.components.venue import venue_badge
from football_prognoz.ui.motion import apply_motion
from football_prognoz.ui.runtime import info_banner
from football_prognoz.ui.theme import ACCENT, CARD, MUTED, SURFACE, glass_border, scaled

_POSITION_ORDER = ("gk", "df", "mf", "fw", "other")
_POSITION_RU = {
    "gk": "Вратари",
    "df": "Защитники",
    "mf": "Полузащитники",
    "fw": "Нападающие",
    "other": "Прочие",
}
_ROLE_RU = {
    "gk": "Вратарь",
    "df": "Защитник",
    "mf": "Полузащитник",
    "fw": "Нападающий",
    "other": "Игрок",
}


def position_key(value: str | None) -> str:
    raw = (value or "").casefold()
    if "goal" in raw:
        return "gk"
    if "defen" in raw or raw in {"defence", "defense"}:
        return "df"
    if "mid" in raw:
        return "mf"
    if "attack" in raw or "offence" in raw or "offense" in raw or "forward" in raw:
        return "fw"
    return "other"


def person_age(dob: str | None, *, today: date | None = None) -> int | None:
    if not dob:
        return None
    try:
        born = date.fromisoformat(dob[:10])
    except ValueError:
        return None
    now = today or datetime.now(UTC).date()
    years = now.year - born.year - ((now.month, now.day) < (born.month, born.day))
    if years < 15 or years > 80:
        return None
    return years


def person_status(person: Person, *, today: date | None = None) -> str:
    bits: list[str] = []
    if person.role.upper() == "COACH":
        bits.append("Тренер")
    else:
        bits.append(_ROLE_RU[position_key(person.position)])
        if person.shirt_number:
            bits.append(f"№{person.shirt_number}")
    age = person_age(person.date_of_birth, today=today)
    if age is not None:
        bits.append(f"{age} лет")
    if person.contract_until:
        bits.append(f"до {person.contract_until[:10]}")
    return " · ".join(bits)


def _person_row(person: Person, *, window_width: int, emphasize: bool = False) -> ft.Control:
    trailing: list[ft.Control] = []
    if person.nationality:
        trailing.append(country_label(person.nationality, size=scaled(11, window_width)))
    status = person_status(person)
    if status:
        trailing.append(
            ft.Text(
                status,
                size=scaled(11, window_width),
                color=MUTED,
                max_lines=1,
                overflow=ft.TextOverflow.ELLIPSIS,
            )
        )
    return ft.Row(
        [
            team_label(
                person.name,
                size=scaled(13 if emphasize else 12, window_width),
                weight=ft.FontWeight.W_600 if emphasize else ft.FontWeight.NORMAL,
            ),
            *trailing,
        ],
        spacing=8,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )


def _group_players(players: list[Person], *, window_width: int) -> list[ft.Control]:
    grouped: dict[str, list[Person]] = {key: [] for key in _POSITION_ORDER}
    for player in players:
        grouped[position_key(player.position)].append(player)
    blocks: list[ft.Control] = []
    for key in _POSITION_ORDER:
        bucket = grouped[key]
        if not bucket:
            continue
        blocks.append(
            ft.Text(_POSITION_RU[key], size=scaled(11, window_width), color=MUTED)
        )
        blocks.extend(_person_row(player, window_width=window_width) for player in bucket)
    return blocks


def _section(title: str, players: list[Person], *, window_width: int) -> list[ft.Control]:
    if not players:
        return []
    return [
        ft.Text(title, size=scaled(12, window_width), color=ACCENT, weight=ft.FontWeight.W_600),
        *_group_players(players, window_width=window_width),
    ]


def _team_squad(
    roster: TeamRoster | None,
    side: str,
    *,
    window_width: int,
    elo: float | None = None,
    starters: tuple[int, ...] = (),
    bench: tuple[int, ...] = (),
) -> ft.Control:
    if roster is None or (roster.coach is None and not roster.squad):
        return info_banner(
            "Состав не загружен.",
            action_hint="Заявка клуба с football-data.org, без травм.",
        )
    header_bits: list[ft.Control] = [
        venue_badge(side, size=16),
        crest_image(roster.crest, label=roster.team_name, size=22, team_id=roster.team_id),
        team_label(roster.team_name, size=scaled(14, window_width)),
    ]
    if elo is not None:
        header_bits.append(
            ft.Text(
                f"Elo {elo:.0f}",
                size=scaled(12, window_width),
                color=ACCENT,
                weight=ft.FontWeight.W_600,
            )
        )
    if roster.country:
        header_bits.append(country_label(roster.country, size=scaled(11, window_width)))
    blocks: list[ft.Control] = [
        ft.Row(header_bits, spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER)
    ]
    if roster.coach is not None:
        blocks.append(
            ft.Container(
                content=_person_row(roster.coach, window_width=window_width, emphasize=True),
                bgcolor=SURFACE,
                padding=8,
                border_radius=8,
            )
        )
    start_set = set(starters)
    bench_set = set(bench)
    if start_set or bench_set:
        xi = [player for player in roster.squad if player.id in start_set]
        sub = [player for player in roster.squad if player.id in bench_set]
        rest = [
            player
            for player in roster.squad
            if player.id not in start_set and player.id not in bench_set
        ]
        blocks.extend(_section("Основа", xi, window_width=window_width))
        blocks.extend(_section("Запас", sub, window_width=window_width))
        blocks.extend(_section("Заявка", rest, window_width=window_width))
        if not xi and not sub:
            blocks.append(
                ft.Text(
                    "Основа ещё не объявлена.",
                    size=scaled(11, window_width),
                    color=MUTED,
                )
            )
    else:
        blocks.append(
            ft.Text(
                "Заявка",
                size=scaled(12, window_width),
                color=ACCENT,
                weight=ft.FontWeight.W_600,
            )
        )
        blocks.extend(_group_players(list(roster.squad), window_width=window_width))
    return ft.Column(
        blocks,
        spacing=6,
        tight=True,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
    )


def squad_card(
    home: TeamRoster | None,
    away: TeamRoster | None,
    *,
    compact: bool = False,
    window_width: int = 1440,
    home_elo: float | None = None,
    away_elo: float | None = None,
    lineup: MatchLineup | None = None,
) -> ft.Control:
    home_block = _team_squad(
        home,
        "home",
        window_width=window_width,
        elo=home_elo,
        starters=lineup.home_start if lineup else (),
        bench=lineup.home_bench if lineup else (),
    )
    away_block = _team_squad(
        away,
        "away",
        window_width=window_width,
        elo=away_elo,
        starters=lineup.away_start if lineup else (),
        bench=lineup.away_bench if lineup else (),
    )
    if compact:
        body: ft.Control = ft.Column([home_block, away_block], spacing=14, tight=True)
    else:
        body = ft.Row(
            [
                ft.Container(content=home_block, expand=True),
                ft.Container(content=away_block, expand=True),
            ],
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )
    return apply_motion(
        ft.Container(
            content=ft.Column(
                [
                    ft.Text("Состав и тренер", size=scaled(13, window_width), color=MUTED),
                    body,
                ],
                spacing=10,
                tight=True,
            ),
            bgcolor=CARD,
            border=glass_border(),
            border_radius=12,
            padding=12,
        )
    )
