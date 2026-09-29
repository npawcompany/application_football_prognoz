from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from football_prognoz.config import ROOT_DIR
from football_prognoz.data.api_football import (
    FD_TO_AF_LEAGUE,
    ApiFootballClient,
    ApiFootballError,
    StoreBudget,
    af_season,
    parse_cards,
    parse_fixtures,
    parse_injuries,
    parse_lineups,
    parse_ratings,
    parse_sidelined,
    parse_transfers,
)
from football_prognoz.data.football_data_org import RateLimiter
from football_prognoz.data.store import SQLiteStore

AF_SAMPLES = ROOT_DIR / "data" / "samples" / "api_football"


def _sample(name: str) -> dict:
    return json.loads((AF_SAMPLES / name).read_text(encoding="utf-8"))


def _client(handler, **kwargs) -> ApiFootballClient:
    http = httpx.Client(
        base_url="https://v3.football.api-sports.io", transport=httpx.MockTransport(handler)
    )
    kwargs.setdefault("limiter", RateLimiter(1000))
    return ApiFootballClient("af-key", client=http, **kwargs)


def test_no_key_raises_without_request() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = ApiFootballClient("  ", client=http)
    assert client.enabled is False
    with pytest.raises(ApiFootballError) as info:
        client.injuries(1)
    assert info.value.kind == "no_key"
    assert calls == []


def test_get_sends_only_apisports_header_and_params() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json=_sample("injuries.json"),
            headers={"x-ratelimit-requests-remaining": "88", "X-RateLimit-Remaining": "9"},
        )

    client = _client(handler)
    items = client.injuries(686314)
    assert len(items) == 13
    request = seen[0]
    assert request.url.path == "/injuries"
    assert request.url.params["fixture"] == "686314"
    assert request.headers["x-apisports-key"] == "af-key"
    assert client.daily_remaining == 88
    assert client.minute_remaining == 9


@pytest.mark.parametrize(
    ("sample", "kind"),
    [("error_plan.json", "plan"), ("error_token.json", "auth")],
)
def test_error_envelope_is_classified(sample: str, kind: str) -> None:
    client = _client(lambda _r: httpx.Response(200, json=_sample(sample)))
    with pytest.raises(ApiFootballError) as info:
        client.injuries(1)
    assert info.value.kind == kind
    assert "af-key" not in str(info.value)


def test_daily_quota_error_closes_budget(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "q.db")
    budget = StoreBudget(store, 90)
    body = {"errors": {"requests": "You have reached the request limit for the day"}}
    client = _client(lambda _r: httpx.Response(200, json=body), budget=budget)
    with pytest.raises(ApiFootballError) as info:
        client.injuries(1)
    assert info.value.kind == "quota"
    assert budget.remaining() == 0


def test_budget_exhausted_makes_no_request(tmp_path: Path) -> None:
    calls = []
    store = SQLiteStore(tmp_path / "b.db")
    budget = StoreBudget(store, 1)

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"errors": [], "response": []})

    client = _client(handler, budget=budget)
    client.injuries(1)
    with pytest.raises(ApiFootballError) as info:
        client.injuries(2)
    assert info.value.kind == "quota"
    assert len(calls) == 1


def test_status_does_not_consume_budget(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "s.db")
    budget = StoreBudget(store, 90)
    body = {
        "errors": [],
        "response": {
            "subscription": {"plan": "Free"},
            "requests": {"current": 3, "limit_day": 100},
        },
    }
    client = _client(lambda _r: httpx.Response(200, json=body), budget=budget)
    assert client.status()["requests"]["limit_day"] == 100
    assert budget.remaining() == 90


def test_zero_daily_remaining_header_closes_budget(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "h.db")
    budget = StoreBudget(store, 90)
    client = _client(
        lambda _r: httpx.Response(
            200,
            json={"errors": [], "response": []},
            headers={"x-ratelimit-requests-remaining": "0"},
        ),
        budget=budget,
    )
    client.injuries(1)
    assert budget.remaining() == 0


def test_429_backs_off_with_retry_after_then_succeeds() -> None:
    sleeps: list[float] = []
    responses = [
        httpx.Response(429, headers={"Retry-After": "3"}),
        httpx.Response(200, json={"errors": [], "response": [{"ok": 1}]}),
    ]
    client = _client(lambda _r: responses.pop(0), sleep=sleeps.append)
    assert client.injuries(1) == [{"ok": 1}]
    assert sleeps == [3.0]


def test_429_gives_up_after_retries() -> None:
    sleeps: list[float] = []
    client = _client(lambda _r: httpx.Response(429), sleep=sleeps.append)
    with pytest.raises(ApiFootballError) as info:
        client.injuries(1)
    assert info.value.kind == "rate_limit"
    assert sleeps == [2.0, 4.0]


@pytest.mark.parametrize("status", [401, 403, 499, 500])
def test_http_errors(status: int) -> None:
    client = _client(lambda _r: httpx.Response(status, json={"message": "x"}))
    with pytest.raises(ApiFootballError) as info:
        client.injuries(1)
    assert info.value.kind == ("auth" if status in {401, 403} else "http")


def test_parse_injuries_groups_by_team_and_keeps_suspensions() -> None:
    grouped = parse_injuries(_sample("injuries.json")["response"])
    assert set(grouped) == {157, 85}
    psg = {a.player_name: a for a in grouped[85]}
    assert psg["L. Paredes"].is_suspension
    assert psg["L. Paredes"].is_certain
    assert grouped[157][0].reason == "Broken ankle"


def test_parse_sidelined_players_variant() -> None:
    periods = parse_sidelined(_sample("sidelined_players.json")["response"])
    assert set(periods) == {276, 278}
    assert periods[276][0] == ("Virus", "2023-08-10", "2023-08-15")


def test_parse_cards_from_official_events_sample() -> None:
    cards = parse_cards(_sample("fixtures_events.json")["response"], 215662, "2019-10-01")
    all_cards = [card for items in cards.values() for card in items]
    reds = [card for card in all_cards if card.is_red]
    assert len(all_cards) == 11
    assert len(reds) == 1
    assert reds[0].detail == "Red Card"


def test_parse_transfers_filters_by_team_and_date() -> None:
    items = _sample("transfers.json")["response"]
    moves = parse_transfers(items, 2289, since="2012-01-01")
    assert [(m.direction, m.date) for m in moves] == [
        ("out", "2018-07-01"),
        ("in", "2015-06-11"),
        ("out", "2014-01-01"),
        ("in", "2012-01-01"),
    ]
    assert moves[0].other_team == "Santa Fe"
    assert moves[0].kind is None  # "N/A"
    # teams.in == teams.out (Atlas -> Atlas) is not a real move
    assert parse_transfers(items, 2283, since="2000-01-01") == []


def test_parse_lineups_and_ratings() -> None:
    lineups = parse_lineups(_sample("fixtures_lineups.json")["response"])
    city = lineups[50]
    assert city.formation == "4-3-3"
    assert len(city.start_xi) == 11
    assert city.start_xi[0].name == "Ederson"
    ratings = parse_ratings(_sample("fixtures_players.json")["response"])
    assert ratings[2284][0].rating == pytest.approx(6.3)
    assert ratings[2284][0].minutes == 90


def test_parse_fixtures_and_season_helpers() -> None:
    fixtures = parse_fixtures(_sample("fixtures_season.json")["response"])
    assert [f.fixture_id for f in fixtures][:2] == [1299980, 1299990]
    target = next(f for f in fixtures if f.fixture_id == 1300001)
    assert target.home_name == "Arsenal"
    assert not target.is_finished
    assert FD_TO_AF_LEAGUE["PL"] == 39
    assert af_season("PL", datetime(2026, 9, 26, tzinfo=UTC)) == 2026
    assert af_season("PL", datetime(2027, 3, 1, tzinfo=UTC)) == 2026
    assert af_season("BSA", datetime(2027, 3, 1, tzinfo=UTC)) == 2027
    assert af_season("WC", datetime(2026, 6, 20, tzinfo=UTC)) == 2026
