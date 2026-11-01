import json
import sqlite3
import time
from datetime import datetime, timezone

import pytest

from memory_tools import MemoryStore, memory_context


def test_startup_contains_index_but_no_unrequested_facts(tmp_path, monkeypatch):
    monkeypatch.setenv("ARIANA_MEMORY_PATH", str(tmp_path / "memory.db"))
    MemoryStore().run({"action": "remember", "topic": "hobby", "fact": "Likes sailing"})
    data = json.loads(memory_context().split("\n")[-1])
    assert data["available_topics"] == ["hobby"]
    assert data["memories"] == []
    assert "Likes sailing" not in memory_context()


def test_repeated_save_preserves_followup_revision_and_expiry(tmp_path, monkeypatch):
    now = time.time()
    monkeypatch.setattr(time, "time", lambda: now)
    store = MemoryStore(tmp_path / "memory.db")
    request = {
        "action": "remember",
        "topic": "exam",
        "fact": "Physics exam Thursday",
        "kind": "event",
        "follow_up_at": datetime.fromtimestamp(now + 60, timezone.utc).isoformat(),
    }
    before = store.run(request)["details"][0]
    monkeypatch.setattr(time, "time", lambda: now + 120)
    assert store.claim_follow_up(before)
    after = store.run({"action": "remember", "topic": "exam", "fact": request["fact"]})[
        "details"
    ][0]
    assert after["revision"] == before["revision"]
    assert after["expires_at"] == before["expires_at"]
    assert after["followed_up"] == 1
    assert store.follow_up() is None


def test_duplicate_fact_under_another_topic_is_not_silently_merged(tmp_path):
    store = MemoryStore(tmp_path / "memory.db")
    store.run({"action": "remember", "topic": "hobby", "fact": "Likes sailing"})
    result = store.run(
        {"action": "remember", "topic": "weekends", "fact": "  likes   SAILING "}
    )
    assert result["duplicate_topic"] == "hobby"
    assert len(store.run({"action": "recall"})["memories"]) == 1


def test_importance_only_ranks_relevant_memories_and_migrates_old_database(tmp_path):
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE facts(topic TEXT PRIMARY KEY, fact TEXT NOT NULL, updated TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
        db.execute("INSERT INTO facts(topic,fact) VALUES ('a','Rover motor')")
    store = MemoryStore(path)
    store.run(
        {"action": "remember", "topic": "b", "fact": "Rover wheel", "importance": 5}
    )
    store.run({"action": "remember", "topic": "c", "fact": "Sailing", "importance": 5})
    assert (
        store.run({"action": "recall", "query": "rover"})["memories"][0]["topic"] == "b"
    )
    assert store.run({"action": "recall", "query": "banana"})["memories"] == []
    for value in [True, -1, 6, "high"]:
        with pytest.raises(ValueError):
            store.run(
                {
                    "action": "remember",
                    "topic": "bad",
                    "fact": "Bad",
                    "importance": value,
                }
            )


def test_mutations_do_not_return_unrelated_personal_facts(tmp_path):
    store = MemoryStore(tmp_path / "memory.db")
    store.run({"action": "remember", "topic": "hobby", "fact": "Likes sailing"})
    saved = store.run({"action": "remember", "topic": "rover", "fact": "Motor stalls"})
    assert saved["memories"] == [{"topic": "rover", "fact": "Motor stalls"}]
    assert store.run({"action": "pause"})["memories"] == []
    assert store.run({"action": "forget", "topic": "rover"})["memories"] == []
    assert len(store.run({"action": "recall"})["memories"]) == 1
