"""LLM validation for the markets table (B) and the news summary (D); RSS robustness."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from football_prognoz.ai.explainer import Explainer, ExplanationError, parse_markets_part
from football_prognoz.ai.news_summary import (
    NewsSummarizer,
    NewsSummaryError,
    build_news_prompt,
    parse_news_summary,
)
from football_prognoz.ai.ollama import LLMReply
from football_prognoz.data.news import NewsError, parse_rss
from football_prognoz.domain.match import Match, MatchStatus, Score
from football_prognoz.domain.news import NewsItem, NewsReport, TeamNews
from football_prognoz.domain.prediction import MatchFeatures, Probabilities
from football_prognoz.models.markets import build_markets
from football_prognoz.services.news import gnews_query, mentions_team, team_phrases

PROBS = Probabilities(0.5, 0.26, 0.24)
TABLE = build_markets(1.6, 1.1, PROBS, sample_matches=12)
MATCH = Match(
    1,
    "PL",
    datetime(2026, 10, 3, 14, tzinfo=UTC),
    MatchStatus.TIMED,
    7,
    57,
    "Arsenal FC",
    65,
    "Manchester City FC",
    Score(None, None),
)
FEATURES = MatchFeatures("WWDLW", "WLWDW", 1600, 1580, "", 2, 3, 1.8, 0.9, 1.6, 1.1, 12)


def _good(**override) -> dict:
    body = {
        "summary": "Коротко.",
        "home_factors": [],
        "away_factors": [],
        "favorite": "1",
        "verdict": "Хозяева чуть сильнее.",
        "confidence": "medium",
        "confidence_reason": "Выборка 12 матчей.",
        "market_comments": [
            {"market": "1x2_1", "comment": "Хозяева фавориты: 50% по модели."},
            {"market": "total_over_2.5", "comment": "Голы примерно поровну."},
        ],
        "top_markets": [
            {"market": "dc_1x", "reason": "Дома стабильны."},
            {"market": "total_over_1.5", "reason": "Результативные матчи."},
            {"market": "1x2_1", "reason": "Выше Elo."},
        ],
        "risks": ["Близкие вероятности."],
    }
    body.update(override)
    return body


def test_valid_market_part_is_kept() -> None:
    part = parse_markets_part(_good(), TABLE)
    assert [c["market"] for c in part["top_markets"]] == ["dc_1x", "total_over_1.5", "1x2_1"]
    assert part["risks"] == ["Близкие вероятности."]


@pytest.mark.parametrize(
    ("override", "fragment"),
    [
        ({"top_markets": [{"market": "total_over_7.5", "reason": "x"}]}, "нет в таблице"),
        ({"top_markets": [{"market": "1x2_1", "reason": "x"}]}, "ровно 3"),
        (
            {"market_comments": [{"market": "corners_over_9.5", "comment": "Много угловых."}]},
            "нет в таблице",  # no API-Football data -> not commentable
        ),
        (
            {"market_comments": [{"market": "1x2_1", "comment": "Шанс хозяев 70%."}]},
            "не совпадает",  # the LLM may not change numbers
        ),
        (
            {"top_markets": [{"market": "1x2_1", "reason": "a"}] * 3},
            "повторяется",
        ),
    ],
)
def test_invalid_market_references_are_rejected(override: dict, fragment: str) -> None:
    from football_prognoz.ai.explainer import _Invalid

    with pytest.raises(_Invalid, match=fragment):
        parse_markets_part(_good(**override), TABLE)


class _LLM:
    def __init__(self, *answers: dict) -> None:
        self.answers = [json.dumps(a, ensure_ascii=False) for a in answers]
        self.users: list[str] = []

    def chat(self, system: str, user: str, **_kwargs) -> LLMReply:
        self.users.append(user)
        return LLMReply(self.answers.pop(0), "gpt-oss:120b", notice="Модель X — ответила Y.")


def test_explainer_sends_the_table_retries_once_and_never_changes_numbers() -> None:
    bad = _good(top_markets=[{"market": "made_up", "reason": "x"}] * 3)
    llm = _LLM(bad, _good())
    result = Explainer(llm, "gpt-oss:120b").explain(MATCH, FEATURES, PROBS, markets=TABLE)
    assert result is not None and len(llm.users) == 2
    assert "made_up" in llm.users[1] and "rejected" in llm.users[1]
    sent = json.loads(llm.users[0])
    assert {m["id"] for m in sent["markets"]} == TABLE.available_keys
    assert any(m["id"] == "corners_over_9.5" for m in sent["markets_unavailable"])
    assert sent["probabilities"]["home"] == 0.5  # unchanged model numbers go in
    assert result.notice == "Модель X — ответила Y."
    assert TABLE.by_key("1x2_1").win == pytest.approx(0.5)

    with pytest.raises(ExplanationError):
        Explainer(_LLM(bad, bad), "gpt-oss:120b").explain(MATCH, FEATURES, PROBS, markets=TABLE)


# --- news summary -------------------------------------------------------------------

NOW = datetime(2026, 10, 1, 12, tzinfo=UTC)
REPORT = NewsReport(
    TeamNews(
        "Arsenal",
        (
            NewsItem(
                "Saka doubt with hamstring injury",
                "BBC Sport",
                "u",
                NOW,
                "injury",
                summary="Winger limped off.",
            ),
            NewsItem("Arteta praises squad depth", "Sky Sports", "u", NOW - timedelta(days=1)),
        ),
    ),
    TeamNews(
        "Man City",
        (NewsItem("Man City found guilty of breaches", "ESPN", "u", NOW, "club"),),
    ),
    provider="rss",
)


def _summary(**override) -> dict:
    body = {
        "summary": "По данным СМИ, у Арсенала под вопросом Сака. У Сити внимание к делу АПЛ.",
        "home": {"points": [{"text": "Сака под вопросом", "headline": "h1"}], "relevance": "Да."},
        "away": {"points": [{"text": "Решение АПЛ", "headline": "a1"}], "relevance": "Слабо."},
        "stale_note": "",
    }
    body.update(override)
    return body


def test_news_prompt_has_ids_and_summaries() -> None:
    prompt = build_news_prompt(MATCH, REPORT)
    assert [h["id"] for h in prompt["headlines"]] == ["h1", "h2", "a1"]
    assert prompt["headlines"][0]["summary"] == "Winger limped off."


def test_news_summary_cites_only_listed_headlines() -> None:
    parsed = parse_news_summary(json.dumps(_summary(), ensure_ascii=False), REPORT, "m")
    assert parsed.cited == {
        "h1": "Saka doubt with hamstring injury",
        "a1": "Man City found guilty of breaches",
    }
    from football_prognoz.ai.explainer import _Invalid

    wrong_team = _summary(home={"points": [{"text": "x", "headline": "a1"}]})
    missing = _summary(away={"points": [{"text": "x", "headline": "a7"}]})
    percent = _summary(summary="Шансы Арсенала выросли до 60%.")
    fake_quote = _summary(summary="СМИ пишут «Haaland injured before derby clash».")
    for body in (wrong_team, missing, percent, fake_quote):
        with pytest.raises(_Invalid):
            parse_news_summary(json.dumps(body, ensure_ascii=False), REPORT, "m")


def test_news_summarizer_retries_then_fails_and_skips_without_news() -> None:
    bad = _summary(home={"points": [{"text": "x", "headline": "h9"}]})
    ok = NewsSummarizer(_LLM(bad, _summary())).summarize(MATCH, REPORT)
    assert ok is not None and ok.notice
    with pytest.raises(NewsSummaryError):
        NewsSummarizer(_LLM(bad, bad)).summarize(MATCH, REPORT)
    empty = NewsReport(TeamNews("A"), TeamNews("B"), provider="rss")
    assert NewsSummarizer(_LLM()).summarize(MATCH, empty) is None
    assert NewsSummarizer(None).summarize(MATCH, REPORT) is None


# --- RSS robustness and team aliases -----------------------------------------------

ITEM = (
    "<item><title><![CDATA[Man City guilty verdict]]></title>"
    "<description>Fans & pundits react</description>"
    "<link>https://www.espn.com/soccer/story/1</link>"
    "<pubDate>Tue, 29 Sep 2026 16:51:46 EST</pubDate></item>"
)


def test_rss_tolerates_bom_bare_ampersand_and_html_entities() -> None:
    feed = "\ufeff  <?xml version='1.0'?><rss><channel>" + ITEM + "</channel></rss>"
    items = parse_rss(feed.encode("utf-8"), "ESPN")
    assert items[0].title == "Man City guilty verdict"
    assert items[0].description == "Fans & pundits react"
    assert items[0].published_at == datetime(2026, 9, 29, 21, 51, 46, tzinfo=UTC)
    nbsp = parse_rss(
        ("<rss><channel>" + ITEM.replace("Fans", "Fans&nbsp;") + "</channel></rss>"), "X"
    )
    assert nbsp[0].title == "Man City guilty verdict"


def test_rss_regex_fallback_and_html_page_error() -> None:
    broken = "<rss><channel>" + ITEM + "<item><title>Unclosed</title></channel>"
    items = parse_rss(broken, "ESPN")
    assert [a.title for a in items] == ["Man City guilty verdict"]
    with pytest.raises(NewsError, match="HTML"):
        parse_rss(b"<!DOCTYPE html><html><body>Consent</body></html>", "ESPN")
    latin = (
        "<?xml version='1.0' encoding='windows-1252'?><rss><channel>"
        + ITEM.replace("verdict", "verdict – reaction")
        + "</channel></rss>"
    )
    decoded = parse_rss(latin.encode("cp1252"), "ESPN")
    assert decoded[0].title == "Man City guilty verdict – reaction"


def test_team_aliases_find_lask_and_avoid_city_names() -> None:
    lask = team_phrases("LASK Linz")
    assert "lask" in lask
    assert mentions_team("LASK stun Salzburg in Austrian Bundesliga", lask)
    assert gnews_query("LASK Linz") == '("lask linz" OR "lask") AND (football OR soccer)'
    city = team_phrases("Manchester City FC")
    assert "manchester" not in city
    assert not mentions_team("Manchester United beat Chelsea", city)
    assert "betis" in team_phrases("Real Betis Balompié")
