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


def test_list_teams_maps_domain_fields(teams_payload: dict) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Auth-Token"] == "test-key"
        assert request.url.path.endswith("/competitions/PL/teams")
        return httpx.Response(200, json=teams_payload)

    teams = _client(handler).list_teams("PL")
    assert [team.id for team in teams] == [57, 65]
    arsenal = teams[0]
    assert arsenal.name == "Arsenal FC"
    assert arsenal.short_name == "Arsenal"
    assert arsenal.tla == "ARS"
    assert arsenal.crest == "https://crests.football-data.org/57.png"
    city = teams[1]
    assert city.short_name == "Man City"
    assert city.tla == "MCI"


def test_list_teams_skips_invalid_ids() -> None:
    payload = {
        "teams": [
            {"id": 0, "name": "Broken"},
            {"id": 18, "name": "Borussia Mönchengladbach", "shortName": "M'gladbach", "tla": "BMG"},
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    teams = _client(handler).list_teams("BL1")
    assert len(teams) == 1
    assert teams[0].id == 18
    assert teams[0].short_name == "M'gladbach"


def test_get_team_maps_coach_and_squad(team_payload: dict) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/teams/57")
        return httpx.Response(200, json=team_payload)

    roster = _client(handler).get_team(57)
    assert roster.team_name == "Arsenal FC"
    assert roster.coach is not None
    assert roster.coach.name == "Mikel Arteta"
    assert roster.coach.role == "COACH"
    assert roster.coach.contract_until == "2027-06-30"
    names = [player.name for player in roster.squad]
    assert names == ["David Raya", "William Saliba", "Martin Ødegaard", "Bukayo Saka"]
    assert roster.squad[2].shirt_number == 8
    assert roster.venue == "Emirates Stadium"
    assert roster.city == "London"
    assert roster.country == "England"
    assert roster.country_code == "gb-eng"


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
