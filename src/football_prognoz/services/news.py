"""Recent team headlines for the explanation (indirect factor, never part of 1X2).

GNews is used when GNEWS_API_KEY is set; RSS feeds of sports outlets are the keyless
fallback. Everything is cached in SQLite (`api_cache`) and the GNews daily budget is
counted in `api_usage`. The service never raises: problems go to `NewsReport.notes`.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from football_prognoz.data.api_football import StoreBudget
from football_prognoz.data.news import (
    GNEWS_DAILY_BUDGET,
    GNEWS_PROVIDER,
    GNewsClient,
    NewsError,
    RawArticle,
    RssClient,
    classify_topic,
)
from football_prognoz.data.store import SQLiteStore
from football_prognoz.domain.match import Match
from football_prognoz.domain.news import NewsItem, NewsReport, TeamNews
from football_prognoz.services.team_matching import normalize_team_name

log = logging.getLogger(__name__)

TTL_GNEWS_H = 6
TTL_RSS_H = 1
WINDOW_DAYS = 7
MAX_PER_TEAM = 5

SRC_GNEWS = "GNews: заголовки новостей о командах (задержка до 12 ч)"
SRC_RSS_PREFIX = "RSS спортивных изданий"

# Extra names used by the press. Keys are normalize_team_name() results.
_PRESS_NAMES: dict[str, tuple[str, ...]] = {
    "manchester city": ("man city",),
    "manchester united": ("man utd", "man united"),
    "tottenham": ("spurs", "tottenham hotspur"),
    "wolves": ("wolverhampton",),
    "inter": ("inter milan", "internazionale"),
    "bayern munich": ("bayern", "bayern munchen"),
    "paris saint germain": ("psg", "paris st germain"),
    "atletico madrid": ("atletico",),
    "borussia dortmund": ("dortmund",),
    "brighton": ("brighton hove albion",),
    "west ham": ("west ham united",),
    "newcastle": ("newcastle united",),
    "nottingham forest": ("forest",),
    "bayer leverkusen": ("leverkusen",),
    "athletic bilbao": ("athletic club",),
    "psv eindhoven": ("psv",),
    "lask": ("lask linz",),
    "lask linz": ("lask",),
    "red bull salzburg": ("salzburg", "rb salzburg"),
    "sturm graz": ("sturm",),
    "rapid wien": ("rapid vienna",),
    "austria wien": ("austria vienna",),
    "rb leipzig": ("leipzig",),
    "eintracht frankfurt": ("frankfurt",),
    "vfb stuttgart": ("stuttgart",),
    "borussia monchengladbach": ("gladbach", "monchengladbach"),
    "olympique lyonnais": ("lyon",),
    "olympique de marseille": ("marseille",),
    "real sociedad": ("la real",),
    "sporting cp": ("sporting lisbon",),
    "sporting portugal": ("sporting cp", "sporting lisbon"),
    "real betis": ("betis",),
    "real betis balompie": ("betis", "real betis"),
    "benfica": ("sl benfica",),
    "porto": ("fc porto",),
    "ajax": ("ajax amsterdam",),
    "feyenoord": ("feyenoord rotterdam",),
    "celtic": ("celtic fc",),
    "rangers": ("rangers fc",),
    "club brugge": ("brugge", "club bruges"),
    "galatasaray": ("gala",),
    "shakhtar donetsk": ("shakhtar",),
    "dinamo zagreb": ("dinamo",),
    "crvena zvezda": ("red star belgrade", "red star"),
    "slavia praha": ("slavia prague",),
    "sparta praha": ("sparta prague",),
}
_SHORT_OK = frozenset({"psg", "psv", "az"})
# Generic club words: dropped to build short aliases ("LASK Linz" -> also "LASK").
_CLUB_WORDS = frozenset(
    {
        "fc",
        "afc",
        "cf",
        "sc",
        "sk",
        "fk",
        "ac",
        "as",
        "ss",
        "us",
        "sv",
        "bk",
        "if",
        "ik",
        "cd",
        "ud",
        "rc",
        "rcd",
        "sd",
        "club",
        "de",
        "the",
        "calcio",
        "futebol",
        "clube",
        "football",
        "1",
        "1.",
        "cp",
        "sl",
        "nk",
        "hnk",
        "gnk",
        "tsg",
        "vfl",
        "vfb",
        "osc",
    }
)


def _normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    text = text.replace("&", " and ")
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", text).split())


def team_phrases(name: str) -> tuple[str, ...]:
    """Whole-word phrases that identify a team in a headline ("Man City", "Arsenal").

    Besides the full name and press names, short aliases are derived: the name without
    generic club words, and its first token when it is an acronym in the original
    ("LASK Linz" -> "lask"). City names alone are never aliases (Manchester, Milan).
    """
    primary = normalize_team_name(name)
    tokens = [t for t in _normalize_text(name).split() if t not in _CLUB_WORDS]
    raw = " ".join(tokens)
    phrases = [primary, raw, *_PRESS_NAMES.get(primary, ()), *_PRESS_NAMES.get(raw, ())]
    original = [t for t in re.split(r"[\s\-]+", name.strip()) if t]
    acronyms = {_normalize_text(t) for t in original if len(t) >= 3 and t.isupper() and t.isalpha()}
    if len(tokens) >= 2 and tokens[0] in acronyms:
        phrases.append(tokens[0])  # "LASK Linz" -> "lask"; city names are never used alone
    result = []
    for phrase in phrases:
        phrase = _normalize_text(phrase)
        if not phrase or phrase in result:
            continue
        if len(phrase) < 4 and phrase not in _SHORT_OK and phrase not in acronyms:
            continue
        result.append(phrase)
    return tuple(result)


def mentions_team(text: str, phrases: tuple[str, ...]) -> bool:
    haystack = f" {_normalize_text(text)} "
    return any(f" {phrase} " in haystack for phrase in phrases)


def gnews_query(name: str) -> str:
    """Up to three aliases OR-ed: `("lask linz" OR "lask") AND (football OR soccer)`."""
    phrases = list(team_phrases(name)[:3]) or [name]
    if len(phrases) == 1:
        return f'"{phrases[0]}" AND (football OR soccer)'
    joined = " OR ".join(f'"{p}"' for p in phrases)
    return f"({joined}) AND (football OR soccer)"


class NewsService:
    def __init__(
        self,
        store: SQLiteStore,
        *,
        gnews: GNewsClient | None = None,
        rss: RssClient | None = None,
        budget: StoreBudget | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        self._gnews = gnews if gnews is not None and gnews.enabled else None
        self._rss = rss
        self._budget = budget or StoreBudget(store, GNEWS_DAILY_BUDGET, provider=GNEWS_PROVIDER)
        self._now = now or (lambda: datetime.now(UTC))

    @property
    def enabled(self) -> bool:
        return self._gnews is not None or self._rss is not None

    @property
    def provider(self) -> str | None:
        if self._gnews is not None:
            return "gnews"
        return "rss" if self._rss is not None else None

    def close(self) -> None:
        for client in (self._gnews, self._rss):
            if client is not None:
                client.close()

    # --- public ---------------------------------------------------------------

    def report_for(self, match: Match) -> NewsReport | None:
        if not self.enabled:
            return None
        now = self._now()
        since = now - timedelta(days=WINDOW_DAYS)
        notes: list[str] = []
        sources: list[str] = []
        provider = ""
        home: list[RawArticle] = []
        away: list[RawArticle] = []

        if self._gnews is not None:
            try:
                home = self._gnews_team(match.home_name, since)
                away = self._gnews_team(match.away_name, since)
                provider = "gnews"
                sources.append(SRC_GNEWS)
            except NewsError as exc:
                log.warning("GNews failed: %s", exc)
                notes.append(str(exc))
                home, away = [], []

        if not (home or away) and self._rss is not None:
            articles, used = self._rss_articles(notes)
            home_phrases = team_phrases(match.home_name)
            away_phrases = team_phrases(match.away_name)
            home = [
                a for a in articles if mentions_team(f"{a.title} {a.description}", home_phrases)
            ]
            away = [
                a for a in articles if mentions_team(f"{a.title} {a.description}", away_phrases)
            ]
            provider = "rss"
            if used:
                sources.append(f"{SRC_RSS_PREFIX}: {', '.join(used)}")

        report = NewsReport(
            home=TeamNews(match.home_name, self._select(home, since, now)),
            away=TeamNews(match.away_name, self._select(away, since, now)),
            provider=provider or (self.provider or ""),
            sources=tuple(sources),
            notes=tuple(dict.fromkeys(notes)),
        )
        if not report.has_data():
            report = NewsReport(
                home=report.home,
                away=report.away,
                provider=report.provider,
                sources=report.sources,
                notes=report.notes + (f"Свежих новостей за {WINDOW_DAYS} дней не найдено.",),
            )
        return report

    # --- internals ------------------------------------------------------------

    def _gnews_team(self, team_name: str, since: datetime) -> list[RawArticle]:
        assert self._gnews is not None
        key = f"gnews:{normalize_team_name(team_name)}"
        cached = self._store.get_api_payload(key, TTL_GNEWS_H)
        if isinstance(cached, list):
            return [RawArticle.from_json(item) for item in cached if isinstance(item, dict)]
        if not self._budget.try_consume():
            raise NewsError("Суточный бюджет запросов GNews исчерпан.", kind="quota")
        try:
            articles = self._gnews.search(gnews_query(team_name), since=since)
        except NewsError as exc:
            if exc.kind == "quota":
                self._budget.mark_exhausted()
            raise
        self._store.put_api_payload(key, [a.to_json() for a in articles])
        return articles

    def _rss_articles(self, notes: list[str]) -> tuple[list[RawArticle], list[str]]:
        assert self._rss is not None
        articles: list[RawArticle] = []
        used: list[str] = []
        for source, url in self._rss.feeds.items():
            key = f"rss:{url}"
            cached = self._store.get_api_payload(key, TTL_RSS_H)
            if isinstance(cached, list):
                items = [RawArticle.from_json(item) for item in cached if isinstance(item, dict)]
            else:
                try:
                    items = self._rss.fetch(source, url)
                except NewsError as exc:
                    log.info("RSS feed failed: %s", exc)
                    notes.append(str(exc))
                    continue
                self._store.put_api_payload(key, [a.to_json() for a in items])
            used.append(source)
            articles.extend(items)
        return articles, used

    @staticmethod
    def _select(articles: list[RawArticle], since: datetime, now: datetime) -> tuple[NewsItem, ...]:
        seen: set[str] = set()
        fresh = []
        for article in sorted(articles, key=lambda a: a.published_at, reverse=True):
            if not (since <= article.published_at <= now + timedelta(hours=1)):
                continue
            key = _normalize_text(article.title)
            if key in seen:
                continue
            seen.add(key)
            fresh.append(
                NewsItem(
                    title=article.title,
                    source=article.source,
                    url=article.url,
                    published_at=article.published_at,
                    topic=classify_topic(f"{article.title} {article.description}"),
                    summary=article.description,
                )
            )
            if len(fresh) >= MAX_PER_TEAM:
                break
        return tuple(fresh)
