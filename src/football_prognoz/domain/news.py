"""Team news headlines: an indirect factor for the explanation, never for 1X2."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

TOPIC_INJURY = "injury"
TOPIC_SUSPENSION = "suspension"
TOPIC_MANAGER = "manager"
TOPIC_TRANSFER = "transfer"
TOPIC_OTHER = "other"

TOPIC_LABELS = {
    TOPIC_INJURY: "травма",
    TOPIC_SUSPENSION: "дисквалификация",
    TOPIC_MANAGER: "тренер",
    TOPIC_TRANSFER: "трансфер",
    TOPIC_OTHER: "прочее",
}


@dataclass(frozen=True)
class NewsItem:
    title: str
    source: str
    url: str
    published_at: datetime
    topic: str = TOPIC_OTHER

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
