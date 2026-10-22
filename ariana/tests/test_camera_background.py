import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from camera_events import CameraEventBridge
from camera_settings import CameraPermission


def bridge(state="idle", user="away"):
    companion = SimpleNamespace(
        session=SimpleNamespace(agent_state=state, user_state=user),
        policy=SimpleNamespace(last_activity=time.monotonic() - 10),
        uploads={},
        speech=None,
        closed=False,
    )
    result = CameraEventBridge(companion, {"sensor.bedroom_person_count": "person"})
    result.status = "connected"
    result.announce = AsyncMock()
    return result


def queue_empty_arrival(b, text="Hey, welcome back."):
    entity = next(iter(b.sources))
    b.transitions.states[entity] = "1"
    b.pending_arrival = b.arrival_tracks.arrival(entity, 0, 1, time.monotonic())
    b.pending = (text, time.monotonic() + 60)


def test_permission_survives_new_sessions_and_is_scoped_and_revocable(tmp_path):
    store = CameraPermission(tmp_path / "speech.json")
    sources = {"sensor.bedroom_person_count": "person"}
    assert not store.enabled("bedroom", sources)
    store.save(True, "bedroom", sources)
    assert CameraPermission(store.path).enabled("bedroom", sources)
    assert not store.enabled("other", sources)
    assert not store.enabled("bedroom", {"sensor.different": "person"})
    assert store.path.stat().st_mode & 0o077 == 0
    store.save(False, "bedroom", sources)
    assert not CameraPermission(store.path).enabled("bedroom", sources)
    store.path.write_text("not json")
    assert not store.enabled("bedroom", sources)


def test_new_bridge_restores_saved_permission_and_other_session_revokes():
    first = bridge()
    first.permission.save(True, first.transitions.camera, first.sources)
    second = bridge()
    assert second.enabled
    first.permission.save(False, first.transitions.camera, first.sources)
    second.sync_permission()
    assert not second.enabled


@pytest.mark.asyncio
async def test_first_greeting_needs_no_user_turn_or_microphone():
    b = bridge(state="idle", user="away")
    b.enabled = True
    b.pending = ("Hey, welcome back.", time.monotonic() + 60)
    assert b.idle()
    await b.flush_pending()
    b.announce.assert_awaited_once_with("Hey, welcome back.")
    assert b.pending is None
    await b.flush_pending()
    assert b.announce.await_count == 1


@pytest.mark.asyncio
async def test_arrival_waits_for_conversation_to_end_instead_of_disappearing():
    b = bridge(state="speaking")
    b.enabled = True
    b.pending = ("Hey, welcome back.", time.monotonic() + 60)
    await b.flush_pending()
    b.announce.assert_not_awaited()
    assert b.pending
    b.companion.session.agent_state = "listening"
    b.companion.policy.last_activity = time.monotonic()
    await b.flush_pending()
    b.announce.assert_not_awaited()
    b.companion.policy.last_activity = time.monotonic() - 4
    await b.flush_pending()
    b.announce.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["expired", "disabled", "offline"])
async def test_stale_or_disallowed_greetings_are_not_replayed(reason):
    b = bridge()
    b.enabled = True
    b.pending = ("Hey, welcome back.", time.monotonic() + 60)
    if reason == "expired":
        b.pending = ("Hello", time.monotonic() - 1)
    if reason == "disabled":
        b.enabled = False
    if reason == "offline":
        b.status = "recovering"
    if reason == "cooldown":
        b.transitions.last_spoken = time.monotonic()
    await b.flush_pending()
    b.announce.assert_not_awaited()
    assert b.pending is None


@pytest.mark.asyncio
async def test_failed_speech_is_not_blindly_retried():
    b = bridge()
    b.enabled = True
    b.announce.side_effect = RuntimeError("provider details must stay private")
    b.pending = ("Hey, welcome back.", time.monotonic() + 60)
    await b.flush_pending()
    await b.flush_pending()
    b.announce.assert_awaited_once()
    assert b.pending is None and "did not complete" in b.last_speech_error
    assert "provider details" not in b.last_speech_error


@pytest.mark.asyncio
async def test_delivery_loop_releases_queued_greeting_after_idle_without_new_event(
    monkeypatch,
):
    import camera_events

    b = bridge(state="thinking")
    b.permission.save(True, b.transitions.camera, b.sources)
    b.sync_permission()
    b.pending = ("Hey, welcome back.", time.monotonic() + 60)
    sleeps = 0

    async def tick(_):
        nonlocal sleeps
        sleeps += 1
        b.companion.session.agent_state = "idle"
        if sleeps >= 2:
            b.companion.closed = True

    monkeypatch.setattr(camera_events.asyncio, "sleep", tick)
    await b.delivery_loop()
    b.announce.assert_awaited_once_with("Hey, welcome back.")


@pytest.mark.asyncio
async def test_departure_cancels_queued_arrival_but_old_data_does_not():
    b = bridge(state="speaking")
    b.transitions.greetings = True
    b.enabled = True
    entity = next(iter(b.sources))
    now = time.time()
    b.transitions.states[entity] = "0"
    b.transitions.observed[entity] = now - 3
    b.transitions.empty_since[entity] = now - 10
    await b.observe(entity, {"state": "1", "last_updated": now - 2})
    assert b.pending
    await b.observe(entity, {"state": "0", "last_updated": now - 3})
    assert b.pending
    await b.observe(entity, {"state": "0", "last_updated": now - 1})
    assert b.pending is None
    b.companion.session.agent_state = "idle"
    await b.flush_pending()
    b.announce.assert_not_awaited()


@pytest.mark.asyncio
async def test_second_arrival_is_retained_through_cooldown_in_same_session():
    b = bridge()
    b.transitions.greetings = True
    b.transitions.cooldown = 15
    b.enabled = True
    entity = next(iter(b.sources))
    now = time.time()
    await b.observe(entity, {"state": "0", "last_updated": now - 25})
    await b.observe(entity, {"state": "1", "last_updated": now - 20})
    assert b.announce.await_count == 1
    await b.observe(entity, {"state": "0", "last_updated": now - 10})
    await b.observe(entity, {"state": "1", "last_updated": now - 5})
    assert b.pending and b.last_decision == "waiting_for_cooldown"
    b.transitions.last_spoken = time.monotonic() - 16
    await b.flush_pending()
    assert b.announce.await_count == 2
    assert b.pending is None


@pytest.mark.asyncio
async def test_brief_detection_flicker_does_not_repeat_welcome():
    b = bridge()
    b.transitions.greetings = True
    b.enabled = True
    entity = next(iter(b.sources))
    now = time.time()
    await b.observe(entity, {"state": "1", "last_updated": now - 10})
    await b.observe(entity, {"state": "0", "last_updated": now - 2})
    await b.observe(entity, {"state": "1", "last_updated": now - 1})
    b.announce.assert_not_awaited()
    assert b.last_decision == "brief_detection_gap"


@pytest.mark.asyncio
async def test_fresh_verified_identity_personalizes_greeting():
    b = bridge()
    b.named_greetings = True
    b.transitions.greetings = True
    b.enabled = True
    b.identity_lookup = AsyncMock(
        return_value={
            "current_presence_verified": True,
            "person_track_ids": ["track-1"],
            "person_count": 1,
            "current_recognized_people": [
                {"reported_name": "Alex", "confidence": 0.99, "track_id": "track-1"}
            ],
        }
    )
    queue_empty_arrival(b)
    await b.flush_pending()
    task = b.name_task
    await task
    await b.flush_pending()
    b.announce.assert_awaited_once_with("Hey Alex, welcome back.")


@pytest.mark.asyncio
async def test_historical_identity_does_not_name_an_unknown_entrant():
    b = bridge()
    b.named_greetings = True
    b.transitions.greetings = True
    b.enabled = True
    b.identity_lookup = AsyncMock(
        return_value={
            "current_presence_verified": True,
            "person_track_ids": ["track-1"],
            "person_count": 1,
            "current_recognized_people": [],
            "recent_matches": [{"reported_name": "Alex"}],
        }
    )
    queue_empty_arrival(b)
    await b.flush_pending()
    task = b.name_task
    await task
    await b.flush_pending()
    b.announce.assert_awaited_once_with("Hey, welcome back.")


@pytest.mark.asyncio
async def test_departure_cancels_late_name_resolution():
    import asyncio
    from contextlib import suppress

    b = bridge()
    b.named_greetings = True
    b.transitions.greetings = True
    b.enabled = True
    future = asyncio.get_running_loop().create_future()

    async def waiting():
        return await future

    b.identity_lookup = waiting
    queue_empty_arrival(b)
    await b.flush_pending()
    task = b.name_task
    await asyncio.sleep(0)
    b.cancel_pending("departure")
    with suppress(asyncio.CancelledError):
        await task
    assert b.pending is None
    b.announce.assert_not_awaited()


@pytest.mark.asyncio
async def test_delayed_name_is_rechecked_after_conversation():
    b = bridge()
    b.named_greetings = True
    b.transitions.greetings = True
    b.enabled = True
    b.name_resolved = True
    b.name_observed = time.monotonic() - 11
    queue_empty_arrival(b, "Hey Alex, welcome back.")
    b.identity_lookup = AsyncMock(
        return_value={
            "current_presence_verified": True,
            "person_track_ids": ["track-1"],
            "person_count": 1,
            "current_recognized_people": [
                {"reported_name": "Blair", "track_id": "track-1"}
            ],
        }
    )
    await b.flush_pending()
    task = b.name_task
    await task
    await b.flush_pending()
    b.announce.assert_awaited_once_with("Hey Blair, welcome back.")
