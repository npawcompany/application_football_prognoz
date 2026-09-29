from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
import pytest

from football_prognoz.config import ROOT_DIR
from football_prognoz.data.football_data_org import RateLimiter
from football_prognoz.data.news import (
    GNewsClient,
    NewsError,
    RssClient,
    classify_topic,
    parse_gnews,
    parse_rss,
    plain_text,
)
from football_prognoz.data.store import SQLiteStore
from football_prognoz.domain.match import Match, MatchStatus, Score
from football_prognoz.services.facts import news_facts
from football_prognoz.services.news import (
    SRC_GNEWS,
    NewsService,
    gnews_query,
    mentions_team,
    team_phrases,
)

NEWS = ROOT_DIR / "data" / "samples" / "news"
NOW = datetime(2026, 9, 26, 10, 0, tzinfo=UTC)
BBC = "https://feeds.example/bbc.xml"
GUARDIAN = "https://feeds.example/guardian.xml"


def _text(name: str) -> str:
    return (NEWS / name).read_text(encoding="utf-8")


def _match() -> Match:
    return Match(
        id=1,
        competition_code="PL",
        utc_date=datetime(2026, 9, 26, 14, 0, tzinfo=UTC),
        status=MatchStatus.SCHEDULED,
        matchday=6,
        home_id=57,
        home_name="Arsenal FC",
        away_id=65,
        away_name="Manchester City FC",
        score=Score(None, None),
    )


class _Recorder:
    def __init__(self, routes: dict[str, httpx.Response]) -> None:
        self.routes = routes
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        for key, response in self.routes.items():
            if key in str(request.url):
                return response
        return httpx.Response(404)


def _rss_client(recorder: _Recorder) -> RssClient:
    return RssClient(
        {"BBC Sport": BBC, "The Guardian": GUARDIAN},
        http=httpx.Client(transport=httpx.MockTransport(recorder)),
    )


def _gnews_client(recorder: _Recorder, key: str = "secret-key") -> GNewsClient:
    return GNewsClient(
        key,
        http=httpx.Client(
            base_url="https://gnews.io/api/v4", transport=httpx.MockTransport(recorder)
        ),
        limiter=RateLimiter(1000),
    )


def _rss_routes() -> dict[str, httpx.Response]:
    return {
        "bbc.xml": httpx.Response(200, content=_text("rss_bbc.xml").encode()),
        "guardian.xml": httpx.Response(200, content=_text("rss_guardian.xml").encode()),
    }


# --- parsing ---------------------------------------------------------------------


def test_parse_gnews_sample() -> None:
    articles = parse_gnews(json.loads(_text("gnews_search.json")))
    assert len(articles) == 3
    first = articles[0]
    assert first.title.startswith("Arsenal sweat on Saka")
    assert first.source == "Example Sport"
    assert first.published_at == datetime(2026, 9, 24, 9, 15, tzinfo=UTC)


def test_parse_rss_strips_html_and_parses_rfc822_dates() -> None:
    bbc = parse_rss(_text("rss_bbc.xml"), "BBC Sport")
    assert [a.title for a in bbc][0] == "Man City without De Bruyne for Arsenal trip after ban"
    assert bbc[0].published_at == datetime(2026, 9, 24, 18, 12, 33, tzinfo=UTC)
    assert "&amp;" not in bbc[0].url
    guardian = parse_rss(_text("rss_guardian.xml"), "The Guardian")
    assert guardian[0].description == "Pep Guardiola says Manchester City can handle absences."


def test_parse_rss_rejects_broken_xml() -> None:
    with pytest.raises(NewsError) as info:
        parse_rss("<rss><channel><item>", "X")
    assert info.value.kind == "payload"


@pytest.mark.parametrize(
    ("text", "topic"),
    [
        ("Saka doubt with hamstring injury", "injury"),
        ("De Bruyne serves a one-match ban", "suspension"),
        ("Club sack manager after defeat", "manager"),
        ("Arsenal complete loan signing", "transfer"),
        ("Match preview", "other"),
    ],
)
def test_classify_topic(text: str, topic: str) -> None:
    assert classify_topic(text) == topic


def test_plain_text_limits_length() -> None:
    assert plain_text("<p>" + "a" * 500 + "</p>", 10) == "a" * 10


# --- team matching ----------------------------------------------------------------


def test_team_phrases_and_whole_word_matching() -> None:
    city = team_phrases("Manchester City FC")
    assert "manchester city" in city and "man city" in city
    arsenal = team_phrases("Arsenal FC")
    assert mentions_team("Man City without De Bruyne", city)
    assert mentions_team("Arsenal complete loan signing", arsenal)
    assert not mentions_team("Arsenalistas celebrate in Lisbon", arsenal)
    assert not mentions_team("Manchester United win", city)
    assert gnews_query("Arsenal FC") == '"arsenal" AND (football OR soccer)'


# --- clients ----------------------------------------------------------------------


def test_gnews_sends_key_in_header_not_url() -> None:
    recorder = _Recorder({"/search": httpx.Response(200, text=_text("gnews_search.json"))})
    client = _gnews_client(recorder)
    articles = client.search('"arsenal"', since=NOW)
    assert len(articles) == 3
    request = recorder.requests[0]
    assert request.headers["X-Api-Key"] == "secret-key"
    assert "secret-key" not in str(request.url)
    assert request.url.params["from"] == "2026-09-26T10:00:00Z"
    assert request.url.params["lang"] == "en"


@pytest.mark.parametrize(("status", "kind"), [(401, "auth"), (403, "quota"), (429, "rate_limit")])
def test_gnews_error_kinds(status: int, kind: str) -> None:
    recorder = _Recorder({"/search": httpx.Response(status, text=_text("gnews_error_quota.json"))})
    with pytest.raises(NewsError) as info:
        _gnews_client(recorder).search("x", since=NOW)
    assert info.value.kind == kind


def test_gnews_without_key_is_disabled_and_refuses() -> None:
    client = _gnews_client(_Recorder({}), key=" ")
    assert client.enabled is False
    with pytest.raises(NewsError):
        client.search("x", since=NOW)


def test_rss_http_error_and_network_error() -> None:
    client = _rss_client(_Recorder({"bbc.xml": httpx.Response(503)}))
    with pytest.raises(NewsError) as info:
        client.fetch("BBC Sport", BBC)
    assert info.value.kind == "http"

    def boom(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    broken = RssClient({"X": BBC}, http=httpx.Client(transport=httpx.MockTransport(boom)))
    with pytest.raises(NewsError) as info:
        broken.fetch("X", BBC)
    assert info.value.kind == "network"


# --- service ----------------------------------------------------------------------


def test_service_disabled_returns_none(tmp_path) -> None:
    service = NewsService(SQLiteStore(tmp_path / "n.db"))
    assert service.enabled is False
    assert service.report_for(_match()) is None


def test_rss_fallback_filters_by_team_and_caches(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "n.db")
    recorder = _Recorder(_rss_routes())
    service = NewsService(store, rss=_rss_client(recorder), now=lambda: NOW)
    report = service.report_for(_match())
    assert report is not None and report.provider == "rss"
    home_titles = [item.title for item in report.home.items]
    away_titles = [item.title for item in report.away.items]
    assert home_titles == [
        "Man City without De Bruyne for Arsenal trip after ban",
        "Arsenal complete loan signing",
    ]
    assert "Guardiola: Manchester City must cope without key men" in away_titles
    assert all("Chelsea" not in t for t in home_titles + away_titles)
    assert report.home.items[1].topic == "transfer"
    assert report.away.items[-1].topic == "suspension"
    assert report.sources == ("RSS спортивных изданий: BBC Sport, The Guardian",)
    calls = len(recorder.requests)
    service.report_for(_match())
    assert len(recorder.requests) == calls  # served from SQLite api_cache


def test_rss_feed_failure_becomes_note(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "n.db")
    routes = _rss_routes()
    routes["guardian.xml"] = httpx.Response(500)
    service = NewsService(store, rss=_rss_client(_Recorder(routes)), now=lambda: NOW)
    report = service.report_for(_match())
    assert report is not None
    assert "Лента The Guardian: HTTP 500." in report.notes
    assert report.home.items  # BBC still works


def test_gnews_flow_counts_budget_and_filters_old_items(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "n.db")
    recorder = _Recorder({"/search": httpx.Response(200, text=_text("gnews_search.json"))})
    service = NewsService(store, gnews=_gnews_client(recorder), now=lambda: NOW)
    report = service.report_for(_match())
    assert report is not None and report.provider == "gnews"
    assert len(recorder.requests) == 2  # one per team
    assert store.api_calls_today("gnews") == (2, False)
    titles = [item.title for item in report.home.items]
    assert "Old Arsenal story from last month" not in titles
    assert report.home.items[0].title == "Arteta: Arsenal ready for title test"
    assert report.home.items[1].topic == "injury"
    assert report.sources == (SRC_GNEWS,)
    service.report_for(_match())
    assert len(recorder.requests) == 2  # cached for 6 h


def test_gnews_quota_closes_day_and_falls_back_to_rss(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "n.db")
    routes = {"/search": httpx.Response(403, text=_text("gnews_error_quota.json"))}
    routes.update(_rss_routes())
    recorder = _Recorder(routes)
    service = NewsService(
        store,
        gnews=_gnews_client(recorder),
        rss=_rss_client(recorder),
        now=lambda: NOW,
    )
    report = service.report_for(_match())
    assert report is not None and report.provider == "rss"
    assert any("квота" in note for note in report.notes)
    assert store.api_calls_today("gnews")[1] is True
    searches = sum("/search" in str(r.url) for r in recorder.requests)
    service.report_for(_match())
    assert sum("/search" in str(r.url) for r in recorder.requests) == searches


def test_no_fresh_news_note(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "n.db")
    later = datetime(2026, 12, 1, tzinfo=UTC)
    service = NewsService(store, rss=_rss_client(_Recorder(_rss_routes())), now=lambda: later)
    report = service.report_for(_match())
    assert report is not None and not report.has_data()
    assert report.notes[-1] == "Свежих новостей за 7 дней не найдено."
    assert news_facts(report) is None


def test_news_facts_block(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "n.db")
    service = NewsService(store, rss=_rss_client(_Recorder(_rss_routes())), now=lambda: NOW)
    facts = news_facts(service.report_for(_match()))
    assert facts is not None
    assert facts["provider"] == "rss"
    assert facts["home"][0] == {
        "title": "Man City without De Bruyne for Arsenal trip after ban",
        "source": "BBC Sport",
        "published": "2026-09-24",
        "topic": "дисквалификация",
    }
    assert "не меняют вероятности" in facts["note"]
