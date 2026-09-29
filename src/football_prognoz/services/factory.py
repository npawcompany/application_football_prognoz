"""Composition root: builds MatchService from Settings (UI must not import data/ai).

Rate limiters are process-wide so rebuilding the service after a settings save does
not reset the football-data.org 10 req/min window (or the API-Football one).
"""

from __future__ import annotations

from football_prognoz.ai.explainer import Explainer
from football_prognoz.ai.ollama import OllamaClient
from football_prognoz.config import Settings
from football_prognoz.data.api_football import (
    DEFAULT_DAILY_BUDGET,
    DEFAULT_PER_MINUTE,
    ApiFootballClient,
    StoreBudget,
)
from football_prognoz.data.football_data_org import FootballDataOrgClient, RateLimiter
from football_prognoz.data.store import SQLiteExplanationCache, SQLiteStore
from football_prognoz.models.predictor import Predictor
from football_prognoz.services.features import FeatureService
from football_prognoz.services.matches import MatchService
from football_prognoz.services.player_status import PlayerStatusService

FOOTBALL_DATA_LIMITER = RateLimiter(10)
API_FOOTBALL_LIMITER = RateLimiter(DEFAULT_PER_MINUTE)


def build_llm(settings: Settings) -> OllamaClient | None:
    if not settings.llm_configured:
        return None
    return OllamaClient(
        model=settings.ollama_model,
        host=settings.ollama_base_url,
        api_key=settings.ollama_api_key,
        fallback_model=settings.ollama_fallback_model,
    )


def build_service(
    settings: Settings,
    *,
    fd_limiter: RateLimiter | None = None,
    af_limiter: RateLimiter | None = None,
) -> MatchService:
    store = SQLiteStore(settings.db_path)
    client = FootballDataOrgClient(
        settings.football_data_api_key,
        limiter=fd_limiter or FOOTBALL_DATA_LIMITER,
    )
    llm = build_llm(settings)
    model_name = settings.ollama_model.strip() or settings.ollama_fallback_model.strip()
    player_status = None
    if settings.has_api_football_key:
        budget = StoreBudget(store, DEFAULT_DAILY_BUDGET)
        af_client = ApiFootballClient(
            settings.api_football_key,
            limiter=af_limiter or API_FOOTBALL_LIMITER,
            budget=budget,
        )
        player_status = PlayerStatusService(af_client, store, budget=budget)
    return MatchService(
        client=client,
        store=store,
        features=FeatureService(store),
        predictor=Predictor(),
        explainer=Explainer(llm, model_name, cache=SQLiteExplanationCache(store)),
        player_status=player_status,
    )
