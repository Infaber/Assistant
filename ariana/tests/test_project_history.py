import sqlite3
import time

import pytest

from memory_tools import MemoryStore, memory_context


def project(store, fact="Motor driver overheats"):
    return store.run(
        {"action": "remember", "topic": "rover", "kind": "project", "fact": fact}
    )


def test_progress_is_bounded_dated_and_retrieves_previous_context(tmp_path):
    store = MemoryStore(tmp_path / "memory.db")
    project(store)
    for fact in [
        "Heatsink helped but cable loose",
        "Cable fixed; stalls under load",
        "Current limit increased; testing pending",
    ]:
        store.run({"action": "progress", "topic": "rover", "fact": fact})
    store.run({"action": "remember", "topic": "food", "fact": "Likes apples"})
    result = store.run({"action": "recall", "query": "heatsink"})
    assert result["memories"] == [
        {"topic": "rover", "fact": "Current limit increased; testing pending"}
    ]
    history = result["details"][0]["previous_summaries"]
    assert [row["summary"] for row in history] == [
        "Heatsink helped but cable loose",
        "Cable fixed; stalls under load",
    ]
    assert all(row["recorded_at"] <= time.time() for row in history)
    assert not store.run({"action": "recall", "query": "football"})["memories"]


def test_correction_and_forgetting_remove_history_not_just_current_fact(tmp_path):
    store = MemoryStore(tmp_path / "memory.db")
    project(store, "Uses ESP32")
    store.run({"action": "progress", "topic": "rover", "fact": "ESP32 tested"})
    project(store, "Correction: uses Raspberry Pi")
    assert not store.run({"action": "recall", "query": "ESP32"})["memories"]
    assert store.run({"action": "recall"})["details"][0]["previous_summaries"] == []
    store.run({"action": "progress", "topic": "rover", "fact": "Pi motor testing"})
    store.run({"action": "forget", "topic": "rover"})
    with sqlite3.connect(store.path) as db:
        assert db.execute("SELECT count(*) FROM project_history").fetchone()[0] == 0


def test_progress_preserves_pause_credentials_limits_and_existing_kind(tmp_path):
    store = MemoryStore(tmp_path / "memory.db")
    project(store)
    for request in [
        {"topic": "missing", "fact": "new"},
        {"topic": "rover", "fact": "AQ." + "X" * 40},
        {"topic": "rover", "fact": "new", "kind": "fact"},
        {"topic": "rover", "fact": "x" * 401},
    ]:
        with pytest.raises(ValueError):
            store.run({"action": "progress", **request})
    store.run({"action": "pause"})
    assert "error" in store.run({"action": "progress", "topic": "rover", "fact": "new"})
    assert not store.run({"action": "recall"})["details"][0]["previous_summaries"]


def test_history_expires_with_project_and_is_not_added_to_startup(
    tmp_path, monkeypatch
):
    now = time.time()
    monkeypatch.setattr(time, "time", lambda: now)
    path = tmp_path / "memory.db"
    monkeypatch.setenv("ARIANA_MEMORY_PATH", str(path))
    store = MemoryStore(path)
    project(store, "Earlier heatsink problem")
    store.run(
        {
            "action": "progress",
            "topic": "rover",
            "fact": "Testing pending",
            "retention_days": 1,
        }
    )
    assert "Earlier heatsink" not in memory_context()
    monkeypatch.setattr(time, "time", lambda: now + 86401)
    assert not store.run({"action": "recall"})["memories"]
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT count(*) FROM project_history").fetchone()[0] == 0


def test_repeated_progress_does_not_erase_pending_followup(tmp_path, monkeypatch):
    from datetime import datetime, timezone

    now = time.time()
    monkeypatch.setattr(time, "time", lambda: now)
    store = MemoryStore(tmp_path / "memory.db")
    result = store.run(
        {
            "action": "remember",
            "topic": "rover",
            "kind": "project",
            "fact": "Testing pending",
            "follow_up_at": datetime.fromtimestamp(now + 60, timezone.utc).isoformat(),
        }
    )
    original = result["details"][0]
    updated = store.run(
        {"action": "progress", "topic": "rover", "fact": "Testing pending"}
    )["details"][0]
    assert updated["revision"] == original["revision"]
    assert updated["follow_up_at"] == original["follow_up_at"]


@pytest.mark.asyncio
async def test_conversation_simulation_grades_project_history_not_only_dialogue(
    tmp_path,
):
    from types import SimpleNamespace
    from unittest.mock import Mock

    from simulation_tools import check_simulation_state

    store = MemoryStore(tmp_path / "simulation.db")
    project(store)
    expected = {
        "fixture": "conversation_memory",
        "memory_expectations": {"current_terms": ["heatsink"], "minimum_history": 1},
    }
    ctx = SimpleNamespace(
        userdata=lambda: expected,
        job_context=SimpleNamespace(
            primary_session=SimpleNamespace(userdata={"_memory_simulator": store.run})
        ),
        fail=Mock(),
    )
    await check_simulation_state(ctx)
    assert ctx.fail.called
    store.run(
        {
            "action": "progress",
            "topic": "rover",
            "fact": "Heatsink added, testing pending",
        }
    )
    ctx.fail.reset_mock()
    await check_simulation_state(ctx)
    ctx.fail.assert_not_called()
