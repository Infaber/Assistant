import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest

from memory_tools import MemoryStore


def iso(stamp):
    return datetime.fromtimestamp(stamp, timezone.utc).isoformat()


def test_existing_database_migrates_without_losing_facts(tmp_path):
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE facts(topic TEXT PRIMARY KEY,fact TEXT NOT NULL,updated TEXT DEFAULT CURRENT_TIMESTAMP)"
        )
        db.execute("INSERT INTO facts(topic,fact) VALUES ('name','Alex')")
    result = MemoryStore(path).run({"action": "recall"})
    assert result["memories"] == [{"topic": "name", "fact": "Alex"}]
    assert result["details"][0]["kind"] == "fact"


def test_types_correction_filter_and_forgetting_preserve_integrity(tmp_path):
    store = MemoryStore(tmp_path / "memory.db")
    store.run(
        {
            "action": "remember",
            "topic": "rover",
            "fact": "ESP32 motor driver overheats",
            "kind": "project",
        }
    )
    store.run(
        {
            "action": "remember",
            "topic": "humour",
            "fact": "Likes gentle teasing",
            "kind": "preference",
        }
    )
    store.run(
        {
            "action": "remember",
            "topic": "rover",
            "fact": "Raspberry Pi motor driver still overheats",
        }
    )
    result = store.run(
        {"action": "recall", "kind": "project", "query": "motor drivers"}
    )
    assert result["memories"] == [
        {"topic": "rover", "fact": "Raspberry Pi motor driver still overheats"}
    ]
    assert result["details"][0]["kind"] == "project"
    assert result["details"][0]["expires_at"] > time.time()
    store.run({"action": "forget", "topic": "rover"})
    assert store.run({"action": "recall", "kind": "project"})["details"] == []
    with sqlite3.connect(store.path) as db:
        assert (
            db.execute(
                "SELECT count(*) FROM memory_details WHERE topic='rover'"
            ).fetchone()[0]
            == 0
        )


def test_expired_events_are_removed_but_permanent_facts_stay(tmp_path, monkeypatch):
    now = time.time()
    monkeypatch.setattr(time, "time", lambda: now)
    store = MemoryStore(tmp_path / "memory.db")
    store.run(
        {
            "action": "remember",
            "topic": "exam",
            "fact": "An automation exam",
            "kind": "event",
            "retention_days": 1,
        }
    )
    store.run({"action": "remember", "topic": "name", "fact": "Alex"})
    monkeypatch.setattr(time, "time", lambda: now + 86401)
    assert store.run({"action": "recall"})["memories"] == [
        {"topic": "name", "fact": "Alex"}
    ]


def test_followups_are_single_use_across_sessions_and_corrections_invalidate_claim(
    tmp_path, monkeypatch
):
    now = time.time()
    monkeypatch.setattr(time, "time", lambda: now)
    store = MemoryStore(tmp_path / "memory.db")
    request = {
        "action": "remember",
        "topic": "exam",
        "fact": "Automation exam today",
        "kind": "event",
        "follow_up_at": iso(now + 60),
    }
    store.run(request)
    assert store.follow_up() is None
    monkeypatch.setattr(time, "time", lambda: now + 61)
    candidate = store.follow_up()
    store.run({**request, "fact": "Exam postponed", "follow_up_at": iso(now + 3600)})
    assert not store.claim_follow_up(candidate)
    monkeypatch.setattr(time, "time", lambda: now + 3601)
    candidate = store.follow_up()
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(
            pool.map(
                lambda _: MemoryStore(store.path).claim_follow_up(candidate), range(2)
            )
        )
    assert sorted(claims) == [False, True]
    assert MemoryStore(store.path).follow_up() is None


def test_pause_expiry_and_cross_topic_cooldown_block_proactive_followups(
    tmp_path, monkeypatch
):
    now = time.time()
    monkeypatch.setattr(time, "time", lambda: now)
    store = MemoryStore(tmp_path / "memory.db")
    for topic in ["exam", "rover"]:
        store.run(
            {
                "action": "remember",
                "topic": topic,
                "fact": "A planned follow-up",
                "kind": "event",
                "follow_up_at": iso(now + 60),
            }
        )
    monkeypatch.setattr(time, "time", lambda: now + 61)
    store.run({"action": "pause"})
    assert store.follow_up() is None
    store.run({"action": "resume"})
    assert store.claim_follow_up(store.follow_up(), 3600)
    assert not store.claim_follow_up(store.follow_up(), 3600)


@pytest.mark.parametrize(
    "change",
    [
        {"kind": "mood"},
        {"retention_days": True},
        {"retention_days": 500},
        {"follow_up_at": "next Tuesday"},
        {"follow_up_at": iso(time.time() - 60)},
        {"kind": "fact", "follow_up_at": iso(time.time() + 60)},
    ],
)
def test_invalid_metadata_never_partially_saves(tmp_path, change):
    store = MemoryStore(tmp_path / "memory.db")
    with pytest.raises(ValueError):
        store.run(
            {
                "action": "remember",
                "topic": "exam",
                "fact": "Automation exam",
                "kind": "event",
                **change,
            }
        )
    assert store.run({"action": "recall"})["memories"] == []


def test_current_google_key_format_cannot_be_saved(tmp_path):
    with pytest.raises(ValueError, match="credentials"):
        MemoryStore(tmp_path / "memory.db").run(
            {"action": "remember", "topic": "misc", "fact": "AQ." + "X" * 40}
        )
