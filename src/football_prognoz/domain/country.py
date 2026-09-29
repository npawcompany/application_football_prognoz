"""Map football-data.org nationality / area names to flag-icons ISO codes."""

from __future__ import annotations

from dataclasses import dataclass

# Codes match lipis/flag-icons `flags/4x3/{code}.svg` (ISO 3166-1 alpha-2,
# plus gb-eng / gb-sct / gb-wls / gb-nir for Home Nations).
_NAME_TO_CODE: dict[str, str] = {
    "afghanistan": "af",
    "albania": "al",
    "algeria": "dz",
    "andorra": "ad",
    "angola": "ao",
    "argentina": "ar",
    "armenia": "am",
    "australia": "au",
    "austria": "at",
    "azerbaijan": "az",
    "bahrain": "bh",
    "bangladesh": "bd",
    "belarus": "by",
    "belgium": "be",
    "benin": "bj",
    "bolivia": "bo",
    "bosnia": "ba",
    "bosnia and herzegovina": "ba",
    "bosnia-herzegovina": "ba",
    "brazil": "br",
    "bulgaria": "bg",
    "burkina faso": "bf",
    "cameroon": "cm",
    "canada": "ca",
    "cape verde": "cv",
    "cabo verde": "cv",
    "chile": "cl",
    "china": "cn",
    "china pr": "cn",
    "colombia": "co",
    "congo": "cg",
    "congo dr": "cd",
    "dr congo": "cd",
    "costa rica": "cr",
    "côte d'ivoire": "ci",
    "cote d'ivoire": "ci",
    "ivory coast": "ci",
    "croatia": "hr",
    "cuba": "cu",
    "curacao": "cw",
    "cyprus": "cy",
    "czechia": "cz",
    "czech republic": "cz",
    "denmark": "dk",
    "dominican republic": "do",
    "ecuador": "ec",
    "egypt": "eg",
    "el salvador": "sv",
    "england": "gb-eng",
    "europe": "eu",
    "equatorial guinea": "gq",
    "estonia": "ee",
    "ethiopia": "et",
    "faroe islands": "fo",
    "finland": "fi",
    "france": "fr",
    "gabon": "ga",
    "gambia": "gm",
    "georgia": "ge",
    "germany": "de",
    "ghana": "gh",
    "gibraltar": "gi",
    "greece": "gr",
    "grenada": "gd",
    "guatemala": "gt",
    "guinea": "gn",
    "guinea-bissau": "gw",
    "haiti": "ht",
    "honduras": "hn",
    "hong kong": "hk",
    "hungary": "hu",
    "iceland": "is",
    "india": "in",
    "indonesia": "id",
    "iran": "ir",
    "iraq": "iq",
    "ireland": "ie",
    "republic of ireland": "ie",
    "israel": "il",
    "italy": "it",
    "jamaica": "jm",
    "japan": "jp",
    "jordan": "jo",
    "kazakhstan": "kz",
    "kenya": "ke",
    "kosovo": "xk",
    "kuwait": "kw",
    "latvia": "lv",
    "lebanon": "lb",
    "liberia": "lr",
    "libya": "ly",
    "liechtenstein": "li",
    "lithuania": "lt",
    "luxembourg": "lu",
    "macedonia": "mk",
    "north macedonia": "mk",
    "madagascar": "mg",
    "malaysia": "my",
    "mali": "ml",
    "malta": "mt",
    "mauritania": "mr",
    "mexico": "mx",
    "moldova": "md",
    "montenegro": "me",
    "morocco": "ma",
    "mozambique": "mz",
    "namibia": "na",
    "netherlands": "nl",
    "new zealand": "nz",
    "nicaragua": "ni",
    "nigeria": "ng",
    "northern ireland": "gb-nir",
    "north ireland": "gb-nir",
    "norway": "no",
    "oman": "om",
    "pakistan": "pk",
    "palestine": "ps",
    "panama": "pa",
    "paraguay": "py",
    "peru": "pe",
    "philippines": "ph",
    "poland": "pl",
    "portugal": "pt",
    "qatar": "qa",
    "romania": "ro",
    "russia": "ru",
    "rwanda": "rw",
    "saudi arabia": "sa",
    "scotland": "gb-sct",
    "senegal": "sn",
    "serbia": "rs",
    "sierra leone": "sl",
    "singapore": "sg",
    "slovakia": "sk",
    "slovenia": "si",
    "somalia": "so",
    "south africa": "za",
    "south korea": "kr",
    "korea republic": "kr",
    "korea, south": "kr",
    "spain": "es",
    "sudan": "sd",
    "suriname": "sr",
    "sweden": "se",
    "switzerland": "ch",
    "syria": "sy",
    "taiwan": "tw",
    "tajikistan": "tj",
    "tanzania": "tz",
    "thailand": "th",
    "togo": "tg",
    "trinidad and tobago": "tt",
    "tunisia": "tn",
    "turkey": "tr",
    "türkiye": "tr",
    "turkiye": "tr",
    "uganda": "ug",
    "ukraine": "ua",
    "united arab emirates": "ae",
    "uae": "ae",
    "united states": "us",
    "usa": "us",
    "united states of america": "us",
    "uruguay": "uy",
    "uzbekistan": "uz",
    "venezuela": "ve",
    "vietnam": "vn",
    "wales": "gb-wls",
    "zambia": "zm",
    "zimbabwe": "zw",
}

_ISO3_TO_CODE: dict[str, str] = {
    "ARG": "ar",
    "AUS": "au",
    "AUT": "at",
    "BEL": "be",
    "BRA": "br",
    "CAN": "ca",
    "CHE": "ch",
    "CHL": "cl",
    "CHN": "cn",
    "CIV": "ci",
    "CMR": "cm",
    "COL": "co",
    "CZE": "cz",
    "DEU": "de",
    "DNK": "dk",
    "DZA": "dz",
    "ECU": "ec",
    "EGY": "eg",
    "ENG": "gb-eng",
    "ESP": "es",
    "FIN": "fi",
    "FRA": "fr",
    "GBR": "gb",
    "GHA": "gh",
    "GRC": "gr",
    "HRV": "hr",
    "HUN": "hu",
    "IDN": "id",
    "IRL": "ie",
    "IRN": "ir",
    "IRQ": "iq",
    "ISL": "is",
    "ISR": "il",
    "ITA": "it",
    "JAM": "jm",
    "JPN": "jp",
    "KOR": "kr",
    "MAR": "ma",
    "MEX": "mx",
    "NGA": "ng",
    "NLD": "nl",
    "NIR": "gb-nir",
    "NOR": "no",
    "NZL": "nz",
    "PER": "pe",
    "POL": "pl",
    "PRT": "pt",
    "PRY": "py",
    "QAT": "qa",
    "ROU": "ro",
    "RUS": "ru",
    "SAU": "sa",
    "SCO": "gb-sct",
    "SEN": "sn",
    "SRB": "rs",
    "SVK": "sk",
    "SVN": "si",
    "SWE": "se",
    "TUN": "tn",
    "TUR": "tr",
    "UKR": "ua",
    "URY": "uy",
    "USA": "us",
    "VEN": "ve",
    "WAL": "gb-wls",
    "ZAF": "za",
}


def flag_code(name: str | None, *, iso3: str | None = None) -> str | None:
    """Return a flag-icons file stem, or None when the name is unknown."""
    if iso3:
        mapped = _ISO3_TO_CODE.get(iso3.strip().upper())
        if mapped:
            return mapped
        if len(iso3) == 2:
            return iso3.strip().lower()
    if not name:
        return None
    key = " ".join(name.replace("_", " ").split()).casefold()
    if key in _NAME_TO_CODE:
        return _NAME_TO_CODE[key]
    if len(key) == 2 and key.isalpha():
        return key
    if len(key) == 3 and key.isalpha():
        return _ISO3_TO_CODE.get(key.upper())
    return None


# Free-tier competition codes → country/region shown next to the league name.
_COMPETITION_COUNTRY: dict[str, str] = {
    "PL": "England",
    "ELC": "England",
    "PD": "Spain",
    "SA": "Italy",
    "BL1": "Germany",
    "FL1": "France",
    "DED": "Netherlands",
    "PPL": "Portugal",
    "BSA": "Brazil",
    "CL": "Europe",
    "EC": "Europe",
    "WC": "World",
}


def competition_country(code: str | None) -> str | None:
    if not code:
        return None
    return _COMPETITION_COUNTRY.get(code.strip().upper())


# Areas without a country flag. football-data.org serves no `area.flag` for World.
_WORLD_NAMES = frozenset({"world", "international", "worldwide", "мир"})
_WORLD_CODES = frozenset({"INT", "WLD", "WOR"})
_CONTINENT_NAMES = frozenset(
    {"africa", "asia", "south america", "north america", "oceania", "n/c america"}
)
_EUROPE_NAMES = frozenset({"europe", "европа"})
_EUROPE_CODES = frozenset({"EUR", "EU", "UEFA"})

FLAG_ICON_GLOBE = "globe"
FLAG_ICON_UNKNOWN = "flag"


@dataclass(frozen=True)
class FlagSource:
    """How to draw the flag of an area: remote URL, bundled asset code, fallback icon.

    The UI shows `url` first (football-data.org `area.flag`, cached by the image
    cache), with the bundled `asset` as the error/offline fallback, and `icon` when
    there is neither (World and continents: a globe; unknown names: a flag outline).
    """

    url: str | None = None
    asset: str | None = None
    icon: str | None = None

    @property
    def empty(self) -> bool:
        return not (self.url or self.asset or self.icon)


def _key(name: str | None) -> str:
    return " ".join((name or "").replace("_", " ").split()).casefold()


def is_world_area(name: str | None, iso3: str | None = None) -> bool:
    code = (iso3 or "").strip().upper()
    return code in _WORLD_CODES or _key(name) in _WORLD_NAMES


def resolve_flag(
    name: str | None,
    *,
    iso3: str | None = None,
    flag_url: str | None = None,
) -> FlagSource:
    """Every area gets a mark: flag URL, bundled flag, globe (World) or flag icon."""
    url = (flag_url or "").strip() or None
    if url is not None and not url.startswith(("http://", "https://")):
        url = None
    key = _key(name)
    code = (iso3 or "").strip().upper()
    if not key and not code and url is None:
        return FlagSource()
    if is_world_area(name, iso3) or key in _CONTINENT_NAMES:
        return FlagSource(url=url, icon=FLAG_ICON_GLOBE)
    if key in _EUROPE_NAMES or code in _EUROPE_CODES:
        return FlagSource(url=url, asset="eu")
    asset = flag_code(name, iso3=iso3)
    if url is None and asset is None:
        return FlagSource(icon=FLAG_ICON_UNKNOWN)
    return FlagSource(url=url, asset=asset)
