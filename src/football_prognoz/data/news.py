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
    TOPIC_CLUB,
    TOPIC_INJURY,
    TOPIC_LINEUP,
    TOPIC_MANAGER,
    TOPIC_MATCH,
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

# name -> URL. Checked with curl on 2026-09-29 and 2026-09-30 (HTTP 200, RSS 2.0).
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
        re.compile(
            r"\b(suspen\w*|ban(ned|s)?|red cards?|sent off|serves? a|dismiss\w*|"
            r"one-match|three-match|appeal\w*)\b",
            re.IGNORECASE,
        ),
    ),
    (
        TOPIC_INJURY,
        re.compile(
            r"\b(injur\w*|hamstring|knee|ankle|groin|calf|thigh|foot|back|shoulder|"
            r"concussion|fitness|doubts?|doubtful|ruled out|sidelined|surgery|operation|"
            r"knocks?|limp\w*|setback|scan|recover\w*|returns? from|out for|miss(es)? "
            r"(the )?(game|match|clash|trip)|medical|illness|ill)\b",
            re.IGNORECASE,
        ),
    ),
    (
        TOPIC_MANAGER,
        re.compile(
            r"\b(sack\w*|manager\w*|head coach|coach(es|ing)?|boss|interim|appoint\w*|"
            r"resign\w*|gaffer|dugout|under pressure|under-fire|press conference|tactic\w*)\b",
            re.IGNORECASE,
        ),
    ),
    (
        TOPIC_TRANSFER,
        re.compile(
            r"\b(transfers?|sign(s|ed|ing)?|loan\w*|bid|deal|fee|target\w*|linked|"
            r"contract|extension|renew\w*|rumou?rs?|move to|joins?|departure|exit|"
            r"release clause|free agent)\b",
            re.IGNORECASE,
        ),
    ),
    (
        TOPIC_LINEUP,
        re.compile(
            r"\b(line-?ups?|starting xi|predicted xi|team news|squad|call-?up|"
            r"selection|bench(ed)?|rotation|captain\w*|debut)\b",
            re.IGNORECASE,
        ),
    ),
    (
        TOPIC_CLUB,
        re.compile(
            r"\b(verdict|guilty|charge[sd]?|breach\w*|financ\w*|fined?|points? deduction|"
            r"takeover|owner\w*|investor|stadium|revenue|debt|sanction\w*|psr|ffp|"
            r"court|tribunal|fans?|supporters?|protest\w*)\b",
            re.IGNORECASE,
        ),
    ),
    (
        TOPIC_MATCH,
        re.compile(
            r"\b(preview|report|ratings?|beat|beats|win(s|ning)?|won|draw(s|n)?|defeat\w*|"
            r"los(e|es|t|ing)|thrash\w*|stun\w*|comeback|hat-?trick|scor(e|es|ed|er)|"
            r"goals?|form|unbeaten|streak|table|top of|relegation|title race|vs?\.?|clash|"
            r"derby|fixture|highlights|talking points|player of)\b",
            re.IGNORECASE,
        ),
    ),
)

_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")


def classify_topic(text: str) -> str:
    """Keyword topic: suspension > injury > manager > transfer > lineup > club > match."""
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


_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_BARE_AMP_RE = re.compile(r"&(?!#\d+;|#x[0-9a-fA-F]+;|[A-Za-z][A-Za-z0-9]{1,31};)")
_ITEM_RE = re.compile(r"<item\b[^>]*>(.*?)</item>", re.IGNORECASE | re.DOTALL)
_HTML_START_RE = re.compile(rb"^\s*(<!doctype html|<html)", re.IGNORECASE)


def _decode_feed(data: str | bytes) -> str:
    if isinstance(data, str):
        return data.lstrip("\ufeff").lstrip()
    head = data[:200].decode("ascii", "ignore")
    match = re.search(r'encoding=["\']([A-Za-z0-9_\-]+)["\']', head)
    encodings = [match.group(1)] if match else []
    for encoding in (*encodings, "utf-8", "cp1252", "latin-1"):
        try:
            return data.decode(encoding).lstrip("\ufeff").lstrip()
        except (LookupError, UnicodeDecodeError):
            continue
    return data.decode("utf-8", "replace")


def _sanitize_xml(text: str) -> str:
    """Fix what breaks strict XML in real feeds: control chars, bare '&', HTML entities."""
    text = _CTRL_RE.sub("", text)
    text = re.sub(r"<\?xml[^>]*\?>", "", text, count=1)  # declared encoding is now moot
    for entity, char in (
        ("&nbsp;", "\u00a0"),
        ("&mdash;", "—"),
        ("&ndash;", "–"),
        ("&rsquo;", "’"),
        ("&lsquo;", "‘"),
        ("&hellip;", "…"),
    ):
        text = text.replace(entity, char)
    return _BARE_AMP_RE.sub("&amp;", text)


def _tag_text(block: str, tag: str) -> str | None:
    found = re.search(rf"<{tag}\b[^>]*>(.*?)</{tag}>", block, re.IGNORECASE | re.DOTALL)
    if not found:
        return None
    value = found.group(1).strip()
    cdata = re.fullmatch(r"<!\[CDATA\[(.*?)\]\]>", value, re.DOTALL)
    return cdata.group(1) if cdata else value


def _article(
    source: str, title: str | None, date: str | None, desc: str | None, link: str | None
) -> RawArticle | None:
    clean_title = plain_text(title, 300)
    published = _rss_date(date)
    if not clean_title or published is None:
        return None
    return RawArticle(
        title=clean_title,
        description=plain_text(desc),
        url=plain_text(link, 500),
        source=source,
        published_at=published,
    )


def parse_rss(xml_text: str | bytes, source: str) -> list[RawArticle]:
    """RSS 2.0 `channel/item` -> RawArticle. Items without a title or date are skipped.

    Tolerant: BOM / leading whitespace, wrong declared encoding, control characters and
    bare '&' are repaired; if strict XML still fails, items are read with a regex. An
    HTML page (consent wall, bot check, error page) is reported as such.
    """
    raw = xml_text if isinstance(xml_text, bytes) else xml_text.encode("utf-8", "replace")
    if _HTML_START_RE.match(raw.lstrip(b"\xef\xbb\xbf")):
        raise NewsError(f"Лента {source}: сайт вернул HTML-страницу вместо RSS.", kind="payload")
    text = _decode_feed(xml_text)
    root = None
    for candidate in (text, _sanitize_xml(text)):
        try:
            root = ET.fromstring(candidate)
            break
        except ET.ParseError:
            continue
    articles: list[RawArticle] = []
    if root is not None:
        for item in root.iter("item"):
            article = _article(
                source,
                item.findtext("title"),
                item.findtext("pubDate"),
                item.findtext("description"),
                item.findtext("link"),
            )
            if article is not None:
                articles.append(article)
        return articles
    blocks = _ITEM_RE.findall(text)
    if not blocks:
        raise NewsError(f"Лента {source}: не удалось разобрать XML.", kind="payload")
    for block in blocks:
        article = _article(
            source,
            _tag_text(block, "title"),
            _tag_text(block, "pubDate"),
            _tag_text(block, "description"),
            _tag_text(block, "link"),
        )
        if article is not None:
            articles.append(article)
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
            timeout=timeout,
            follow_redirects=True,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/rss+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.1",
            },
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
