"""LLM explainer: turns a structured facts package into a Russian analysis.

The model never computes or changes 1X2 probabilities. Its answer is validated:
JSON schema, favourite equal to the computed one, no "guaranteed outcome" wording,
and a confidence level capped by sample size and probability spread.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any, Protocol

from football_prognoz.ai.ollama import LLMError, LLMReply
from football_prognoz.domain.markets import MarketsTable
from football_prognoz.domain.match import Match
from football_prognoz.domain.prediction import (
    CONFIDENCE_LEVELS,
    Explanation,
    Factor,
    FactsPackage,
    MarketComment,
    MatchFeatures,
    Probabilities,
    Scoreline,
)

log = logging.getLogger(__name__)

PROMPT_VERSION = "analysis-v4"

SYSTEM_PROMPT = """You explain football statistical forecasts for a desktop app.
You receive JSON with: match, probabilities (1X2 computed by a local Elo + Poisson model;
they are FINAL), favorite ("1" home, "X" draw, "2" away), facts, context (Elo gap, form,
home/away records, goal trends, standings, head-to-head, rest days), an optional
preliminary_score, an optional markets table (bookmaker markets with the probability
computed by the same model: id, label, probability, push for refunds, fair_odds,
confidence), an optional player_status block (absences, recent red cards,
transfers, lineups, ratings, set-piece averages), an optional news block (recent
media headlines per team with topic), an optional historical_accuracy block (how past
pre-match forecasts of this model performed, incl. how often outcomes with a similar
probability came true) and data_sources.

Return ONLY one JSON object, no markdown, with exactly these keys:
{
  "summary": "2-3 short sentences in Russian",
  "home_factors": [{"factor": "fact from the JSON, Russian",
                    "effect": "how it shifts the picture for the home side, Russian",
                    "direction": "up|down|neutral"}],
  "away_factors": [{"factor": "...", "effect": "...", "direction": "up|down|neutral"}],
  "favorite": "1|X|2",
  "verdict": "1-2 sentences in Russian consistent with the computed probabilities",
  "confidence": "low|medium|high",
  "confidence_reason": "one short Russian sentence",
  "market_comments": [{"market": "<id from markets>", "comment": "1 short Russian sentence"}],
  "top_markets": [{"market": "<id from markets>", "reason": "why the facts support it, Russian"}],
  "risks": ["short Russian risk that could break the picture"]
}

Rules:
- All text values in Russian. 1-4 factors per side; direction is relative to that side.
- Every factor must be based on a value present in the JSON. Do not invent injuries,
  lineups, transfers, xG, weather, or scores that are not in the JSON. If player_status
  is null, say nothing specific about players.
- News headlines are unverified media reports: mention them only as "по данным СМИ",
  never as confirmed facts, and never let them override player_status or the numbers.
- "favorite" MUST equal the "favorite" field of the input. Never recompute, round
  differently, or contradict the probabilities; the verdict explains them.
- Never claim a guaranteed or certain outcome. Use cautious wording.
- "confidence": low when the sample is small or probabilities are close; high only
  when one outcome clearly dominates and the sample is large.
- If historical_accuracy is present, ground "confidence" and "confidence_reason" in it
  (e.g. "исторически такие прогнозы сбывались в 48% случаев"). It never changes the
  probabilities of this match. If it is null, do not mention past accuracy.
- If a preliminary score is present, you may mention it with its probability; it is
  not a guarantee.
- markets: the numbers are FINAL. Comment on 3-8 key markets and pick exactly 3
  "top_markets" — the ones best supported by the facts (not the highest odds). Use only
  ids present in "markets"; never invent a market, line or number. If you quote a
  percentage, it must be that market's "probability" rounded. Rows listed in
  "markets_unavailable" have no data: do not comment on them.
- risks: 1-4 concrete risks from the facts (absences, small sample, close
  probabilities, rest days, unverified news).
- Do not give betting advice: describe probabilities, never tell the user to bet.
"""

_GUARANTEE_RE = re.compile(
    r"(?:(\w+)\s+)?(гарантир\w*|стопроцентн\w*|без\s+сомнени\w*|"
    r"точно\s+(?:выиграет|победит|проиграет|будет))",
    re.IGNORECASE,
)
_NEGATIONS = frozenset({"не", "нет", "ни"})
_CONFIDENCE_ALIASES = {
    "low": "low",
    "низкая": "low",
    "medium": "medium",
    "средняя": "medium",
    "high": "high",
    "высокая": "high",
}
_DIRECTION_ALIASES = {
    "up": "up",
    "+": "up",
    "plus": "up",
    "down": "down",
    "-": "down",
    "minus": "down",
    "neutral": "neutral",
    "0": "neutral",
}
_MAX_FACTORS = 6
_MAX_MARKET_COMMENTS = 8
_MAX_RISKS = 4
TOP_MARKETS = 3
PERCENT_TOLERANCE = 1.5  # percentage points between a quoted % and the table value
_PERCENT_RE = re.compile(r"(\d{1,3}(?:[.,]\d+)?)\s*%")


class LLMClient(Protocol):
    def chat(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.2,
        json_mode: bool = True,
    ) -> LLMReply: ...


class ExplanationCache(Protocol):
    def get(self, key: str) -> dict[str, Any] | None: ...

    def put(self, key: str, value: dict[str, Any]) -> None: ...


class ExplanationError(LLMError):
    """The model answered, but the answer failed validation twice."""


class _Invalid(ValueError):
    pass


HISTORY_MEDIUM_BELOW = 0.5  # similar past forecasts came true less often -> max medium


def confidence_cap(
    probabilities: Probabilities,
    features: MatchFeatures,
    history_rate: float | None = None,
) -> str:
    """Highest honest confidence for these numbers (documented in docs/FORECAST.md).

    `history_rate`: observed hit rate of past forecasts with a similar probability
    (only passed when the sample is large enough)."""
    top = max(probabilities.home, probabilities.draw, probabilities.away)
    if features.sample_matches < 4 or top < 0.40:
        return "low"
    if top < 0.55 or features.sample_matches < 10:
        return "medium"
    if history_rate is not None and history_rate < HISTORY_MEDIUM_BELOW:
        return "medium"
    return "high"


def history_rate_from(facts: FactsPackage | None) -> float | None:
    if facts is None:
        return None
    block = facts.data.get("historical_accuracy")
    if not isinstance(block, dict) or not isinstance(block.get("similar_probability"), dict):
        return None
    rate = block["similar_probability"].get("observed_rate")
    return float(rate) if isinstance(rate, int | float) else None


def _extract_json(text: str) -> dict[str, Any]:
    body = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", body, re.DOTALL)
    if fence:
        body = fence.group(1).strip()
    start, end = body.find("{"), body.rfind("}")
    if start < 0 or end <= start:
        raise _Invalid("ответ не содержит JSON-объект")
    try:
        data = json.loads(body[start : end + 1])
    except json.JSONDecodeError as exc:
        raise _Invalid(f"невалидный JSON ({exc.msg})") from exc
    if not isinstance(data, dict):
        raise _Invalid("JSON не является объектом")
    return data


def _text(data: dict[str, Any], key: str, *, required: bool = True) -> str:
    value = data.get(key)
    if value is None and not required:
        return ""
    if not isinstance(value, str) or not value.strip():
        if required:
            raise _Invalid(f"нет строкового поля {key}")
        return ""
    return value.strip()


def _factors(data: dict[str, Any], key: str) -> tuple[Factor, ...]:
    raw = data.get(key, [])
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise _Invalid(f"{key} должен быть списком")
    items: list[Factor] = []
    for entry in raw[:_MAX_FACTORS]:
        if not isinstance(entry, dict):
            raise _Invalid(f"элемент {key} не объект")
        factor = _text(entry, "factor")
        effect = _text(entry, "effect")
        direction = _DIRECTION_ALIASES.get(str(entry.get("direction", "")).strip().lower())
        items.append(Factor(factor=factor, effect=effect, direction=direction or "neutral"))
    return tuple(items)


def _check_no_guarantee(texts: list[str]) -> None:
    for text in texts:
        for match in _GUARANTEE_RE.finditer(text):
            previous = (match.group(1) or "").lower()
            if previous not in _NEGATIONS:
                raise _Invalid(f"формулировка о гарантированном исходе: «{match.group(0)}»")


def _check_percentages(text: str, market_id: str, table: MarketsTable) -> None:
    market = table.by_key(market_id)
    expected = (market.effective or 0.0) * 100 if market is not None else None
    for raw in _PERCENT_RE.findall(text):
        value = float(raw.replace(",", "."))
        if expected is None or abs(value - expected) > PERCENT_TOLERANCE:
            raise _Invalid(
                f"в комментарии к {market_id} число {raw}% не совпадает с таблицей "
                f"({expected:.0f}%)"
                if expected is not None
                else f"рынок {market_id} без данных"
            )


def _market_items(
    data: dict[str, Any], key: str, text_key: str, table: MarketsTable, limit: int
) -> tuple[MarketComment, ...]:
    raw = data.get(key)
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise _Invalid(f"{key} должен быть списком")
    allowed = table.available_keys
    items: list[MarketComment] = []
    seen: set[str] = set()
    for entry in raw[:limit]:
        if not isinstance(entry, dict):
            raise _Invalid(f"элемент {key} не объект")
        market_id = str(entry.get("market") or "").strip()
        if market_id not in allowed:
            raise _Invalid(f"{key}: рынка «{market_id or '∅'}» нет в таблице")
        if market_id in seen:
            raise _Invalid(f"{key}: рынок {market_id} повторяется")
        seen.add(market_id)
        comment = _text(entry, text_key)
        _check_percentages(comment, market_id, table)
        items.append(MarketComment(market=market_id, comment=comment))
    return tuple(items)


def parse_markets_part(data: dict[str, Any], table: MarketsTable | None) -> dict[str, Any]:
    """Validate market comments / top-3 / risks against the computed table."""
    if table is None or not table.available_keys:
        return {"market_comments": [], "top_markets": [], "risks": []}
    comments = _market_items(data, "market_comments", "comment", table, _MAX_MARKET_COMMENTS)
    top = _market_items(data, "top_markets", "reason", table, TOP_MARKETS + 2)
    need = min(TOP_MARKETS, len(table.available_keys))
    if len(top) != need:
        raise _Invalid(f"top_markets: нужно ровно {need} рынка из таблицы, получено {len(top)}")
    raw_risks = data.get("risks") or []
    if not isinstance(raw_risks, list):
        raise _Invalid("risks должен быть списком")
    risks = [str(r).strip() for r in raw_risks[:_MAX_RISKS] if str(r).strip()]
    _check_no_guarantee([c.comment for c in comments + top] + risks)
    return {
        "market_comments": [c.__dict__ for c in comments],
        "top_markets": [c.__dict__ for c in top],
        "risks": risks,
    }


def parse_analysis(
    text: str,
    probabilities: Probabilities,
    features: MatchFeatures,
    history_rate: float | None = None,
    markets: MarketsTable | None = None,
) -> dict[str, Any]:
    """Validate the model answer. Returns normalized fields or raises _Invalid."""
    data = _extract_json(text)
    summary = _text(data, "summary")
    verdict = _text(data, "verdict")
    favorite = str(data.get("favorite", "")).strip().upper()
    expected = probabilities.favorite_label
    if favorite != expected:
        raise _Invalid(f"favorite={favorite or '∅'} противоречит расчёту (ожидалось {expected})")
    confidence = _CONFIDENCE_ALIASES.get(str(data.get("confidence", "")).strip().lower())
    if confidence is None:
        raise _Invalid("confidence должен быть low|medium|high")
    home_factors = _factors(data, "home_factors")
    away_factors = _factors(data, "away_factors")
    reason = _text(data, "confidence_reason", required=False)
    _check_no_guarantee(
        [summary, verdict, reason]
        + [f.factor + " " + f.effect for f in home_factors + away_factors]
    )
    cap = confidence_cap(probabilities, features, history_rate)
    if CONFIDENCE_LEVELS.index(confidence) > CONFIDENCE_LEVELS.index(cap):
        confidence = cap
        note = (
            "Уровень уверенности снижен приложением: мала выборка, близкие вероятности "
            "или похожие прогнозы в прошлом сбывались реже чем в половине случаев."
        )
        reason = f"{reason} {note}".strip()
    market_part = parse_markets_part(data, markets)
    return {
        **market_part,
        "summary": summary,
        "verdict": verdict,
        "confidence": confidence,
        "confidence_reason": reason,
        "home_factors": [f.__dict__ for f in home_factors],
        "away_factors": [f.__dict__ for f in away_factors],
    }


def _explanation_from(
    parsed: dict[str, Any], model: str, sources: tuple[str, ...], notice: str = ""
) -> Explanation:
    return Explanation(
        text=parsed["summary"],
        model=model,
        home_factors=tuple(Factor(**item) for item in parsed["home_factors"]),
        away_factors=tuple(Factor(**item) for item in parsed["away_factors"]),
        verdict=parsed["verdict"],
        confidence=parsed["confidence"],
        confidence_reason=parsed["confidence_reason"],
        sources=sources,
        market_comments=tuple(MarketComment(**c) for c in parsed.get("market_comments", [])),
        top_markets=tuple(MarketComment(**c) for c in parsed.get("top_markets", [])),
        risks=tuple(parsed.get("risks", [])),
        notice=notice,
    )


def explanation_to_dict(explanation: Explanation) -> dict[str, Any]:
    """Durable form for SQLite `llm_analyses` (kind "match")."""
    return {
        "summary": explanation.text,
        "verdict": explanation.verdict,
        "confidence": explanation.confidence,
        "confidence_reason": explanation.confidence_reason,
        "home_factors": [f.__dict__ for f in explanation.home_factors],
        "away_factors": [f.__dict__ for f in explanation.away_factors],
        "market_comments": [c.__dict__ for c in explanation.market_comments],
        "top_markets": [c.__dict__ for c in explanation.top_markets],
        "risks": list(explanation.risks),
        "sources": list(explanation.sources),
        "notice": explanation.notice,
    }


def explanation_from_dict(data: dict[str, Any], model: str) -> Explanation:
    return _explanation_from(
        data, model, tuple(data.get("sources", [])), str(data.get("notice") or "")
    )


class Explainer:
    def __init__(
        self,
        llm: LLMClient | None,
        model_name: str,
        *,
        cache: ExplanationCache | None = None,
    ) -> None:
        self._llm = llm
        self._model_name = model_name
        self._cache = cache

    @property
    def enabled(self) -> bool:
        return self._llm is not None

    @property
    def model_name(self) -> str:
        return self._model_name

    def close(self) -> None:
        closer = getattr(self._llm, "close", None)
        if callable(closer):
            closer()

    def build_prompt(
        self,
        match: Match,
        features: MatchFeatures,
        probabilities: Probabilities,
        scoreline: Scoreline | None = None,
        facts: FactsPackage | None = None,
        markets: MarketsTable | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "match": {
                "home": match.home_name,
                "away": match.away_name,
                "competition": match.competition_code,
                "utc_date": match.utc_date.isoformat(),
            },
            "probabilities": {
                "home": round(probabilities.home, 4),
                "draw": round(probabilities.draw, 4),
                "away": round(probabilities.away, 4),
            },
            "favorite": probabilities.favorite_label,
            "facts": {
                "home_form": features.home_form,
                "away_form": features.away_form,
                "home_elo": round(features.home_elo, 1),
                "away_elo": round(features.away_elo, 1),
                "h2h": features.h2h_summary,
                "home_position": features.home_position,
                "away_position": features.away_position,
                "sample_matches": features.sample_matches,
                "home_recent_goals_for": round(features.home_recent_goals_for, 3),
                "home_recent_goals_against": round(features.home_recent_goals_against, 3),
                "away_recent_goals_for": round(features.away_recent_goals_for, 3),
                "away_recent_goals_against": round(features.away_recent_goals_against, 3),
            },
            "player_status": None,
            "data_sources": list(facts.sources) if facts else [],
        }
        if facts is not None:
            lifted = {"player_status", "news", "historical_accuracy"}
            payload["context"] = {k: v for k, v in facts.data.items() if k not in lifted}
            payload["player_status"] = facts.data.get("player_status")
            payload["news"] = facts.data.get("news")
            payload["historical_accuracy"] = facts.data.get("historical_accuracy")
        if scoreline is not None:
            payload["preliminary_score"] = {
                "label": scoreline.label,
                "home_goals": scoreline.home_goals,
                "away_goals": scoreline.away_goals,
                "probability": round(scoreline.probability, 4),
                "expected_home": round(scoreline.expected_home, 3),
                "expected_away": round(scoreline.expected_away, 3),
            }
        if markets is not None:
            payload["markets"] = [m.to_dict() for m in markets.sorted() if m.available]
            payload["markets_unavailable"] = [
                {"id": m.key, "label": m.label, "note": m.note}
                for m in markets.sorted()
                if not m.available
            ]
            payload["markets_method"] = markets.method
        return payload

    def cache_key(self, user: str) -> str:
        raw = f"{PROMPT_VERSION}\n{self._model_name}\n{SYSTEM_PROMPT}\n{user}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def explain(
        self,
        match: Match,
        features: MatchFeatures,
        probabilities: Probabilities,
        scoreline: Scoreline | None = None,
        facts: FactsPackage | None = None,
        markets: MarketsTable | None = None,
    ) -> Explanation | None:
        """Return a validated analysis, None without an LLM, or raise LLMError."""
        if self._llm is None:
            return None
        payload = self.build_prompt(match, features, probabilities, scoreline, facts, markets)
        user = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        sources = facts.sources if facts else ()
        key = self.cache_key(user)
        if self._cache is not None:
            cached = self._cache.get(key)
            if cached is not None:
                try:
                    return _explanation_from(
                        cached["parsed"], cached["model"], sources, cached.get("notice", "")
                    )
                except (KeyError, TypeError) as exc:
                    log.warning("Ignoring malformed LLM cache entry: %s", exc)
        history_rate = history_rate_from(facts)
        reply = self._llm.chat(SYSTEM_PROMPT, user, temperature=0.2, json_mode=True)
        try:
            parsed = parse_analysis(reply.text, probabilities, features, history_rate, markets)
        except _Invalid as first:
            log.warning("LLM answer rejected (%s); retrying once", first)
            retry_user = (
                f"{user}\n\nYour previous answer was rejected: {first}. "
                "Return ONLY one valid JSON object matching the schema."
            )
            reply = self._llm.chat(SYSTEM_PROMPT, retry_user, temperature=0.0, json_mode=True)
            try:
                parsed = parse_analysis(reply.text, probabilities, features, history_rate, markets)
            except _Invalid as second:
                raise ExplanationError(
                    f"Модель вернула некорректный разбор дважды: {second}."
                ) from second
        if self._cache is not None:
            self._cache.put(key, {"parsed": parsed, "model": reply.model, "notice": reply.notice})
        return _explanation_from(parsed, reply.model, sources, reply.notice)
