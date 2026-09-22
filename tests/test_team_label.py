from __future__ import annotations

from datetime import UTC, datetime

import flet as ft

from football_prognoz.domain.match import Match, MatchStatus, Score
from football_prognoz.domain.prediction import Scoreline
from football_prognoz.domain.team import Competition
from football_prognoz.ui.components.fact_card import fact_card
from football_prognoz.ui.components.filter_bar import filter_bar
from football_prognoz.ui.components.form_pills import form_pills
from football_prognoz.ui.components.league_card import league_card
from football_prognoz.ui.components.match_card import match_card
from football_prognoz.ui.components.probability_bar import preliminary_score_card
from football_prognoz.ui.components.section_header import section_header
from football_prognoz.ui.components.team_label import team_label
from football_prognoz.ui.theme import ACCENT, CARD, MUTED


def _walk(control: object):
    yield control
    content = getattr(control, "content", None)
    if content is not None:
        yield from _walk(content)
    controls = getattr(control, "controls", None)
    if controls:
        for child in controls:
            yield from _walk(child)


def _texts_with_ellipsis(control: object) -> list[ft.Text]:
    found: list[ft.Text] = []
    for node in _walk(control):
        if isinstance(node, ft.Text) and node.overflow == ft.TextOverflow.ELLIPSIS:
            found.append(node)
    return found


def _match() -> Match:
    return Match(
        id=1,
        competition_code="PL",
        utc_date=datetime(2026, 9, 26, 14, 0, tzinfo=UTC),
        status=MatchStatus.SCHEDULED,
        matchday=6,
        home_id=57,
        home_name="Borussia Mönchengladbach",
        away_id=65,
        away_name="Olympique Gymnaste Club de Nice",
        score=Score(None, None),
    )


def test_team_label_ellipsis_tooltip_and_expand() -> None:
    label = team_label("Borussia Mönchengladbach")
    assert label.value == "Borussia Mönchengladbach"
    assert label.max_lines == 1
    assert label.overflow == ft.TextOverflow.ELLIPSIS
    assert label.expand is True
    assert label.tooltip == "Borussia Mönchengladbach"
    assert label.size == 13
    assert label.weight == ft.FontWeight.W_600


def test_match_and_league_cards_ellipsis_long_names() -> None:
    match = _match()
    full = match_card(match, lambda _m: None)
    icons = [node.icon for node in _walk(full) if isinstance(node, ft.Icon)]
    assert ft.Icons.HOME in icons
    assert ft.Icons.DIRECTIONS_BUS in icons
    compact = match_card(match, lambda _m: None, compact=True)
    narrow = match_card(match, lambda _m: None, narrow=True)
    compact_narrow = match_card(match, lambda _m: None, compact=True, narrow=True)
    assert full.height is None
    assert compact.height is None
    assert narrow.height is None
    assert compact_narrow.height is None
    assert isinstance(full.content, ft.Row)
    assert isinstance(narrow.content, ft.Column)
    assert isinstance(compact_narrow.content, ft.Column)
    full_names = {node.value for node in _texts_with_ellipsis(full)}
    compact_names = {node.value for node in _texts_with_ellipsis(compact)}
    narrow_names = {node.value for node in _texts_with_ellipsis(narrow)}
    assert "Borussia Mönchengladbach" in full_names
    assert "Olympique Gymnaste Club de Nice" in full_names
    assert "Borussia Mönchengladbach" in compact_names
    assert "Borussia Mönchengladbach" in narrow_names
    assert "Olympique Gymnaste Club de Nice" in narrow_names
    for node in _texts_with_ellipsis(full):
        if node.value in {match.home_name, match.away_name}:
            assert node.tooltip == node.value
            assert node.expand is True
            assert node.max_lines == 1
    for node in _texts_with_ellipsis(narrow):
        if node.value in {match.home_name, match.away_name}:
            assert node.expand is True
            assert node.max_lines == 1
            assert node.overflow == ft.TextOverflow.ELLIPSIS

    league = league_card(
        Competition(2013, "BSA", "Campeonato Brasileiro Série A"),
        lambda _item: None,
    )
    assert league.tooltip == "Campeonato Brasileiro Série A"
    names = [node.value for node in _texts_with_ellipsis(league)]
    assert "Campeonato Brasileiro Série A" in names
    assert isinstance(league.content, ft.Row)
    assert league.content.expand is True
    name_column = next(
        node for node in _walk(league) if isinstance(node, ft.Column) and node.expand is True
    )
    assert any(isinstance(node, ft.Row) and node.expand is True for node in name_column.controls)


def test_goal_meter_uses_ellipsis_for_club_names() -> None:
    card = preliminary_score_card(
        Scoreline(1, 1, 0.14, 1.5, 1.5),
        _match(),
    )
    names = {node.value: node for node in _texts_with_ellipsis(card)}
    assert "Borussia Mönchengladbach" in names
    assert "Olympique Gymnaste Club de Nice" in names
    home = names["Borussia Mönchengladbach"]
    assert home.max_lines == 1
    assert home.expand is True
    assert home.tooltip == "Borussia Mönchengladbach"


def test_form_pills_colors_and_empty_dash() -> None:
    empty = form_pills("")
    dash = form_pills("—")
    assert isinstance(empty, ft.Text)
    assert empty.value == "—"
    assert empty.color == MUTED
    assert dash.value == "—"

    row = form_pills("WDL")
    assert isinstance(row, ft.Row)
    assert [chip.bgcolor for chip in row.controls] == ["#22C55E", "#F59E0B", "#EF4444"]
    assert [chip.width for chip in row.controls] == [22, 22, 22]
    assert row.controls[0].content.color == "#0F172A"


def test_filter_bar_reads_control_value_and_selected_chip() -> None:
    seen: list[str] = []
    clicks: list[str] = []
    bar = filter_bar(
        hint="Команда",
        value="",
        on_change=seen.append,
        chips=[
            ("Предстоящие", True, lambda: clicks.append("upcoming")),
            ("Все", False, lambda: clicks.append("all")),
        ],
    )
    field = next(node for node in _walk(bar) if isinstance(node, ft.TextField))
    assert field.label == "Команда"
    assert field.hint_text == "Команда"
    assert field.dense is True
    event = type("Event", (), {"control": type("Ctl", (), {"value": "Арсенал"})()})()
    field.on_change(event)
    assert seen == ["Арсенал"]
    none_event = type("Event", (), {"control": type("Ctl", (), {"value": None})()})()
    field.on_change(none_event)
    assert seen[-1] == ""

    chips = [
        node
        for node in _walk(bar)
        if isinstance(node, ft.Container) and isinstance(node.content, ft.Text)
    ]
    selected = next(chip for chip in chips if chip.content.value == "Предстоящие")
    other = next(chip for chip in chips if chip.content.value == "Все")
    assert selected.bgcolor == ACCENT
    assert other.bgcolor != ACCENT
    other.on_click(None)
    assert clicks == ["all"]


def test_section_header_and_fact_card_layout() -> None:
    header = section_header("Лиги", "12 соревнований.", trailing=ft.Text("×"))
    texts = [node.value for node in _walk(header) if isinstance(node, ft.Text)]
    assert "Лиги" in texts
    assert "12 соревнований." in texts
    title = next(
        node for node in _walk(header) if isinstance(node, ft.Text) and node.value == "Лиги"
    )
    assert title.overflow == ft.TextOverflow.ELLIPSIS
    assert title.max_lines == 1

    card = fact_card("Форма", ft.Text("WWDLW"))
    assert card.bgcolor == CARD
    assert card.padding == 12
    assert card.expand is False
    assert card.height is None
    tall = fact_card("Форма", ft.Text("WWDLW"), height=128)
    assert tall.height == 128
    assert any(isinstance(node, ft.Text) and node.value == "Форма" for node in _walk(card))
