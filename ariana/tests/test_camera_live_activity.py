import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import aiohttp
import pytest
from test_camera import context, ha_count

from camera_awareness import CameraAwareness
from camera_recognition import current_identity
from frigate_api import CameraError, FrigateAPI


def fake_ws(monkeypatch, objects, config=None, wrong_camera=False, error=None):
    ws = SimpleNamespace(
        send_json=AsyncMock(),
        receive_json=AsyncMock(
            return_value={
                "topic": "camera_activity",
                "payload": json.dumps(
                    {
                        "other" if wrong_camera else "bedroom": {
                            "objects": objects,
                            "config": config
                            if config is not None
                            else {"enabled": True, "detect": True},
                        }
                    }
                ),
            }
        ),
    )

    class Connection:
        async def __aenter__(self):
            if error:
                raise error
            return ws

        async def __aexit__(self, *args):
            pass

    class Client:
        def __init__(self, **kwargs):
            self.trace = kwargs["trace_configs"][0]
            ws.trace = self.trace

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        def ws_connect(self, url, **kwargs):
            assert url == "ws://frigate.invalid:8971/ws"
            assert kwargs["headers"] == {"Authorization": "Bearer test-token"}
            assert kwargs["max_msg_size"] == 5 * 1024 * 1024
            return Connection()

    monkeypatch.setattr(aiohttp, "ClientSession", Client)
    api = FrigateAPI("http://frigate.invalid:8971", token="test-token")
    api.get = AsyncMock(return_value="0.18.0")
    return api, ws


@pytest.mark.asyncio
async def test_live_activity_includes_stationary_people_without_images_or_mutations(
    monkeypatch,
):
    api, ws = fake_ws(
        monkeypatch,
        [
            {"id": "a", "label": "person-verified", "stationary": True},
            {"id": "b", "label": "person", "stationary": False},
            {"id": "c", "label": "cat"},
        ],
    )
    assert await api.live_activity("bedroom") == ["a", "b"]
    ws.send_json.assert_awaited_once_with({"topic": "onConnect", "payload": ""})
    api.get.assert_awaited_once_with("/api/version", text=True)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "objects,config,wrong_camera",
    [
        ([{"id": "a", "label": "person"}, {"id": "a", "label": "person"}], None, False),
        ([{"label": "person"}], None, False),
        ([], {"enabled": True, "detect": False}, False),
        ([], {"enabled": False, "detect": True}, False),
        ([], None, True),
        ([None], None, False),
    ],
)
async def test_invalid_live_activity_is_not_a_verified_zero(
    monkeypatch, objects, config, wrong_camera
):
    api, _ws = fake_ws(monkeypatch, objects, config, wrong_camera)
    with pytest.raises(CameraError):
        await api.live_activity("bedroom")


@pytest.mark.asyncio
async def test_live_timeout_returns_unknown_without_reusing_cached_count(monkeypatch):
    api, ws = fake_ws(monkeypatch, [])
    ws.receive_json.side_effect = TimeoutError()
    with pytest.raises(CameraError, match="no stale value"):
        await api.live_activity("bedroom")


@pytest.mark.asyncio
async def test_live_auth_failure_requires_reauthentication(monkeypatch):
    error = aiohttp.WSServerHandshakeError(None, (), status=401)
    api, _ws = fake_ws(monkeypatch, [], error=error)
    api._username = "viewer"
    with pytest.raises(CameraError, match="authentication"):
        await api.live_activity("bedroom")
    assert api._token == ""


@pytest.mark.asyncio
async def test_stale_unchanged_ha_value_uses_independent_fresh_tracker():
    api = SimpleNamespace(live_activity=AsyncMock(return_value=["person-1"]))
    client = CameraAwareness(api)
    client.health = AsyncMock(return_value={"online": True, "observed_at": time.time()})
    ctx = context(client)
    eid = ha_count(ctx, 7, age=3600)
    result = await client.current(ctx, "bedroom", eid)
    assert result["person_count"] == 1 and result["person_track_ids"] == ["person-1"]
    assert result["source"] == "authenticated Frigate live activity"
    assert time.time() - result["observed_at"] < 2
    assert client.health.await_count == 2


@pytest.mark.asyncio
async def test_fallback_does_not_trust_a_camera_that_stops_during_the_read():
    client = CameraAwareness(
        SimpleNamespace(live_activity=AsyncMock(return_value=["one"]))
    )
    client.health = AsyncMock(side_effect=[{"online": True}, {"online": False}])
    with pytest.raises(CameraError, match="offline"):
        await client.live_count("bedroom")


@pytest.mark.asyncio
async def test_identity_must_match_live_ids_not_just_person_count():
    now = time.time()
    client = SimpleNamespace(
        current=AsyncMock(
            return_value={
                "person_count": 1,
                "person_track_ids": ["new"],
                "observed_at": now,
            }
        ),
        health=AsyncMock(return_value={"online": True, "observed_at": now}),
        api=SimpleNamespace(
            get=AsyncMock(
                return_value=[
                    {
                        "id": "old",
                        "camera": "bedroom",
                        "label": "person",
                        "start_time": now - 20,
                        "end_time": None,
                        "sub_label": "Alex",
                        "data": {"sub_label_score": 0.99},
                    }
                ]
            )
        ),
    )
    result = await current_identity(client, "bedroom", object())
    assert (
        result["identity_now"] == "unknown" and not result["current_presence_verified"]
    )


@pytest.mark.asyncio
async def test_live_transport_refuses_redirects_before_following_them(monkeypatch):
    api, ws = fake_ws(monkeypatch, [])
    await api.live_activity("bedroom")
    with pytest.raises(CameraError, match="redirects are refused"):
        await ws.trace.on_request_redirect[0](None, None, None)
