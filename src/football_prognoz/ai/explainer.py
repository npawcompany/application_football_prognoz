from __future__ import annotations

import json
from typing import Any, Protocol

import httpx

from football_prognoz.domain.match import Match
from football_prognoz.domain.prediction import Explanation, MatchFeatures, Probabilities, Scoreline

SYSTEM_PROMPT = """You explain football statistical forecasts.
You receive JSON with match facts, 1X2 probabilities, and an optional preliminary score.
The preliminary score is the most likely Poisson cell from last-5 goal averages only.
Write 2-4 short sentences in Russian.
Do not invent injuries, lineups, xG, or scores that are not in the JSON.
If a preliminary score is present, you may mention it with its probability; it is not a guarantee.
Do not give betting advice. Do not claim certainty.
"""


class LLMClient(Protocol):
    def complete(self, system: str, user: str) -> str: ...


class OpenAICompatClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str,
        *,
        http: httpx.Client | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._owns = http is None
        self._http = http or httpx.Client(timeout=timeout)

    def close(self) -> None:
        if self._owns:
            self._http.close()

    def complete(self, system: str, user: str) -> str:
        url = f"{self._base_url}/chat/completions"
        response = self._http.post(
            url,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self._model,
                "temperature": 0.3,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
        )
        response.raise_for_status()
        payload = response.json()
        return str(payload["choices"][0]["message"]["content"]).strip()


class Explainer:
    def __init__(self, llm: LLMClient | None, model_name: str) -> None:
        self._llm = llm
        self._model_name = model_name

    @property
    def enabled(self) -> bool:
        return self._llm is not None

    def build_prompt(
        self,
        match: Match,
        features: MatchFeatures,
        probabilities: Probabilities,
        scoreline: Scoreline | None = None,
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
        }
        if scoreline is not None:
            payload["preliminary_score"] = {
                "label": scoreline.label,
                "home_goals": scoreline.home_goals,
                "away_goals": scoreline.away_goals,
                "probability": round(scoreline.probability, 4),
                "expected_home": round(scoreline.expected_home, 3),
                "expected_away": round(scoreline.expected_away, 3),
            }
        return payload

    def explain(
        self,
        match: Match,
        features: MatchFeatures,
        probabilities: Probabilities,
        scoreline: Scoreline | None = None,
    ) -> Explanation | None:
        if self._llm is None:
            return None
        payload = self.build_prompt(match, features, probabilities, scoreline)
        text = self._llm.complete(SYSTEM_PROMPT, json.dumps(payload, ensure_ascii=False))
        return Explanation(text=text, model=self._model_name)
