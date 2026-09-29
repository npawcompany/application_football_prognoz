from __future__ import annotations

from datetime import UTC, date, datetime

import flet as ft

from football_prognoz.domain.match import Match, MatchStatus, Score
from football_prognoz.services.calendar import (
    WEEKDAYS_SHORT_RU,
    by_kickoff,
    month_bounds,
    month_grid,
    month_title_ru,
    shift_month,
)
from football_prognoz.ui.components.day_picker import MatchDayPicker, cell_style


def _m(mid: int, hour: int, home: str, status=MatchStatus.TIMED, score=(None, None)) -> Match:
    return Match(
        id=mid,
        competition_code="PL",
        utc_date=datetime(2026, 10, 25, hour, 0, tzinfo=UTC),
        status=status,
        matchday=9,
        home_id=mid,
        home_name=home,
        away_id=100 + mid,
        away_name=f"Away {mid}",
        score=Score(*score),
    )


def test_month_grid_starts_on_monday_in_russian() -> None:
    assert WEEKDAYS_SHORT_RU[0] == "Пн" and WEEKDAYS_SHORT_RU[-1] == "Вс"
    weeks = month_grid(date(2026, 10, 1))  # 1 October 2026 is a Thursday
    assert weeks[0][:3] == [None, None, None]
    assert weeks[0][3] == date(2026, 10, 1)
    assert all(len(week) == 7 for week in weeks)
    assert weeks[-1][5] == date(2026, 10, 31)  # Saturday
    days = [d for week in weeks for d in week if d]
    assert len(days) == 31
    assert month_title_ru(date(2026, 10, 1)) == "Октябрь 2026"
    assert shift_month(date(2026, 12, 1), 1) == date(2027, 1, 1)
    assert shift_month(date(2026, 1, 1), -1) == date(2025, 12, 1)
    assert month_bounds(date(2028, 2, 10)) == (date(2028, 2, 1), date(2028, 2, 29))


def test_picker_day_list_is_sorted_by_kickoff() -> None:
    rows = [_m(3, 19, "Chelsea"), _m(1, 14, "Brighton"), _m(2, 14, "Arsenal")]
    assert [m.home_name for m in by_kickoff(rows)] == ["Arsenal", "Brighton", "Chelsea"]


def test_today_is_marked_differently_from_the_selected_day() -> None:
    today, picked = date(2026, 9, 29), date(2026, 10, 25)
    t = cell_style(today, selected=picked, today=today, marked=False)
    s = cell_style(picked, selected=picked, today=today, marked=True)
    assert t["ring"] and not t["filled"]
    assert s["filled"] and not s["ring"] and s["dot"]
    both = cell_style(today, selected=today, today=today, marked=False)
    assert both["ring"] and both["filled"]
    assert cell_style(date(2026, 10, 24), selected=picked, today=today, marked=False)["weekend"]


def _texts(control) -> list[str]:
    out: list[str] = []

    def walk(node) -> None:
        if isinstance(node, ft.Text) and isinstance(node.value, str):
            out.append(node.value)
        for attr in ("content", "controls"):
            value = getattr(node, attr, None)
            if isinstance(value, list):
                for child in value:
                    walk(child)
            elif isinstance(value, ft.Control):
                walk(value)

    walk(control)
    return out


def test_picker_lists_the_highlighted_day_and_ignores_stale_answers() -> None:
    day_requests: list[date] = []
    month_requests: list[tuple[date, date]] = []
    picked: list[date] = []
    picker = MatchDayPicker(
        day=date(2026, 10, 25),
        today=date(2026, 9, 29),
        on_pick=picked.append,
        load_day=lambda day, deliver: day_requests.append(day),
        load_month=lambda first, last, deliver: month_requests.append((first, last)),
    )
    picker._request_day()
    picker._request_month()
    assert day_requests == [date(2026, 10, 25)]
    assert month_requests == [(date(2026, 10, 1), date(2026, 10, 31))]
    assert "Загружаем…" in _texts(picker.dialog.content)
    finished = _m(4, 12, "Leeds", MatchStatus.FINISHED, (2, 1))
    picker.deliver_day(date(2026, 10, 25), [_m(3, 19, "Chelsea"), finished], False)
    texts = _texts(picker.dialog.content)
    assert "2 матча" in texts
    assert "2:1" in texts  # a played match shows its score instead of the time
    assert texts.index("Leeds") < texts.index("Chelsea")
    assert "Октябрь 2026" in texts and "Пн" in texts
    picker.deliver_month(date(2026, 10, 1), {date(2026, 10, 25), date(2026, 10, 3)})
    assert picker.marked == {date(2026, 10, 25), date(2026, 10, 3)}
    picker.select(date(2026, 11, 2))  # another month: markers + list requested again
    assert month_requests[-1] == (date(2026, 11, 1), date(2026, 11, 30))
    assert day_requests[-1] == date(2026, 11, 2)
    picker.deliver_day(date(2026, 10, 25), [_m(9, 10, "Old")], False)  # stale
    assert picker.matches == []
    picker.confirm()
    assert picked == [date(2026, 11, 2)]
