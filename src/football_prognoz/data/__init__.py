from __future__ import annotations

from football_prognoz.domain.team import Competition

FREE_COMPETITIONS: tuple[Competition, ...] = (
    Competition(2021, "PL", "Premier League"),
    Competition(2014, "PD", "La Liga"),
    Competition(2019, "SA", "Serie A"),
    Competition(2002, "BL1", "Bundesliga"),
    Competition(2015, "FL1", "Ligue 1"),
    Competition(2003, "DED", "Eredivisie"),
    Competition(2017, "PPL", "Primeira Liga"),
    Competition(2016, "ELC", "Championship"),
    Competition(2013, "BSA", "Campeonato Brasileiro Série A"),
    Competition(2001, "CL", "UEFA Champions League"),
    Competition(2000, "WC", "FIFA World Cup"),
    Competition(2018, "EC", "European Championship"),
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
