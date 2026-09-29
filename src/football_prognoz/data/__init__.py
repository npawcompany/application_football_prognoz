from __future__ import annotations

from football_prognoz.domain.team import Competition

# Offline fallback when GET /v4/competitions is unavailable. Type and area mirror what the
# API returns for these codes (see docs/DATA_SOURCES.md); season dates stay unknown.
FREE_COMPETITIONS: tuple[Competition, ...] = (
    Competition(2021, "PL", "Premier League", type="LEAGUE", area_name="England"),
    Competition(2014, "PD", "La Liga", type="LEAGUE", area_name="Spain"),
    Competition(2019, "SA", "Serie A", type="LEAGUE", area_name="Italy"),
    Competition(2002, "BL1", "Bundesliga", type="LEAGUE", area_name="Germany"),
    Competition(2015, "FL1", "Ligue 1", type="LEAGUE", area_name="France"),
    Competition(2003, "DED", "Eredivisie", type="LEAGUE", area_name="Netherlands"),
    Competition(2017, "PPL", "Primeira Liga", type="LEAGUE", area_name="Portugal"),
    Competition(2016, "ELC", "Championship", type="LEAGUE", area_name="England"),
    Competition(2013, "BSA", "Campeonato Brasileiro Série A", type="LEAGUE", area_name="Brazil"),
    Competition(2001, "CL", "UEFA Champions League", type="CUP", area_name="Europe"),
    Competition(2000, "WC", "FIFA World Cup", type="CUP", area_name="World"),
    Competition(2018, "EC", "European Championship", type="CUP", area_name="Europe"),
)

FREE_CODES = {item.code for item in FREE_COMPETITIONS}

# football-data.co.uk Div -> football-data.org code
CSV_DIV_TO_CODE = {
    "E0": "PL",
    "E1": "ELC",
    "SP1": "PD",
    "I1": "SA",
    "D1": "BL1",
    "F1": "FL1",
    "N1": "DED",
    "P1": "PPL",
}
