"""News clients: GNews v4 search (keyed) and RSS 2.0 feeds of sports outlets (keyless).

Documented in docs/DATA_SOURCES.md ("Новости"). Only headline metadata is kept:
title, source, link, publication time and a short plain-text description.
"""

from __future__ import annotations

import html
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from football_prognoz.data.football_data_org import RateLimiter, parse_utc
from football_prognoz.domain.news import (
    TOPIC_INJURY,
    TOPIC_MANAGER,
    TOPIC_OTHER,
    TOPIC_SUSPENSION,
    TOPIC_TRANSFER,
)

log = logging.getLogger(__name__)

GNEWS_BASE = "https://gnews.io/api/v4"
GNEWS_PROVIDER = "gnews"
GNEWS_DAILY_BUDGET = 80  # free plan: 100/day
GNEWS_PER_MINUTE = 30  # free plan: 1 request per second
DESCRIPTION_CHARS = 300
MAX_FEED_BYTES = 3_000_000

# name -> URL. Checked with curl on 2026-09-29 (HTTP 200, RSS 2.0).
DEFAULT_FEEDS: dict[str, str] = {
    "BBC Sport": "https://feeds.bbci.co.uk/sport/football/rss.xml",
    "The Guardian": "https://www.theguardian.com/football/rss",
    "Sky Sports": "https://www.skysports.com/rss/12040",
    "ESPN": "https://www.espn.com/espn/rss/soccer/news",
}

USER_AGENT = "FootballPrognoz/1.0 (+desktop app; RSS reader)"

_TOPIC_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        TOPIC_SUSPENSION,
        re.compile(r"\b(suspen\w*|ban(ned)?|red card|sent off|serves? a)\b", re.IGNORECASE),
    ),
    (
        TOPIC_INJURY,
        re.compile(
            r"\b(injur\w*|hamstring|knee|ankle|groin|calf|thigh|fitness|doubt|ruled out|"
            r"sidelined|surgery|knock|limp\w*)\b",
            re.IGNORECASE,
        ),
    ),
    (
        TOPIC_MANAGER,
        re.compile(
            r"\b(sack\w*|manager|head coach|boss|interim|appoint\w*|resign\w*)\b", re.IGNORECASE
        ),
    ),
    (
        TOPIC_TRANSFER,
        re.compile(r"\b(transfer|sign(s|ed|ing)?|loan|bid|deal|fee)\b", re.IGNORECASE),
    ),
)

_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")


def classify_topic(text: str) -> str:
    """Keyword topic: suspension > injury > manager > transfer > other."""
    for topic, pattern in _TOPIC_PATTERNS:
        if pattern.search(text):
            return topic
    return TOPIC_OTHER


def plain_text(value: str | None, limit: int = DESCRIPTION_CHARS) -> str:
    if not value:
        return ""
    text = html.unescape(_TAG_RE.sub(" ", html.unescape(value)))
    text = _SPACE_RE.sub(" ", text).strip()
    text = text.replace("Continue reading...", "").strip()
    return text[:limit]


@dataclass(frozen=True)
class RawArticle:
    title: str
    description: str
    url: str
    source: str
    published_at: datetime

    def to_json(self) -> dict[str, str]:
        return {
            "title": self.title,
            "description": self.description,
            "url": self.url,
            "source": self.source,
            "published_at": self.published_at.isoformat(),
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> RawArticle:
        return cls(
            title=str(data.get("title") or ""),
            description=str(data.get("description") or ""),
            url=str(data.get("url") or ""),
            source=str(data.get("source") or ""),
            published_at=parse_utc(str(data.get("published_at") or "")),
        )


class NewsError(Exception):
    """kind: auth | quota | rate_limit | http | network | payload | no_key."""

    def __init__(self, message: str, *, kind: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.kind = kind
        self.status_code = status_code


def parse_gnews(body: Any) -> list[RawArticle]:
    if not isinstance(body, dict):
        raise NewsError("Неожиданный ответ GNews.", kind="payload")
    articles = []
    for item in body.get("articles") or []:
        if not isinstance(item, dict) or not item.get("title"):
            continue
        source = item.get("source") if isinstance(item.get("source"), dict) else {}
        try:
            published = parse_utc(item.get("publishedAt"))
        except ValueError:
            continue
        articles.append(
            RawArticle(
                title=plain_text(item.get("title"), 300),
                description=plain_text(item.get("description")),
                url=str(item.get("url") or ""),
                source=str(source.get("name") or "GNews"),
                published_at=published,
            )
        )
    return articles


def _rss_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value.strip())
    except (TypeError, ValueError):
        try:
            dt = parse_utc(value.strip())
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def parse_rss(xml_text: str | bytes, source: str) -> list[RawArticle]:
    """RSS 2.0 `channel/item` -> RawArticle. Items without a title or date are skipped."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise NewsError(f"Лента {source}: не удалось разобрать XML.", kind="payload") from exc
    articles = []
    for item in root.iter("item"):
        title = plain_text(item.findtext("title"), 300)
        published = _rss_date(item.findtext("pubDate"))
        if not title or published is None:
            continue
        articles.append(
            RawArticle(
                title=title,
                description=plain_text(item.findtext("description")),
                url=(item.findtext("link") or "").strip(),
                source=source,
                published_at=published,
            )
        )
    return articles


def _gnews_error(response: httpx.Response) -> NewsError:
    code = response.status_code
    if code == 401:
        return NewsError(
            "GNews отклонил ключ. Проверьте GNEWS_API_KEY.", kind="auth", status_code=code
        )
    if code == 403:
        return NewsError(
            "GNews: суточная квота исчерпана (сброс в 00:00 UTC).", kind="quota", status_code=code
        )
    if code == 429:
        return NewsError(
            "GNews: слишком много запросов (429).", kind="rate_limit", status_code=code
        )
    return NewsError(f"Ошибка GNews: HTTP {code}.", kind="http", status_code=code)


class GNewsClient:
    """GET /search with the key in the X-Api-Key header (never in the URL/logs)."""

    def __init__(
        self,
        api_key: str,
        *,
        http: httpx.Client | None = None,
        limiter: RateLimiter | None = None,
        base_url: str = GNEWS_BASE,
        timeout: float = 15.0,
    ) -> None:
        self._api_key = api_key.strip()
        self._client = http or httpx.Client(base_url=base_url, timeout=timeout)
        self._limiter = limiter or RateLimiter(GNEWS_PER_MINUTE)

    @property
    def enabled(self) -> bool:
        return bool(self._api_key)

    def search(
        self, query: str, *, since: datetime, lang: str = "en", max_items: int = 10
    ) -> list[RawArticle]:
        if not self._api_key:
            raise NewsError("Не задан GNEWS_API_KEY.", kind="no_key")
        params = {
            "q": query[:200],
            "lang": lang,
            "max": max_items,
            "in": "title,description",
            "from": since.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "sortby": "publishedAt",
        }
        self._limiter.wait()
        try:
            response = self._client.get(
                "/search", params=params, headers={"X-Api-Key": self._api_key}
            )
        except httpx.HTTPError as exc:
            raise NewsError("Нет соединения с GNews.", kind="network") from exc
        if response.status_code >= 400:
            raise _gnews_error(response)
        try:
            body = response.json()
        except ValueError as exc:
            raise NewsError("GNews вернул не-JSON.", kind="payload") from exc
        return parse_gnews(body)

    def close(self) -> None:
        self._client.close()


class RssClient:
    """Plain GET of public RSS feeds; no key, no cookies."""

    def __init__(
        self,
        feeds: dict[str, str] | None = None,
        *,
        http: httpx.Client | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.feeds = dict(DEFAULT_FEEDS if feeds is None else feeds)
        self._client = http or httpx.Client(
            timeout=timeout, follow_redirects=True, headers={"User-Agent": USER_AGENT}
        )

    def fetch(self, source: str, url: str) -> list[RawArticle]:
        try:
            response = self._client.get(url)
        except httpx.HTTPError as exc:
            raise NewsError(f"Лента {source} недоступна.", kind="network") from exc
        if response.status_code >= 400:
            raise NewsError(
                f"Лента {source}: HTTP {response.status_code}.",
                kind="http",
                status_code=response.status_code,
            )
        if len(response.content) > MAX_FEED_BYTES:
            raise NewsError(f"Лента {source}: слишком большой ответ.", kind="payload")
        return parse_rss(response.content, source)

    def close(self) -> None:
        self._client.close()
