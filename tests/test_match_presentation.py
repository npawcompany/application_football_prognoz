from __future__ import annotations

from datetime import UTC, datetime

import flet as ft

from football_prognoz.data.football_data_org import lineup_from_api, parse_city
from football_prognoz.domain.country import competition_country, flag_code
from football_prognoz.domain.match import Match, MatchStatus, Score
from football_prognoz.domain.prediction import Scoreline
from football_prognoz.ui.components.flag import country_label, flag_asset
from football_prognoz.ui.components.h2h_table import h2h_table
from football_prognoz.ui.components.probability_bar import preliminary_score_card


def _walk(control: object):
    yield control
    content = getattr(control, "content", None)
    if content is not None:
        yield from _walk(content)
    controls = getattr(control, "controls", None)
    if controls:
        for child in controls:
            yield from _walk(child)


def test_flag_code_home_nations_and_iso3() -> None:
    assert flag_code("England") == "gb-eng"
    assert flag_code("Spain") == "es"
    assert flag_code(None, iso3="DEU") == "de"
    assert flag_code("Côte d'Ivoire") == "ci"
    assert flag_code("Europe") == "eu"
    assert flag_asset("gb-eng") == "/flags/gb-eng.svg"
    assert flag_asset("es") == "/flags/es.svg"
    assert competition_country("PL") == "England"
    assert competition_country("CL") == "Europe"


def _images(control) -> list:
    found = []

    def walk(node) -> None:
        if node is None:
            return
        if isinstance(node, ft.Image):
            found.append(node)
            walk(getattr(node, "error_content", None))
            return
        if isinstance(node, ft.Icon):
            found.append(node)
            return
        for attr in ("content", "controls"):
            value = getattr(node, attr, None)
            if isinstance(value, list):
                for child in value:
                    walk(child)
            elif isinstance(value, ft.Control):
                walk(value)

    walk(control)
    return found


def test_country_label_puts_flag_before_name() -> None:
    row = country_label("England")
    assert isinstance(row, ft.Row)
    assert [getattr(m, "src", None) for m in _images(row.controls[0])] == ["/flags/gb-eng.svg"]
    assert any(isinstance(child, ft.Text) and child.value == "England" for child in row.controls)


def test_resolve_flag_every_area_gets_a_mark() -> None:
    from football_prognoz.domain.country import resolve_flag

    url = "https://crests.football-data.org/770.svg"
    england = resolve_flag("England", iso3="ENG", flag_url=url)
    assert (england.url, england.asset, england.icon) == (url, "gb-eng", None)
    world = resolve_flag("World", iso3="INT")
    assert (world.url, world.asset, world.icon) == (None, None, "globe")
    assert resolve_flag("South America").icon == "globe"
    europe = resolve_flag("Europe", iso3="EUR", flag_url="https://crests.football-data.org/EUR.svg")
    assert europe.asset == "eu" and europe.url and europe.icon is None
    assert resolve_flag(None, iso3="EUR").asset == "eu"
    assert resolve_flag("Atlantis").icon == "flag"
    assert resolve_flag("Brazil", flag_url="javascript:x").url is None
    assert resolve_flag(None).empty


def test_flag_mark_uses_url_with_bundled_fallback_and_globe_for_world() -> None:
    from football_prognoz.ui.components.flag import flag_mark

    url = "https://crests.football-data.org/770.svg"
    marks = _images(flag_mark("England", flag_url=url))
    assert marks[0].src == url
    assert marks[1].src == "/flags/gb-eng.svg"  # offline / error fallback
    world = _images(flag_mark("World"))
    assert isinstance(world[0], ft.Icon) and world[0].icon == ft.Icons.PUBLIC
    europe = _images(flag_mark("Europe"))
    assert europe[0].src == "/flags/eu.svg"


def test_parse_city_from_address() -> None:
    assert parse_city("75 Drayton Park London N5 1BU") == "London"
    assert parse_city(None) is None


def test_lineup_from_api_reads_start_and_bench() -> None:
    payload = {
        "homeTeam": {
            "lineup": [{"id": 1, "name": "A"}, {"id": 2, "name": "B"}],
            "bench": [{"id": 3, "name": "C"}],
        },
        "awayTeam": {"lineup": [{"id": 9, "name": "D"}], "bench": []},
    }
    lineup = lineup_from_api(payload)
    assert lineup.home_start == (1, 2)
    assert lineup.home_bench == (3,)
    assert lineup.away_start == (9,)
    assert lineup.away_bench == ()


def test_h2h_table_shows_score_not_names() -> None:
    match = Match(
        id=10,
        competition_code="PL",
        utc_date=datetime(2024, 8, 24, 14, 0, tzinfo=UTC),
        status=MatchStatus.FINISHED,
        matchday=2,
        home_id=65,
        home_name="Manchester City FC",
        away_id=57,
        away_name="Arsenal FC",
        score=Score(1, 2, "AWAY_TEAM"),
    )
    view = h2h_table((match,))
    blob = " ".join(
        str(getattr(node, "value", "") or "") for node in _walk(view) if isinstance(node, ft.Text)
    )
    assert "1" in blob and "2" in blob
    assert "Дома" in blob
    assert "Manchester City FC" not in blob
    assert "Arsenal FC" not in blob


def test_score_card_names_stay_on_one_row() -> None:
    match = Match(
        id=1,
        competition_code="PL",
        utc_date=datetime(2026, 9, 26, 14, 0, tzinfo=UTC),
        status=MatchStatus.SCHEDULED,
        matchday=6,
        home_id=57,
        home_name="Arsenal FC",
        away_id=341,
        away_name="Leeds United FC",
        score=Score(None, None),
        venue="Emirates Stadium",
    )
    view = preliminary_score_card(Scoreline(1, 1, 0.14, 1.5, 1.5), match)
    name_rows = [
        node
        for node in _walk(view)
        if isinstance(node, ft.Row)
        and node.wrap is False
        and any(isinstance(child, ft.Text) and child.value == "Arsenal FC" for child in _walk(node))
        and any(
            isinstance(child, ft.Text) and child.value == "Leeds United FC" for child in _walk(node)
        )
    ]
    assert name_rows
    blob = " ".join(
        str(getattr(node, "value", "") or "") for node in _walk(view) if isinstance(node, ft.Text)
    )
    assert "VS" in blob
    assert "Emirates Stadium" in blob
