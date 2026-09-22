from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import flet as ft

from football_prognoz.data.football_data_org import roster_from_api
from football_prognoz.data.store import SQLiteStore
from football_prognoz.domain.match import Match, MatchStatus, Score
from football_prognoz.domain.prediction import Scoreline
from football_prognoz.domain.team import Person, TeamRoster
from football_prognoz.ui.components.probability_bar import preliminary_score_card
from football_prognoz.ui.components.squad_card import person_age, person_status, squad_card
from football_prognoz.ui.components.venue import venue_badge


def _walk(control: object):
    yield control
    content = getattr(control, "content", None)
    if content is not None:
        yield from _walk(content)
    controls = getattr(control, "controls", None)
    if controls:
        for child in controls:
            yield from _walk(child)


def test_scoreline_winner_side() -> None:
    assert Scoreline(2, 1, 0.1, 1.8, 1.1).winner_side == "home"
    assert Scoreline(0, 2, 0.1, 0.9, 1.7).winner_side == "away"
    assert Scoreline(1, 1, 0.1, 1.2, 1.2).winner_side is None


def test_roster_roundtrip(tmp_path: Path, team_payload: dict) -> None:
    store = SQLiteStore(tmp_path / "roster.db")
    roster = roster_from_api(team_payload)
    store.upsert_roster(roster)
    loaded = store.get_roster(57)
    assert loaded is not None
    assert loaded.coach is not None
    assert loaded.coach.name == "Mikel Arteta"
    assert [player.name for player in loaded.squad] == [
        "David Raya",
        "William Saliba",
        "Martin Ødegaard",
        "Bukayo Saka",
    ]
    store.clear_all()
    assert store.get_roster(57) is None


def test_person_status_uses_role_nationality_age() -> None:
    player = Person(
        id=1,
        name="David Raya",
        position="Goalkeeper",
        nationality="Spain",
        date_of_birth="1995-09-15",
        shirt_number=1,
    )
    status = person_status(player, today=date(2026, 9, 21))
    assert "Вратарь" in status
    assert "№1" in status
    assert "Spain" not in status
    assert "31 лет" in status
    assert person_age("1995-09-15", today=date(2026, 9, 21)) == 31


def test_squad_card_lists_coach_and_marks_venues(team_payload: dict) -> None:
    home = roster_from_api(team_payload)
    away = TeamRoster(
        team_id=65,
        team_name="Manchester City FC",
        crest=None,
        coach=Person(id=9, name="Pep Guardiola", role="COACH", nationality="Spain"),
        squad=(),
    )
    view = squad_card(home, away, compact=True, home_elo=1600.0, away_elo=1580.0)
    blob = " ".join(
        str(getattr(node, "value", "") or "")
        for node in _walk(view)
        if isinstance(node, ft.Text)
    )
    assert "Состав и тренер" in blob
    assert "Mikel Arteta" in blob
    assert "Bukayo Saka" in blob
    assert "Pep Guardiola" in blob
    assert "Elo 1600" in blob
    assert "Заявка" in blob
    icons = [node.icon for node in _walk(view) if isinstance(node, ft.Icon)]
    assert ft.Icons.HOME in icons
    assert ft.Icons.DIRECTIONS_BUS in icons


def test_preliminary_score_underlines_winner_only() -> None:
    match = Match(
        id=1,
        competition_code="PL",
        utc_date=datetime(2026, 9, 26, 14, 0, tzinfo=UTC),
        status=MatchStatus.SCHEDULED,
        matchday=6,
        home_id=57,
        home_name="Arsenal",
        away_id=65,
        away_name="Man City",
        score=Score(None, None),
    )
    win = preliminary_score_card(Scoreline(2, 1, 0.18, 1.9, 1.1), match)
    draw = preliminary_score_card(Scoreline(1, 1, 0.14, 1.5, 1.5), match)
    win_home = [
        node.style
        for node in _walk(win)
        if isinstance(node, ft.Text) and node.value == "Arsenal"
    ]
    win_away = [
        node.style
        for node in _walk(win)
        if isinstance(node, ft.Text) and node.value == "Man City"
    ]
    draw_styles = [
        node.style
        for node in _walk(draw)
        if isinstance(node, ft.Text) and node.value in {"Arsenal", "Man City"}
    ]
    assert any(
        style is not None and style.decoration == ft.TextDecoration.UNDERLINE
        for style in win_home
    )
    assert not any(
        style is not None and style.decoration == ft.TextDecoration.UNDERLINE
        for style in win_away
    )
    assert not any(
        style is not None and style.decoration == ft.TextDecoration.UNDERLINE
        for style in draw_styles
    )


def test_venue_badge_tooltips() -> None:
    home = venue_badge("home")
    away = venue_badge("away")
    assert home.tooltip == "Дома"
    assert away.tooltip == "В гостях"
    assert home.icon == ft.Icons.HOME
    assert away.icon == ft.Icons.DIRECTIONS_BUS
