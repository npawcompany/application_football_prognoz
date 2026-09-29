"""LLM «Итог по новостям»: reads the team headlines and writes a short Russian takeaway.

Validation: JSON schema, every cited headline id exists in the list and belongs to that
team, quoted titles must be real headlines, no percentages (the news never changes the
model's numbers) and no "guaranteed outcome" wording. One retry, then an error.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from football_prognoz.ai.explainer import LLMClient, _check_no_guarantee, _extract_json, _Invalid
from football_prognoz.ai.ollama import LLMError
from football_prognoz.domain.match import Match
from football_prognoz.domain.news import (
    NewsPoint,
    NewsReport,
    NewsSummary,
    TeamNewsTakeaway,
    headline_ids,
)

log = logging.getLogger(__name__)

NEWS_PROMPT_VERSION = "news-v1"
MAX_POINTS = 4
MAX_SENTENCES = 5

NEWS_SYSTEM_PROMPT = """You summarise football team news for a desktop forecast app.
You receive JSON: match (home, away, kickoff), headlines — a list of
{id, team: "home"|"away", title, summary, source, published, topic}. Headlines are
unverified media reports.

Return ONLY one JSON object, no markdown:
{
  "summary": "2-4 short Russian sentences: the overall takeaway for this match",
  "home": {"points": [{"text": "key point in Russian", "headline": "<id>"}],
           "relevance": "one Russian sentence: does it matter for this match"},
  "away": {"points": [...], "relevance": "..."},
  "stale_note": "Russian note if the news is old, generic or not about this match, else empty"
}

Rules:
- Use only the given headlines; each point cites exactly one existing id of that team
  (home points cite h-ids, away points cite a-ids). 0-4 points per team.
- Key points: injuries, suspensions, transfers, coach, morale/discipline, form.
- Say "по данным СМИ"; never present rumours as facts.
- No percentages, odds or probabilities: the statistical forecast is computed separately
  and must not be changed. Never promise an outcome. No betting advice.
- If the headlines are irrelevant or stale, say so in stale_note and keep points empty.
"""

_QUOTE_RE = re.compile(r"[«\"“]([^»\"”]{12,})[»\"”]")
_SENTENCE_RE = re.compile(r"[^.!?…]+[.!?…]+|[^.!?…]+$")


def build_news_prompt(match: Match, report: NewsReport) -> dict[str, Any]:
    items = []
    for key, item in headline_ids(report).items():
        items.append(
            {
                "id": key,
                "team": "home" if key.startswith("h") else "away",
                "title": item.title,
                "summary": item.summary[:300],
                "source": item.source,
                "published": item.published_at.date().isoformat(),
                "topic": item.topic_label,
            }
        )
    return {
        "match": {
            "home": match.home_name,
            "away": match.away_name,
            "kickoff": match.utc_date.isoformat(),
        },
        "headlines": items,
    }


def _team_part(data: Any, side: str, allowed: set[str]) -> TeamNewsTakeaway:
    if data is None:
        return TeamNewsTakeaway()
    if not isinstance(data, dict):
        raise _Invalid(f"{side} должен быть объектом")
    raw = data.get("points") or []
    if not isinstance(raw, list):
        raise _Invalid(f"{side}.points должен быть списком")
    prefix = "h" if side == "home" else "a"
    points: list[NewsPoint] = []
    for entry in raw[:MAX_POINTS]:
        if not isinstance(entry, dict):
            raise _Invalid(f"{side}.points: элемент не объект")
        text = str(entry.get("text") or "").strip()
        ref = str(entry.get("headline") or "").strip().lower()
        if not text:
            raise _Invalid(f"{side}.points: пустой текст")
        if ref not in allowed or not ref.startswith(prefix):
            raise _Invalid(f"{side}.points: заголовка «{ref or '∅'}» нет в списке этой команды")
        points.append(NewsPoint(text=text, headline=ref))
    return TeamNewsTakeaway(
        points=tuple(points), relevance=str(data.get("relevance") or "").strip()
    )


def parse_news_summary(text: str, report: NewsReport, model: str) -> NewsSummary:
    data = _extract_json(text)
    summary = str(data.get("summary") or "").strip()
    if not summary:
        raise _Invalid("нет поля summary")
    sentences = [s for s in _SENTENCE_RE.findall(summary) if s.strip()]
    if len(sentences) > MAX_SENTENCES:
        raise _Invalid(f"summary длиннее {MAX_SENTENCES} предложений")
    ids = headline_ids(report)
    allowed = set(ids)
    home = _team_part(data.get("home"), "home", allowed)
    away = _team_part(data.get("away"), "away", allowed)
    stale = str(data.get("stale_note") or "").strip()
    texts = [summary, stale, home.relevance, away.relevance]
    texts += [p.text for p in home.points + away.points]
    if any("%" in t for t in texts):
        raise _Invalid("в итоге по новостям не должно быть процентов и вероятностей")
    titles = [item.title.lower() for item in ids.values()]
    for t in texts:
        for quoted in _QUOTE_RE.findall(t):
            q = quoted.strip().lower()
            if not any(q in title or title in q for title in titles):
                raise _Invalid(f"цитата «{quoted[:40]}» не совпадает ни с одним заголовком")
    _check_no_guarantee(texts)
    cited = {p.headline: ids[p.headline].title for p in home.points + away.points}
    return NewsSummary(
        text=summary, home=home, away=away, model=model, stale_note=stale, cited=cited
    )


def news_summary_to_dict(summary: NewsSummary) -> dict[str, Any]:
    def team(t: TeamNewsTakeaway) -> dict[str, Any]:
        return {"points": [p.__dict__ for p in t.points], "relevance": t.relevance}

    return {
        "summary": summary.text,
        "home": team(summary.home),
        "away": team(summary.away),
        "stale_note": summary.stale_note,
        "notice": summary.notice,
        "cited": dict(summary.cited),
    }


def news_summary_from_dict(data: dict[str, Any], model: str) -> NewsSummary:
    def team(raw: Any) -> TeamNewsTakeaway:
        raw = raw if isinstance(raw, dict) else {}
        points = tuple(
            NewsPoint(text=str(p.get("text") or ""), headline=str(p.get("headline") or ""))
            for p in raw.get("points") or []
            if isinstance(p, dict)
        )
        return TeamNewsTakeaway(points=points, relevance=str(raw.get("relevance") or ""))

    return NewsSummary(
        text=str(data.get("summary") or ""),
        home=team(data.get("home")),
        away=team(data.get("away")),
        model=model,
        stale_note=str(data.get("stale_note") or ""),
        notice=str(data.get("notice") or ""),
        cited={str(k): str(v) for k, v in (data.get("cited") or {}).items()},
    )


class NewsSummaryError(LLMError):
    """The model answered twice, but both answers failed validation."""


class NewsSummarizer:
    def __init__(self, llm: LLMClient | None) -> None:
        self._llm = llm

    @property
    def enabled(self) -> bool:
        return self._llm is not None

    def summarize(self, match: Match, report: NewsReport) -> NewsSummary | None:
        """None without an LLM or without headlines; raises LLMError on failure."""
        if self._llm is None or not report.has_data():
            return None
        user = json.dumps(build_news_prompt(match, report), ensure_ascii=False, sort_keys=True)
        reply = self._llm.chat(NEWS_SYSTEM_PROMPT, user, temperature=0.2, json_mode=True)
        try:
            parsed = parse_news_summary(reply.text, report, reply.model)
        except _Invalid as first:
            log.warning("News summary rejected (%s); retrying once", first)
            retry = (
                f"{user}\n\nYour previous answer was rejected: {first}. "
                "Return ONLY one valid JSON object matching the schema."
            )
            reply = self._llm.chat(NEWS_SYSTEM_PROMPT, retry, temperature=0.0, json_mode=True)
            try:
                parsed = parse_news_summary(reply.text, report, reply.model)
            except _Invalid as second:
                raise NewsSummaryError(
                    f"Модель вернула некорректный итог по новостям дважды: {second}."
                ) from second
        return NewsSummary(
            text=parsed.text,
            home=parsed.home,
            away=parsed.away,
            model=parsed.model,
            stale_note=parsed.stale_note,
            notice=reply.notice,
            cited=parsed.cited,
        )
