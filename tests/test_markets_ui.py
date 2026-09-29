"""UI: markets table card, AI top markets, «Итог по новостям» block."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from test_views import _blob, _detail, _forecast

from football_prognoz.domain.markets import NOTE_NO_KEY
from football_prognoz.domain.news import (
    NewsItem,
    NewsPoint,
    NewsReport,
    NewsSummary,
    TeamNews,
    TeamNewsTakeaway,
)
from football_prognoz.domain.prediction import Explanation, MarketComment, Probabilities
from football_prognoz.models.markets import build_markets
from football_prognoz.services.llm_policy import FINISHED_NONE_TEXT
from football_prognoz.ui.components import markets_table as mt
from football_prognoz.ui.components.ai_analysis import AI_LOADING, AI_NOTE, resolve_ai_state


def _table():
    return build_markets(1.6, 1.1, Probabilities(0.45, 0.27, 0.28), sample_matches=12)


def test_markets_card_popular_rows_and_unavailable_note() -> None:
    mt._FILTERS.clear()
    card = mt.markets_card(_table(), match_id=1, window_width=1400)
    blob = _blob(card)
    assert "Таблица ставок" in blob
    assert "Популярные" in blob and "Все" in blob
    assert "Обе забьют — да" in blob or "Обе забьют" in blob
    # set pieces are shown as unavailable without an API-Football key
    mt._FILTERS[1] = "corners"
    blob = _blob(mt.markets_card(_table(), match_id=1, window_width=1400))
    assert NOTE_NO_KEY in blob


def test_markets_card_filter_switch_is_remembered() -> None:
    mt._FILTERS.clear()
    card = mt.MarketsTableCard(_table(), match_id=7, window_width=1400)
    popular = len(mt.visible_rows(card.table, mt.FILTER_POPULAR))
    card.select(mt.FILTER_ALL)
    assert mt._FILTERS[7] == mt.FILTER_ALL
    assert len(mt.visible_rows(card.table, mt.FILTER_ALL)) > popular
    again = mt.MarketsTableCard(_table(), match_id=7, window_width=1400)
    assert again.selected == mt.FILTER_ALL


def test_match_detail_shows_markets_and_ai_top_markets() -> None:
    mt._FILTERS.clear()
    table = _table()
    keys = [m.key for m in table.sorted() if m.available][:3]
    explanation = Explanation(
        text="Коротко.",
        model="gpt-oss:120b",
        top_markets=tuple(MarketComment(k, f"обоснование {k}") for k in keys),
        risks=("Ротация состава",),
        notice="Модель X недоступна (402) — ответила gpt-oss:20b.",
        generated_at=datetime(2026, 9, 29, 12, 0, tzinfo=UTC),
    )
    forecast = replace(_forecast(), markets=table, explanation=explanation)
    blob = _detail(forecast)
    assert "Таблица ставок" in blob
    assert "Наиболее обоснованные рынки" in blob
    assert f"обоснование {keys[0]}" in blob
    assert "Ротация состава" in blob
    assert "ответила gpt-oss:20b" in blob
    assert "Сгенерировано" in blob and "gpt-oss:120b" in blob


def test_finished_match_without_saved_analysis_shows_note() -> None:
    forecast = replace(_forecast(), analysis_note=FINISHED_NONE_TEXT)
    assert resolve_ai_state(forecast, None, None) == AI_NOTE
    assert FINISHED_NONE_TEXT in _detail(forecast)


def _news() -> NewsReport:
    return NewsReport(
        home=TeamNews(
            "Arsenal",
            (
                NewsItem(
                    "Saka doubt for City clash",
                    "BBC Sport",
                    "https://x",
                    datetime(2026, 9, 24, tzinfo=UTC),
                    "injury",
                ),
            ),
        ),
        away=TeamNews("Man City"),
        provider="rss",
    )


def test_news_summary_block_renders_points_and_citation() -> None:
    summary = NewsSummary(
        text="У хозяев под вопросом Сака.",
        home=TeamNewsTakeaway(
            points=(NewsPoint("Сака может пропустить матч", "h1"),),
            relevance="ослабляет атаку",
        ),
        away=TeamNewsTakeaway(),
        model="gpt-oss:120b",
        stale_note="Про гостей свежих новостей нет.",
        generated_at=datetime(2026, 9, 29, 9, 0, tzinfo=UTC),
        cited={"h1": "Saka doubt for City clash"},
    )
    blob = _detail(replace(_forecast(), news=_news(), news_summary=summary))
    assert "Итог по новостям" in blob
    assert "Сака может пропустить матч" in blob
    assert "по заголовку: «Saka doubt for City clash»" in blob
    assert "Значение для матча: ослабляет атаку" in blob
    assert "Про гостей свежих новостей нет." in blob
    assert "Сгенерировано" in blob


def test_news_summary_loading_and_no_llm_note() -> None:
    loading = _detail(replace(_forecast(), news=_news()), ai_state=AI_LOADING)
    assert "Идёт анализ новостей…" in loading
    note = _detail(
        replace(_forecast(), news=_news(), news_note="Итог недоступен: нет ключа Ollama.")
    )
    assert "Итог недоступен: нет ключа Ollama." in note
