from __future__ import annotations

import httpx
import pytest

from football_prognoz.data.csv_loader import load_csv
from football_prognoz.data.football_data_org import (
    FootballDataError,
    FootballDataOrgClient,
    RateLimiter,
)


def _client(handler) -> FootballDataOrgClient:
    transport = httpx.MockTransport(handler)
    http = httpx.Client(transport=transport, base_url="https://api.football-data.org/v4")
    return FootballDataOrgClient("test-key", client=http, limiter=RateLimiter(max_per_minute=100))


def test_list_competitions_filters_free_tier(competitions_payload: dict) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Auth-Token"] == "test-key"
        assert request.url.path.endswith("/competitions")
        return httpx.Response(200, json=competitions_payload)

    client = _client(handler)
    items = client.list_competitions()
    codes = {item.code for item in items}
    assert codes == {"PL", "PD"}
    assert "XYZ" not in codes


def test_list_matches_maps_domain_fields(matches_payload: dict) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "/competitions/PL/matches" in str(request.url)
        return httpx.Response(200, json=matches_payload)

    client = _client(handler)
    matches = client.list_matches("PL", season=2024)
    assert matches[0].home_name == "Arsenal FC"
    assert matches[0].score.home == 2
    assert matches[-1].status.value == "SCHEDULED"
    assert matches[-1].score.home is None


def test_list_standings(standings_payload: dict) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=standings_payload)

    rows = _client(handler).list_standings("PL")
    assert rows[0].team_name == "Manchester City FC"
    assert rows[0].position == 1


@pytest.mark.parametrize("status,message", [(403, "403"), (429, "429")])
def test_api_errors(status: int, message: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"message": "nope"})

    with pytest.raises(FootballDataError) as exc:
        _client(handler).list_competitions()
    assert exc.value.status_code == status
    assert message in str(exc.value)


def test_missing_api_key() -> None:
    http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})))
    client = FootballDataOrgClient("  ", client=http)
    with pytest.raises(FootballDataError):
        client.list_competitions()


def test_csv_loader(sample_csv) -> None:
    matches = load_csv(sample_csv)
    assert len(matches) == 6
    assert matches[0].competition_code == "PL"
    assert matches[0].score.home == 2
    arsenal_ids = {m.home_id for m in matches if m.home_name == "Arsenal"}
    arsenal_ids |= {m.away_id for m in matches if m.away_name == "Arsenal"}
    assert len(arsenal_ids) == 1
