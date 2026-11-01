import time
from datetime import datetime, timezone

import pytest
from test_companion import settings

from companion import CheckInPolicy
from companion_followups import FollowUps
from memory_tools import MemoryStore


def due(store, topic, importance, now):
    return store.run(
        {
            "action": "remember",
            "topic": topic,
            "fact": topic + " project pending",
            "kind": "project",
            "importance": importance,
            "follow_up_at": datetime.fromtimestamp(now + 1, timezone.utc).isoformat(),
        }
    )["details"][0]


@pytest.mark.asyncio
async def test_priority_filter_orders_due_events_without_consuming_lower_priorities(
    tmp_path, monkeypatch
):
    now = time.time()
    monkeypatch.setattr(time, "time", lambda: now)
    store = MemoryStore(tmp_path / "memory.db")
    low = due(store, "rover", 2, now)
    high = due(store, "exam", 5, now)
    monkeypatch.setattr(time, "time", lambda: now + 2)
    followups = FollowUps(store)
    chosen = await followups.prepare(100, {}, minimum_importance=4)
    assert chosen["topic"] == "exam"
    assert await followups.claim(chosen, {}, minimum_importance=4)
    assert store.follow_up(minimum_importance=4) is None
    assert store.follow_up()["topic"] == low["topic"]
    assert high["importance"] == 5


def test_claim_rechecks_changed_priority_and_current_threshold(tmp_path, monkeypatch):
    now = time.time()
    monkeypatch.setattr(time, "time", lambda: now)
    store = MemoryStore(tmp_path / "memory.db")
    candidate = due(store, "rover", 5, now)
    monkeypatch.setattr(time, "time", lambda: now + 2)
    store.run(
        {
            "action": "remember",
            "topic": "rover",
            "fact": "rover project pending",
            "importance": 1,
        }
    )
    assert not store.claim_follow_up(candidate, minimum_importance=4)
    assert store.follow_up()["followed_up"] == 0


def test_priority_configuration_is_bounded_and_old_clients_remain_compatible():
    policy = CheckInPolicy()
    policy.configure(settings(), 0)
    assert policy.minimum_importance == 1
    policy.configure(settings(minimum_importance=4), 1)
    assert policy.minimum_importance == 4
    policy.configure(settings(), 2)
    assert policy.minimum_importance == 4
    for value in [0, 6, True, "5"]:
        with pytest.raises(ValueError):
            policy.configure(settings(minimum_importance=value), 2)
        assert policy.minimum_importance == 4


@pytest.mark.asyncio
async def test_raising_threshold_during_claim_cannot_dispatch_an_old_low_priority_candidate(
    monkeypatch,
):
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from test_companion import bridge

    import companion

    b = bridge()
    b.session.agent_state, b.session.user_state = "listening", "away"
    b.policy.configure(settings(quiet_start=0, quiet_end=0), 0)
    b.policy.lease_until = 2000
    monkeypatch.setattr(companion.time, "monotonic", lambda: 1000)

    async def claim(*args):
        b.policy.minimum_importance = 5
        return True

    b.followups = SimpleNamespace(
        prepare=AsyncMock(
            return_value={
                "topic": "rover",
                "fact": "Pending",
                "follow_up_at": 1,
                "importance": 2,
            }
        ),
        claim=AsyncMock(side_effect=claim),
    )
    count = 0

    async def sleep(_):
        nonlocal count
        count += 1
        if count > 1:
            raise asyncio.CancelledError

    monkeypatch.setattr(companion.asyncio, "sleep", sleep)
    with pytest.raises(asyncio.CancelledError):
        await b.check_in_loop()
    b.session.generate_reply.assert_not_called()
    assert not b.policy.awaiting_user
