# API-Football v3 samples

Not live responses: no API key yet (see `docs/DATA_SOURCES.md`).

Official examples copied verbatim from the API-Football OpenAPI spec v3.9.3
(`https://www.api-football.com/public/doc/openapi.yaml`, archived 2025-11-02):

- `injuries.json` — `GET /injuries?fixture=686314`
- `sidelined_players.json` — `GET /sidelined?players=276-278`
- `fixtures_events.json` — `GET /fixtures/events?fixture=215662`
- `transfers.json` — `GET /transfers?player=35845`
- `fixtures_lineups.json` — `GET /fixtures/lineups?fixture=592872`
- `fixtures_players.json` — `GET /fixtures/players?fixture=169080`
- `fixtures_statistics.json` — `GET /fixtures/statistics?fixture=215662&team=463`

Synthetic files in the same schema (Premier League names/ids for matching tests):

- `fixtures_season.json` — `GET /fixtures?league=39&season=2026`
- `injuries_fixture_pl.json` — `GET /injuries?fixture=1300001`
- `fixtures_events_pl.json` — `GET /fixtures/events?fixture=1299990`
- `error_plan.json`, `error_token.json` — error envelopes (`errors` as an object);
  the message texts follow public reports and must be verified with a real key.
