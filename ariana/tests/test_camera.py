import asyncio
import base64
import io
import time
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from livekit.agents import ChatContext
from PIL import Image

from camera_awareness import CameraAwareness, read_camera
from camera_events import CameraTransitions, start_camera_events
from camera_privacy import approval
from camera_recognition import RecognitionPolicy, recognition_capabilities
from camera_tools import camera_announcements, camera_snapshot, normalized_snapshot
from frigate_api import MAX_BYTES, CameraError, FrigateAPI
from home_assistant_simulation import fixture_client


def context(client=None):
    agent = SimpleNamespace(chat_ctx=ChatContext(), update_chat_ctx=AsyncMock())

    async def update(chat):
        agent.chat_ctx = chat

    agent.update_chat_ctx.side_effect = update
    session = SimpleNamespace(
        userdata={"_camera_client": client} if client else {},
        history=SimpleNamespace(items=[SimpleNamespace(role="user", id="u1")]),
        current_agent=agent,
        user_state="away",
        on=lambda *args: None,
        off=lambda *args: None,
    )
    try:
        previous = asyncio.get_running_loop().create_future()
    except RuntimeError:
        previous = None
    return SimpleNamespace(session=session, speech_handle=previous)


def reply(ctx, turn_id="u2"):
    ctx.session.history.items.append(
        SimpleNamespace(
            role="assistant",
            id="disclosure-" + turn_id,
            text_content="May I send one camera snapshot to Google Gemini?",
        )
    )
    ctx.session.history.items.append(SimpleNamespace(role="user", id=turn_id))


def api(handler):
    return FrigateAPI(
        "http://frigate.invalid:8971",
        token="test-private-token",
        transport=httpx.MockTransport(handler),
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://frigate.invalid:5000",
        "http://user:secret@host:8971",
        "ftp://host",
        "http://host:bad",
        "http://host:8971/api",
        "http://host:8971?token=private",
    ],
)
def test_reject_unsafe_configuration(url):
    with pytest.raises(CameraError):
        FrigateAPI(url, token="fake")


@pytest.mark.asyncio
async def test_disabled_camera_no_network(monkeypatch):
    monkeypatch.setenv("ARIANA_CAMERA_ENABLED", "false")
    assert "disabled" in (await read_camera(context(), "current"))["error"]


@pytest.mark.asyncio
async def test_authenticated_connection():
    def handler(request):
        assert request.headers["authorization"] == "Bearer test-private-token"
        assert request.method == "GET" and request.url.path == "/api/stats"
        return httpx.Response(200, json={"cameras": {"bedroom": {}}})

    assert (await CameraAwareness(api(handler)).cameras())["cameras"] == ["bedroom"]


@pytest.mark.asyncio
async def test_login_once_and_recovery():
    calls = []

    def handler(request):
        calls.append(request.url.path)
        if request.url.path == "/api/login":
            return httpx.Response(
                200,
                headers={"set-cookie": "frigate_token=fake-session; Path=/"},
                json={},
            )
        assert request.headers["authorization"] == "Bearer fake-session"
        return httpx.Response(200, json={})

    client = FrigateAPI(
        "http://frigate.invalid:8971",
        username="viewer",
        password="fake-password",
        transport=httpx.MockTransport(handler),
    )
    await client.get("/api/stats")
    await client.get("/api/stats")
    assert calls == ["/api/login", "/api/stats", "/api/stats"]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 403, 404, 302, 500])
async def test_http_errors_never_export_response_or_secret(status):
    with pytest.raises(CameraError) as error:
        await api(
            lambda r: httpx.Response(status, text="test-private-token PRIVATE DETAILS")
        ).get("/api/stats")
    assert "PRIVATE" not in str(error.value) and "test-private-token" not in str(
        error.value
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("exception", [httpx.ConnectError, httpx.ReadTimeout])
async def test_connection_failure(exception):
    def handler(request):
        raise exception("SECRET URL", request=request)

    with pytest.raises(CameraError) as error:
        await api(handler).get("/api/stats")
    assert "SECRET" not in str(error.value)


@pytest.mark.asyncio
async def test_oversized_transport_response():
    with pytest.raises(CameraError, match="oversized"):
        await api(lambda r: httpx.Response(200, content=b"x" * (MAX_BYTES + 1))).get(
            "/api/stats"
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("fps,online", [(5, True), (0, False)])
async def test_camera_health(fps, online):
    client = CameraAwareness(
        api(
            lambda r: httpx.Response(
                200,
                json={
                    "service": {"last_updated": time.time()},
                    "cameras": {"bedroom": {"camera_fps": fps}},
                },
            )
        )
    )
    assert (await client.health("bedroom"))["online"] is online
    with pytest.raises(CameraError):
        await client.health("missing")


@pytest.mark.asyncio
async def test_stale_camera_stats_unknown():
    client = CameraAwareness(
        api(
            lambda r: httpx.Response(
                200,
                json={
                    "service": {"last_updated": time.time() - 120},
                    "cameras": {"bedroom": {"camera_fps": 5}},
                },
            )
        )
    )
    with pytest.raises(CameraError, match="stale"):
        await client.health("bedroom")


def ha_count(ctx, value, name="Bedroom Person Count", platform="frigate", age=0):
    ha, fixture = fixture_client()
    entity = "sensor.bedroom_person_count"
    fixture.rows[entity] = {
        "entity_id": entity,
        "state": str(value),
        "last_reported": datetime.fromtimestamp(
            time.time() - age, timezone.utc
        ).isoformat(),
        "attributes": {"friendly_name": name, "unit_of_measurement": "objects"},
    }
    fixture.registry["entity"].append(
        {
            "entity_id": entity,
            "id": "person-count",
            "platform": platform,
            "original_name": name,
        }
    )
    ctx.session.userdata["_ha_client"] = ha
    return entity


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [0, 1, 2])
async def test_fresh_counts_do_not_infer_identity(monkeypatch, count):
    monkeypatch.setenv("ARIANA_CAMERA_ENABLED", "true")
    client = CameraAwareness(None)
    ctx = context(client)
    entity = ha_count(ctx, count)
    result = await client.current(ctx, "bedroom", entity)
    assert result["person_count"] == count and result["identity"] == "unknown"
    assert result["verified"]
    assert (await client.objects(ctx, "bedroom"))["counts"][0]["count"] == count


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "value,age,name,platform",
    [
        (1, 120, "Bedroom Person Count", "frigate"),
        ("unavailable", 0, "Bedroom Person Count", "frigate"),
        (1, 0, "Bedroom Active Person Count", "frigate"),
        (1, 0, "Bedroom Person Count", "other"),
        (-1, 0, "Bedroom Person Count", "frigate"),
        (1.5, 0, "Bedroom Person Count", "frigate"),
    ],
)
async def test_stale_invalid_or_unrelated_count_is_unknown(value, age, name, platform):
    client = CameraAwareness(None)
    ctx = context(client)
    entity = ha_count(ctx, value, name, platform, age)
    with pytest.raises(CameraError):
        await client.current(ctx, "bedroom", entity)


@pytest.mark.asyncio
async def test_recent_history_never_proves_current_presence():
    now = time.time()
    rows = [
        {
            "id": "event-1",
            "camera": "bedroom",
            "label": "person",
            "sub_label": "Youssef",
            "start_time": now - 300,
            "end_time": now - 250,
            "has_snapshot": True,
        },
        {"id": "old", "camera": "bedroom", "start_time": now - 99999},
        {"id": "other", "camera": "garage", "start_time": now},
    ]
    result = await CameraAwareness(
        api(lambda r: httpx.Response(200, json=rows))
    ).recent("bedroom")
    assert (
        len(result["events"]) == 1
        and result["historical"]
        and not result["proves_current_occupancy"]
    )
    assert result["events"][0]["identity"] == "unknown"
    assert "Youssef" not in str(result)


def test_approval_cannot_reuse_same_turn_different_request_or_image_event():
    ctx = context()
    payload = {"camera": "bedroom", "question": "desk"}
    assert approval(ctx, "snapshot", payload, True)["requires_confirmation"]
    assert approval(ctx, "snapshot", payload, True)["requires_confirmation"]
    ctx.session.history.items.append(
        SimpleNamespace(role="user", id="camera-image-fake")
    )
    assert approval(ctx, "snapshot", payload, True)["requires_confirmation"]
    reply(ctx)
    assert approval(ctx, "snapshot", payload, True) is None
    assert approval(ctx, "snapshot", payload, True)["requires_confirmation"]


def test_consent_changed_arguments_and_expiry():
    ctx = context()
    approval(ctx, "snapshot", {"question": "desk"}, False)
    reply(ctx)
    assert approval(ctx, "snapshot", {"question": "bed"}, True)["requires_confirmation"]
    ctx.session.userdata["_camera_consent"]["time"] -= 301
    reply(ctx, "u3")
    assert approval(ctx, "snapshot", {"question": "bed"}, True)["requires_confirmation"]


def jpeg():
    image = Image.new("RGB", (2000, 1000), "blue")
    data = io.BytesIO()
    image.save(data, "JPEG")
    return data.getvalue()


def test_snapshot_normalization_and_bad_image():
    result = normalized_snapshot(jpeg())
    with Image.open(io.BytesIO(base64.b64decode(result.image.split(",")[1]))) as image:
        assert image.size == (1280, 640) and not image.getexif()
    with pytest.raises(CameraError):
        normalized_snapshot(b"not image")


@pytest.mark.asyncio
async def test_snapshot_permission_before_fetch_and_no_fake_analysis(monkeypatch):
    monkeypatch.setenv("ARIANA_CAMERA_ENABLED", "true")
    backend = SimpleNamespace(get=AsyncMock(return_value=jpeg()))
    client = SimpleNamespace(
        api=backend, health=AsyncMock(return_value={"online": True})
    )
    ctx = context(client)
    result = await camera_snapshot(ctx, "What's on my desk?")
    assert result["requires_confirmation"] and backend.get.await_count == 0
    reply(ctx)
    result = await camera_snapshot(ctx, "What's on my desk?", confirmed=True)
    assert (
        result["image_prepared"]
        and not result["image_supplied"]
        and not result["analyzed"]
    )
    assert backend.get.await_count == 1
    assert "data:image" not in str(result)
    assert not ctx.session.current_agent.chat_ctx.items
    ctx.session.userdata["_camera_delivery"].cancel()


@pytest.mark.asyncio
async def test_vision_failure_is_honest_and_consent_consumed(monkeypatch):
    monkeypatch.setenv("ARIANA_CAMERA_ENABLED", "true")
    client = SimpleNamespace(
        api=SimpleNamespace(get=AsyncMock(return_value=b"bad")),
        health=AsyncMock(return_value={"online": True}),
    )
    ctx = context(client)
    await camera_snapshot(ctx, "desk")
    reply(ctx)
    assert "error" in await camera_snapshot(ctx, "desk", confirmed=True)
    assert "_camera_consent" not in ctx.session.userdata
    assert not ctx.session.current_agent.chat_ctx.items


def test_events_baseline_dedup_stale_cooldown_and_unknown_identity():
    tracker = CameraTransitions()

    def row(value, at):
        return {"state": str(value), "last_updated": at}

    assert tracker.accept("person", row(0, 100), "person", 100) is None
    result = tracker.accept("person", row(1, 101), "person", 101)
    assert "Someone" in result and "Youssef" not in result
    assert tracker.accept("person", row(1, 101), "person", 101) is None
    assert tracker.accept("person", row(0, 102), "person", 140) is None
    assert tracker.accept("person", row(0, 141), "person", 141)
    assert not tracker.can_speak(1, enabled=False, idle=True)
    assert not tracker.can_speak(1, enabled=True, idle=False)
    assert tracker.can_speak(1, enabled=True, idle=True)
    assert not tracker.can_speak(100, enabled=True, idle=True)
    tracker.reset()
    assert tracker.accept("person", row(1, 142), "person", 142) is None


def test_offline_online_and_alert_transitions():
    tracker = CameraTransitions()
    tracker.states = {"camera": "idle", "alert": "detection"}
    assert tracker.accept(
        "camera", {"state": "unavailable", "last_updated": 100}, "availability", 100
    )
    assert tracker.accept(
        "camera", {"state": "idle", "last_updated": 101}, "availability", 101
    )
    assert tracker.accept(
        "alert", {"state": "alert", "last_updated": 102}, "alert", 102
    )


def test_events_disabled_no_subscription(monkeypatch):
    monkeypatch.setenv("ARIANA_CAMERA_ENABLED", "false")
    assert start_camera_events(SimpleNamespace()) is None


@pytest.mark.asyncio
async def test_announcements_two_turn_opt_in_and_immediate_disable(monkeypatch):
    monkeypatch.setenv("ARIANA_CAMERA_ENABLED", "true")
    ctx = context()
    bridge = SimpleNamespace(enabled=False)
    ctx.session.userdata["_camera_events"] = bridge
    assert (await camera_announcements(ctx, True))["requires_confirmation"]
    assert not bridge.enabled
    reply(ctx)
    assert (await camera_announcements(ctx, True, True))["enabled"]
    assert (await camera_announcements(ctx, False))["enabled"] is False
    assert not bridge.enabled


def test_no_native_identity_without_opt_in_and_confidence():
    assert RecognitionPolicy().identity("Youssef", 0.99)["identity"] == "unknown"
    assert RecognitionPolicy(True).identity("Youssef", 0.5)["identity"] == "unknown"
    assert (
        RecognitionPolicy(True).identity("Youssef", float("nan"))["identity"]
        == "unknown"
    )
    assert RecognitionPolicy(True).identity("Youssef", 0.99)["identity"] == "Youssef"


@pytest.mark.asyncio
async def test_recognition_preparation_does_not_enable_it():
    backend = SimpleNamespace(get=AsyncMock(return_value="0.17.0"))
    result = await recognition_capabilities(backend)
    assert (
        not result["recognition_enabled_by_ariana"]
        and not result["installed_capability_verified"]
    )
    backend.get.assert_awaited_once_with("/api/version", text=True)


@pytest.mark.asyncio
async def test_default_camera_sensor_matching_and_unrelated_exclusion(monkeypatch):
    monkeypatch.setenv("ARIANA_CAMERA_ENABLED", "true")
    client = CameraAwareness(None)
    ctx = context(client)
    ha_count(ctx, 2)
    result = await read_camera(ctx, "current")
    assert result["person_count"] == 2 and result["verified"]
    result = await read_camera(ctx, "current", "garage")
    assert not result.get("verified") and result["current_detection_available"] is False


@pytest.mark.asyncio
async def test_memory_cannot_save_camera_analysis(monkeypatch):
    from memory_tools import memory_manage

    ctx = context()
    ctx.session.userdata["_camera_private_turn"] = "u1"
    backend = AsyncMock()
    ctx.session.userdata["_memory_simulator"] = backend
    result = await memory_manage(ctx, "remember", "desk", "Something visible on desk")
    assert "cannot be saved" in result["error"]
    assert not backend.called


@pytest.mark.asyncio
async def test_image_failure_after_provider_rejection_is_not_analysis(monkeypatch):
    monkeypatch.setenv("ARIANA_CAMERA_ENABLED", "true")
    client = SimpleNamespace(
        api=SimpleNamespace(get=AsyncMock(return_value=jpeg())),
        health=AsyncMock(return_value={"online": True}),
    )
    ctx = context(client)
    monkeypatch.setattr(
        "camera_tools.schedule_delivery",
        __import__("unittest.mock", fromlist=["Mock"]).Mock(
            side_effect=RuntimeError("PRIVATE PROVIDER DETAILS")
        ),
    )
    await camera_snapshot(ctx, "desk")
    reply(ctx)
    result = await camera_snapshot(ctx, "desk", confirmed=True)
    assert "could not be supplied" in result["error"] and "PRIVATE" not in str(result)
    assert not result.get("image_supplied")


@pytest.mark.asyncio
async def test_subscription_baseline_and_new_transition(monkeypatch):
    import aiohttp

    from camera_events import CameraEventBridge

    monkeypatch.setenv("HOME_ASSISTANT_URL", "http://ha.invalid")
    monkeypatch.setenv("HOME_ASSISTANT_TOKEN", "fictional-private-token")
    ctx = context()
    entity = ha_count(ctx, 0)
    now = time.time()

    class WS:
        def __init__(self):
            self.handshake = iter(
                [
                    {"type": "auth_required"},
                    {"type": "auth_ok"},
                    {
                        "id": 1,
                        "success": True,
                        "result": [{"entity_id": entity, "state": "0"}],
                    },
                    {"id": 2, "success": True},
                ]
            )
            self.sent = []
            self.events = iter(
                [
                    {
                        "type": "event",
                        "event": {
                            "event_type": "state_changed",
                            "data": {
                                "entity_id": entity,
                                "new_state": {"state": "1", "last_updated": now},
                            },
                        },
                    }
                ]
            )

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def receive_json(self):
            return next(self.handshake)

        async def send_json(self, data):
            self.sent.append(data)

        def __aiter__(self):
            return self

        async def __anext__(self):
            try:
                return SimpleNamespace(
                    type=aiohttp.WSMsgType.TEXT,
                    data=__import__("json").dumps(next(self.events)),
                )
            except StopIteration:
                raise StopAsyncIteration from None

    ws = WS()

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        def ws_connect(self, *args, **kwargs):
            assert kwargs["heartbeat"] == 30
            return ws

    monkeypatch.setattr(aiohttp, "ClientSession", Client)
    companion = SimpleNamespace(
        session=ctx.session,
        closed=False,
        policy=SimpleNamespace(last_activity=0),
        uploads={},
        speech=None,
    )
    bridge = CameraEventBridge(companion, {entity: "person"})
    bridge.enabled = True
    bridge.idle = lambda: True
    bridge.announce = AsyncMock()
    await bridge.subscribe()
    assert bridge.status == "connected"
    assert (
        ws.sent[1]["type"] == "get_states" and ws.sent[2]["type"] == "subscribe_events"
    )
    assert bridge.announce.await_count == 1
    assert "Someone" in bridge.announce.call_args.args[0]


@pytest.mark.asyncio
async def test_invalid_subscription_source_never_connects(monkeypatch):
    from camera_events import CameraEventBridge

    monkeypatch.setenv("HOME_ASSISTANT_URL", "http://ha.invalid")
    monkeypatch.setenv("HOME_ASSISTANT_TOKEN", "fictional-private-token")
    ctx = context()
    entity = ha_count(ctx, 0, platform="not-frigate")
    companion = SimpleNamespace(session=ctx.session)
    bridge = CameraEventBridge(companion, {entity: "person"})
    await bridge.subscribe()
    assert bridge.status == "invalid_source" and companion.closed_camera_events


@pytest.mark.asyncio
async def test_ha_only_count_does_not_need_frigate_credentials(monkeypatch):
    monkeypatch.setenv("ARIANA_CAMERA_ENABLED", "true")
    for name in (
        "FRIGATE_URL",
        "FRIGATE_TOKEN",
        "FRIGATE_USERNAME",
        "FRIGATE_PASSWORD",
    ):
        monkeypatch.delenv(name, raising=False)
    ctx = context()
    ha_count(ctx, 1)
    assert (await read_camera(ctx, "current"))["person_count"] == 1


@pytest.mark.asyncio
async def test_announcements_never_enable_disconnected_source():
    ctx = context()
    bridge = SimpleNamespace(enabled=False, status="authentication_required")
    ctx.session.userdata["_camera_events"] = bridge
    assert "error" in await camera_announcements(ctx, True, True)
    assert not bridge.enabled


@pytest.mark.asyncio
async def test_announcements_can_be_stopped_during_speech():
    from unittest.mock import Mock

    ctx = context()
    speech = Mock()
    bridge = SimpleNamespace(
        enabled=True, speaking=True, companion=SimpleNamespace(speech=speech)
    )
    ctx.session.userdata["_camera_events"] = bridge
    await camera_announcements(ctx, False)
    speech.interrupt.assert_called_once()
    assert not bridge.enabled


@pytest.mark.parametrize("value", [".", "..", "a/b", {}, None])
def test_camera_identifiers_block_traversal_and_bad_types(value):
    from frigate_api import identifier

    with pytest.raises(CameraError):
        identifier(value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "row",
    [
        {"cameras": [], "service": {}},
        {"cameras": {"bedroom": {}}, "service": []},
        {
            "cameras": {"bedroom": {"camera_fps": 5, "capture_pid": None}},
            "service": {"last_updated": time.time()},
        },
    ],
)
async def test_bad_health_or_missing_capture_cannot_claim_online(row):
    client = CameraAwareness(api(lambda r: httpx.Response(200, json=row)))
    with pytest.raises(CameraError):
        await client.health("bedroom")


def test_out_of_order_events_do_not_become_false_departures():
    tracker = CameraTransitions()
    tracker.states["person"] = "0"
    assert tracker.accept("person", {"state": "1", "last_updated": 199}, "person", 200)
    assert (
        tracker.accept("person", {"state": "0", "last_updated": 198}, "person", 200)
        is None
    )
    assert tracker.states["person"] == "1"


@pytest.mark.asyncio
async def test_event_speech_has_no_tools_and_no_user_authorization():
    from camera_events import CameraEventBridge

    calls = []

    async def speech():
        pass

    def generate(**kwargs):
        calls.append(kwargs)
        return speech()

    companion = SimpleNamespace(
        session=SimpleNamespace(generate_reply=generate), speech=None
    )
    bridge = CameraEventBridge(companion, {})
    await bridge.announce("Someone was newly detected by the bedroom camera.")
    assert calls[0]["tool_choice"] == "none" and calls[0]["tools"] == []
    assert "user_input" not in calls[0] and companion.speech is None


@pytest.mark.asyncio
async def test_image_delivery_waits_for_tool_reply_and_has_no_action_tools():
    from unittest.mock import Mock

    from camera_delivery import schedule_delivery

    ctx = context()
    speech = asyncio.get_running_loop().create_future()
    speech.set_result(None)
    ctx.session.generate_reply = Mock(return_value=speech)
    schedule_delivery(
        ctx, normalized_snapshot(jpeg()), "bedroom", "Describe image", False
    )
    task = ctx.session.userdata["_camera_delivery"]
    await asyncio.sleep(0)
    ctx.session.generate_reply.assert_not_called()
    ctx.speech_handle.set_result(None)
    await task
    ctx.session.generate_reply.assert_called_once()
    assert ctx.session.generate_reply.call_args.kwargs["tools"] == []
    assert ctx.session.generate_reply.call_args.kwargs["tool_choice"] == "none"
    assert not ctx.session.current_agent.chat_ctx.items
    assert "_camera_delivery" not in ctx.session.userdata
    assert "_camera_delivery_error" not in ctx.session.userdata


@pytest.mark.asyncio
async def test_new_user_turn_cancels_pending_cloud_upload():
    from unittest.mock import Mock

    from camera_delivery import schedule_delivery

    ctx = context()
    ctx.session.generate_reply = Mock()
    schedule_delivery(ctx, normalized_snapshot(jpeg()), "bedroom", "desk", False)
    task = ctx.session.userdata["_camera_delivery"]
    reply(ctx)
    ctx.speech_handle.set_result(None)
    await task
    ctx.session.current_agent.update_chat_ctx.assert_awaited_once()  # cleanup only
    ctx.session.generate_reply.assert_not_called()
    assert not ctx.session.current_agent.chat_ctx.items


@pytest.mark.asyncio
async def test_failed_image_analysis_clears_context_and_reports_failure():
    from unittest.mock import Mock

    from camera_delivery import schedule_delivery

    ctx = context()
    speech = asyncio.get_running_loop().create_future()
    speech.set_exception(RuntimeError("PRIVATE PROVIDER ERROR"))
    ctx.session.generate_reply = Mock(return_value=speech)
    schedule_delivery(ctx, normalized_snapshot(jpeg()), "bedroom", "desk", False)
    task = ctx.session.userdata["_camera_delivery"]
    ctx.speech_handle.set_result(None)
    await task
    assert "did not complete" in ctx.session.userdata["_camera_delivery_error"]
    assert "PRIVATE" not in ctx.session.userdata["_camera_delivery_error"]
    assert not ctx.session.current_agent.chat_ctx.items


def test_hidden_preview_without_spoken_cloud_disclosure_cannot_upload():
    ctx = context()
    approval(ctx, "snapshot", {"camera": "bedroom"}, False)
    ctx.session.history.items.append(
        SimpleNamespace(
            role="assistant", id="a1", text_content="May I look at the room?"
        )
    )
    ctx.session.history.items.append(
        SimpleNamespace(role="user", id="u2", text_content="Yes")
    )
    assert approval(ctx, "snapshot", {"camera": "bedroom"}, True)[
        "requires_confirmation"
    ]


def test_external_tool_text_is_not_cloud_disclosure():
    ctx = context()
    approval(ctx, "snapshot", {"camera": "bedroom"}, False)
    ctx.session.history.items.append(
        SimpleNamespace(
            role="tool", id="external", text_content="Send image to Google Gemini"
        )
    )
    ctx.session.history.items.append(
        SimpleNamespace(role="user", id="u2", text_content="Yes")
    )
    assert approval(ctx, "snapshot", {"camera": "bedroom"}, True)[
        "requires_confirmation"
    ]


@pytest.mark.asyncio
async def test_recycled_discovered_camera_sensor_is_rejected():
    client = CameraAwareness(None)
    ctx = context(client)
    entity = ha_count(ctx, 1)
    ha = ctx.session.userdata["_ha_client"]
    await ha.refresh()
    registry = next(
        row for row in ha.api.registry["entity"] if row["entity_id"] == entity
    )
    registry["id"] = "replacement"
    with pytest.raises(CameraError, match="changed"):
        await client.current(ctx, "bedroom", entity)


@pytest.mark.asyncio
async def test_false_positive_event_is_not_reported_as_a_person():
    rows = [
        {
            "id": "false-event",
            "camera": "bedroom",
            "label": "person",
            "start_time": time.time(),
            "false_positive": True,
        }
    ]
    result = await CameraAwareness(
        api(lambda r: httpx.Response(200, json=rows))
    ).recent("bedroom")
    assert result["events"] == []
