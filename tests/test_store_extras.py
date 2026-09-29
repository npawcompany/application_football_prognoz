from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from football_prognoz.data.store import SQLiteExplanationCache, SQLiteStore


def test_api_payload_cache_respects_ttl(tmp_path: Path, monkeypatch) -> None:
    store = SQLiteStore(tmp_path / "c.db")
    store.put_api_payload("af:x", [{"a": 1}])
    assert store.get_api_payload("af:x", 1) == [{"a": 1}]
    later = datetime.now(UTC) + timedelta(hours=2)
    monkeypatch.setattr("football_prognoz.data.store._utcnow", lambda: later)
    assert store.get_api_payload("af:x", 1) is None
    assert store.get_api_payload("af:x", 3) == [{"a": 1}]


def test_daily_budget_counts_and_closes(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "b.db")
    assert store.consume_api_call("p", 2) is True
    assert store.consume_api_call("p", 2) is True
    assert store.consume_api_call("p", 2) is False
    assert store.api_calls_today("p") == (2, False)
    store.mark_api_exhausted("q")
    assert store.consume_api_call("q", 100) is False


def test_budget_and_mapping_survive_clear_all(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "m.db")
    store.consume_api_call("api_football", 90)
    store.upsert_af_team(57, 42, fd_name="Arsenal FC", af_name="Arsenal", method="t")
    store.upsert_af_fixture(1, 99, af_league_id=39, season=2026)
    store.put_api_payload("af:y", {"b": 2})
    store.put_llm("k", {"parsed": {}, "model": "m"})
    store.clear_all()
    assert store.api_calls_today("api_football") == (1, False)
    assert store.get_af_team(57) == 42
    assert store.get_af_fixture(1) == 99
    assert store.get_api_payload("af:y", 10) is None
    assert store.get_llm("k") is None


def test_explanation_cache_roundtrip(tmp_path: Path) -> None:
    cache = SQLiteExplanationCache(SQLiteStore(tmp_path / "l.db"))
    assert cache.get("k") is None
    cache.put("k", {"parsed": {"summary": "x"}, "model": "gpt-oss:120b"})
    assert cache.get("k") == {"parsed": {"summary": "x"}, "model": "gpt-oss:120b"}


def test_existing_database_gets_new_tables(tmp_path: Path) -> None:
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE meta (cache_key TEXT PRIMARY KEY, fetched_at TEXT, etag TEXT)")
    store = SQLiteStore(path)
    store.upsert_af_team(1, 2, fd_name="a", af_name="b", method="m")
    assert store.get_af_team(1) == 2
