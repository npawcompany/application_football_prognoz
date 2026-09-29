"""When to call the LLM for a match (match analysis + market comments, news summary).

Rules (docs/FORECAST.md, «Когда вызывается LLM»):
1. Finished match → never call. Show the analysis saved before or at kick-off, else
   «AI-разбор не сохранён, матч уже сыгран».
2. Every successful generation is saved in SQLite (`llm_analyses`, key match id + kind)
   with generated_at and the model name. A failed generation never overwrites it.
3. At most one generation per 12 hours per match and kind: a fresher saved result is
   shown instantly; an older one is shown while a new one is generated in the
   background, then swapped in.
4. After kick-off a pre-match analysis is frozen (no refresh during the match).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from football_prognoz.domain.match import Match

REFRESH_AFTER = timedelta(hours=12)

KIND_MATCH = "match"
KIND_NEWS = "news"

PLAN_USE_SAVED = "use_saved"  # show saved, no call
PLAN_GENERATE = "generate"  # nothing saved: call now
PLAN_REFRESH = "refresh"  # show saved, regenerate in the background
PLAN_FINISHED_NONE = "finished_none"  # finished and nothing saved: no call

FINISHED_NONE_TEXT = "AI-разбор не сохранён, матч уже сыгран."
NEWS_FINISHED_NONE_TEXT = "Итог по новостям не сохранён, матч уже сыгран."


@dataclass(frozen=True)
class SavedAnalysis:
    kind: str
    payload: dict[str, Any]
    model: str
    generated_at: datetime

    @classmethod
    def from_row(cls, kind: str, row: dict[str, Any] | None) -> SavedAnalysis | None:
        if not row or not isinstance(row.get("payload"), dict):
            return None
        return cls(kind, row["payload"], str(row.get("model") or ""), row["generated_at"])


def plan_for(saved: SavedAnalysis | None, match: Match, now: datetime) -> str:
    kickoff = match.utc_date
    if match.status.is_finished():
        if saved is not None and saved.generated_at <= kickoff:
            return PLAN_USE_SAVED
        return PLAN_FINISHED_NONE
    if saved is None:
        return PLAN_GENERATE
    if now >= kickoff and saved.generated_at <= kickoff:
        return PLAN_USE_SAVED  # frozen at kick-off
    if now - saved.generated_at < REFRESH_AFTER:
        return PLAN_USE_SAVED
    return PLAN_REFRESH


def generated_caption(generated_at: datetime | None, model: str, tz: Any = None) -> str:
    """«Сгенерировано 29.09.2026 21:40, модель gpt-oss:120b» in local time."""
    if generated_at is None:
        return ""
    local = generated_at.astimezone(tz) if tz is not None else generated_at.astimezone()
    text = f"Сгенерировано {local:%d.%m.%Y %H:%M}"
    return f"{text}, модель {model}" if model else text
