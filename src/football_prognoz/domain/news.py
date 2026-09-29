"""Team news headlines: an indirect factor for the explanation, never for 1X2."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

TOPIC_INJURY = "injury"
TOPIC_SUSPENSION = "suspension"
TOPIC_MANAGER = "manager"
TOPIC_TRANSFER = "transfer"
TOPIC_LINEUP = "lineup"
TOPIC_CLUB = "club"
TOPIC_MATCH = "match"
TOPIC_OTHER = "other"

TOPIC_LABELS = {
    TOPIC_INJURY: "травма",
    TOPIC_SUSPENSION: "дисквалификация",
    TOPIC_MANAGER: "тренер",
    TOPIC_TRANSFER: "трансфер",
    TOPIC_LINEUP: "состав",
    TOPIC_CLUB: "клуб и финансы",
    TOPIC_MATCH: "матч и форма",
    TOPIC_OTHER: "прочее",
}


@dataclass(frozen=True)
class NewsItem:
    title: str
    source: str
    url: str
    published_at: datetime
    topic: str = TOPIC_OTHER
    summary: str = ""  # plain-text description from the feed, if any

    @property
    def topic_label(self) -> str:
        return TOPIC_LABELS.get(self.topic, TOPIC_LABELS[TOPIC_OTHER])


@dataclass(frozen=True)
class TeamNews:
    team_name: str
    items: tuple[NewsItem, ...] = ()


@dataclass(frozen=True)
class NewsReport:
    home: TeamNews
    away: TeamNews
    provider: str  # "gnews" | "rss"
    sources: tuple[str, ...] = ()
    notes: tuple[str, ...] = field(default_factory=tuple)

    def has_data(self) -> bool:
        return bool(self.home.items or self.away.items)


@dataclass(frozen=True)
class NewsPoint:
    """One key point of the LLM news summary; `headline` is an id like "h2" / "a1"."""

    text: str
    headline: str


@dataclass(frozen=True)
class TeamNewsTakeaway:
    points: tuple[NewsPoint, ...] = ()
    relevance: str = ""  # how the news matters for this match (Russian)


@dataclass(frozen=True)
class NewsSummary:
    """«Итог по новостям» from the LLM. Never changes probabilities."""

    text: str
    home: TeamNewsTakeaway
    away: TeamNewsTakeaway
    model: str
    stale_note: str = ""  # e.g. "новости старые или не про матч"
    generated_at: datetime | None = None
    notice: str = ""
    cited: dict[str, str] = field(default_factory=dict)  # headline id -> title snapshot


def headline_ids(report: NewsReport) -> dict[str, NewsItem]:
    """Stable ids for the prompt and the validation: h1..hN (home), a1..aN (away)."""
    ids: dict[str, NewsItem] = {}
    for prefix, team in (("h", report.home), ("a", report.away)):
        for index, item in enumerate(team.items, start=1):
            ids[f"{prefix}{index}"] = item
    return ids
