"""Match football-data.org teams/fixtures to API-Football by normalized names + date."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from datetime import timedelta

from football_prognoz.data.api_football import AfFixture
from football_prognoz.domain.match import Match

# Tokens that carry no identity ("FC", "Calcio", ...). Kept small on purpose.
_NOISE = frozenset(
    {
        "fc",
        "afc",
        "cf",
        "sc",
        "ac",
        "as",
        "ssc",
        "rc",
        "rcd",
        "ud",
        "cd",
        "sd",
        "sv",
        "vfb",
        "vfl",
        "tsg",
        "bv",
        "club",
        "de",
        "del",
        "la",
        "calcio",
        "football",
        "futbol",
        "clube",
        "sl",
        "cp",
        "ec",
        "1",
        "the",
    }
)

# Normalized football-data.org name -> normalized API-Football name.
_ALIASES = {
    "wolverhampton wanderers": "wolves",
    "internazionale milano": "inter",
    "manchester united": "manchester united",
    "man united": "manchester united",
    "man city": "manchester city",
    "paris saint germain": "paris saint germain",
    "atletico madrid": "atletico madrid",
    "club atletico madrid": "atletico madrid",
    "brighton hove albion": "brighton",
    "tottenham hotspur": "tottenham",
    "west ham united": "west ham",
    "newcastle united": "newcastle",
    "nottingham forest": "nottingham forest",
    "leeds united": "leeds",
    "bayer 04 leverkusen": "bayer leverkusen",
    "borussia monchengladbach": "borussia monchengladbach",
    "eintracht frankfurt": "eintracht frankfurt",
    "bayern munchen": "bayern munich",
    "athletic": "athletic bilbao",
    "real betis balompie": "real betis",
    "psv": "psv eindhoven",
    "sporting clube portugal": "sporting cp",
    "sport lisboa e benfica": "benfica",
}


def normalize_team_name(name: str) -> str:
    """lower, strip diacritics and noise tokens, '&'->'and', 'st.'->'st'."""
    text = unicodedata.normalize("NFKD", name)
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    text = text.replace("&", " and ").replace("saint-", "saint ").replace("st.", "st ")
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    tokens = [token for token in text.split() if token not in _NOISE and token != "and"]
    normalized = " ".join(tokens)
    return _ALIASES.get(normalized, normalized)


def name_score(fd_name: str, af_name: str) -> int:
    """2 = same normalized name, 1 = one token set inside the other, 0 = different."""
    left = normalize_team_name(fd_name)
    right = normalize_team_name(af_name)
    if not left or not right:
        return 0
    if left == right:
        return 2
    left_tokens, right_tokens = set(left.split()), set(right.split())
    smaller, larger = sorted((left_tokens, right_tokens), key=len)
    # "manchester city" vs "manchester united" share a token but neither contains the other.
    if smaller and smaller <= larger and any(len(t) > 3 for t in smaller):
        return 1
    return 0


def names_match(fd_name: str, af_name: str) -> bool:
    return name_score(fd_name, af_name) > 0


def find_fixture(
    match: Match,
    candidates: Iterable[AfFixture],
    *,
    tolerance: timedelta = timedelta(hours=36),
    known_home: int | None = None,
    known_away: int | None = None,
) -> AfFixture | None:
    """Best fixture within `tolerance` whose teams match both sides.

    Known API-Football ids beat names; exact names beat partial ones ("Espanyol
    Barcelona" must not win over "Barcelona"); ties go to the closest kick-off.
    """
    best: AfFixture | None = None
    best_key: tuple[int, timedelta] | None = None
    for item in candidates:
        gap = abs(item.date - match.utc_date)
        if gap > tolerance:
            continue
        if known_home:
            home = 3 if item.home_id == known_home else 0
        else:
            home = name_score(match.home_name, item.home_name)
        if known_away:
            away = 3 if item.away_id == known_away else 0
        else:
            away = name_score(match.away_name, item.away_name)
        if not (home and away):
            continue
        key = (-(home + away), gap)
        if best_key is None or key < best_key:
            best, best_key = item, key
    return best
