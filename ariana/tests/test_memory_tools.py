import sqlite3
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from memory_tools import MemoryStore, memory_context, memory_manage


def test_persists_corrects_and_forgets(tmp_path):
    path = tmp_path / "memory.sqlite3"
    store = MemoryStore(path)
    store.run(
        {"action": "remember", "topic": "Side project", "fact": "Building Northstar"}
    )
    reopened = MemoryStore(path)
    assert (
        reopened.run({"action": "recall", "topic": "northstar"})["memories"][0]["topic"]
        == "side project"
    )
    reopened.run(
        {"action": "remember", "topic": "Side project", "fact": "Building Moonbeam"}
    )
    assert reopened.run({"action": "recall"})["memories"] == [
        {"topic": "side project", "fact": "Building Moonbeam"}
    ]
    reopened.run({"action": "forget", "topic": "side project"})
    assert reopened.run({"action": "recall"})["memories"] == []
    assert path.stat().st_mode & 0o777 == 0o600


def test_pause_survives_restart_allows_forget(tmp_path):
    store = MemoryStore(tmp_path / "m.db")
    store.run({"action": "remember", "topic": "hobby", "fact": "Hiking"})
    store.run({"action": "pause"})
    reopened = MemoryStore(store.path)
    assert "error" in reopened.run(
        {"action": "remember", "topic": "city", "fact": "Oslo"}
    )
    reopened.run({"action": "forget", "topic": "hobby"})
    assert reopened.run({"action": "recall"})["memories"] == []
    reopened.run({"action": "resume"})
    assert reopened.run({"action": "remember", "topic": "city", "fact": "Oslo"})[
        "success"
    ]


@pytest.mark.parametrize(
    "payload",
    [
        {"action": "delete"},
        {"action": "forget"},
        {"action": "remember", "topic": "password", "fact": "sensitive"},
        {"action": "remember", "topic": "project", "fact": ""},
        {"action": "remember", "topic": "project", "fact": "x" * 401},
    ],
)
def test_invalid_requests_do_not_create_storage(tmp_path, payload):
    path = tmp_path / "m.db"
    with pytest.raises(ValueError):
        MemoryStore(path).run(payload)
    assert not path.exists()


def test_concurrent_writes_preserve_facts(tmp_path):
    path = tmp_path / "m.db"
    # Initialize schema before racing independent writer processes/connections.
    MemoryStore(path).run({"action": "recall"})
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(
            pool.map(
                lambda i: MemoryStore(path).run(
                    {"action": "remember", "topic": f"project {i}", "fact": f"Idea {i}"}
                ),
                range(30),
            )
        )
    assert len(MemoryStore(path).run({"action": "recall"})["memories"]) == 30


def test_bounded_memory_does_not_silently_evict(tmp_path):
    store = MemoryStore(tmp_path / "m.db")
    for i in range(100):
        store.run({"action": "remember", "topic": f"topic {i}", "fact": "Fact"})
    assert "error" in store.run({"action": "remember", "topic": "new", "fact": "New"})
    assert store.run({"action": "remember", "topic": "topic 0", "fact": "Corrected"})[
        "success"
    ]
    assert len(store.run({"action": "recall"})["memories"]) == 100


def test_corrupt_database_preserved_and_startup_survives(tmp_path, monkeypatch):
    path = tmp_path / "bad.db"
    path.write_bytes(b"broken original database")
    monkeypatch.setenv("ARIANA_MEMORY_PATH", str(path))
    assert "unavailable" in memory_context()
    assert path.read_bytes() == b"broken original database"
    with pytest.raises(sqlite3.Error):
        MemoryStore(path).run({"action": "recall"})


def test_startup_loads_bounded_context_from_disk(tmp_path, monkeypatch):
    path = tmp_path / "m.db"
    monkeypatch.setenv("ARIANA_MEMORY_PATH", str(path))
    monkeypatch.setattr("memory_tools.read_preferences", lambda: {"display_name": "QA"})
    store = MemoryStore(path)
    for i in range(25):
        store.run({"action": "remember", "topic": f"topic {i}", "fact": f"Fact {i}"})
    import json

    data = json.loads(memory_context().split("\n")[-1])
    assert data["total_memories"] == 25
    assert len(data["memories"]) == 20
    assert data["preferences"] == {"display_name": "QA"}


def test_relevant_local_retrieval_omits_unrelated_and_corrects(tmp_path):
    store = MemoryStore(tmp_path / "relevant.db")
    for topic, fact in [
        ("esp32", "Building an ESP32 controller"),
        ("lighting", "LED strips connected to Home Assistant"),
        ("sensors", "Temperature sensors for automation"),
        ("sports", "Enjoys football"),
        ("holiday", "Visited Italy"),
    ]:
        store.run({"action": "remember", "topic": topic, "fact": fact})
    result = store.run({"action": "recall", "query": "my ESP32 project"})["memories"]
    assert result[0]["topic"] == "esp32"
    assert {item["topic"] for item in result} == {"esp32", "lighting", "sensors"}
    assert store.run({"action": "recall", "query": "bananas"})["memories"] == []
    assert (
        store.run({"action": "recall", "query": "what do you remember about me"})[
            "memories"
        ]
        == []
    )
    store.run(
        {"action": "remember", "topic": "esp32", "fact": "ESP32 prototype finished"}
    )
    assert (
        store.run({"action": "recall", "query": "esp32"})["memories"][0]["fact"]
        == "ESP32 prototype finished"
    )


def test_unlabelled_credentials_are_rejected(tmp_path):
    store = MemoryStore(tmp_path / "memory.sqlite3")
    with pytest.raises(ValueError, match="credentials"):
        store.run({"action": "remember", "topic": "misc", "fact": "AIza" + "x" * 35})


@pytest.mark.asyncio
async def test_invalid_memory_protocol_cannot_fake_success():
    called = []
    ctx = SimpleNamespace(
        session=SimpleNamespace(
            userdata={"_memory_simulator": lambda request: called.append(request)}
        )
    )
    result = await memory_manage._func(ctx, "save", "project", "Northstar")
    assert result["error"] and called == []
