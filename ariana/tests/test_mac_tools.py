import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from livekit.agents import AgentSession

import mac_tools as mac
from mac_simulation import DesktopFixture


def context():
    desktop = DesktopFixture()
    ctx = SimpleNamespace(
        session=SimpleNamespace(userdata={"_mac_simulator": desktop.run})
    )
    return ctx, desktop


@pytest.mark.asyncio
async def test_real_sdk_unset_state_is_initialized():
    session = AgentSession()
    assert mac._state(SimpleNamespace(session=session)) == {}
    assert session.userdata == {}


@pytest.mark.asyncio
async def test_full_search_uses_fresh_targets_and_verifies_result():
    ctx, desktop = context()
    fn = mac.mac_control._func
    await fn(ctx, "open", app_name="Spotify")
    view = await fn(ctx, "inspect")
    assert "path" not in view["elements"][0]
    assert "signature" not in view["elements"][0]
    assert (await fn(ctx, "click", snapshot_id=view["snapshot_id"], element_id="e0"))[
        "success"
    ]
    assert "error" in await fn(
        ctx, "type", snapshot_id=view["snapshot_id"], element_id="e1", text="wrong"
    )
    view = await fn(ctx, "inspect")
    assert (
        await fn(
            ctx,
            "type",
            snapshot_id=view["snapshot_id"],
            element_id="e1",
            text="Daft Punk",
        )
    )["success"]
    view = await fn(ctx, "inspect")
    assert (await fn(ctx, "shortcut", snapshot_id=view["snapshot_id"], key="return"))[
        "success"
    ]
    result = await fn(ctx, "inspect")
    assert desktop.app == "Spotify"
    assert desktop.query == "Daft Punk"
    assert result["elements"][2]["value"] == "Daft Punk"


@pytest.mark.asyncio
async def test_snapshot_mismatch_expiry_and_open_invalidate(monkeypatch):
    ctx, desktop = context()
    fn = mac.mac_control._func
    view = await fn(ctx, "inspect")
    assert "error" in await fn(ctx, "click", snapshot_id="invented", element_id="e0")
    stamp = ctx.session.userdata["mac_snapshot"]["time"]
    monkeypatch.setattr(mac.time, "monotonic", lambda: stamp + 61)
    assert "error" in await fn(
        ctx, "click", snapshot_id=view["snapshot_id"], element_id="e0"
    )
    await fn(ctx, "open", app_name="Spotify")
    assert "mac_snapshot" not in ctx.session.userdata
    assert [e["action"] for e in desktop.events] == ["inspect", "open"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "action,kwargs",
    [
        ("click", {"element_id": "missing"}),
        ("type", {"element_id": "e1", "text": ""}),
        ("shortcut", {"key": "arbitrary command"}),
        ("shortcut", {"key": "a", "modifiers": ["bad"]}),
        ("scroll", {"direction": "sideways"}),
        ("scroll", {"amount": 11}),
    ],
)
async def test_invalid_actions_do_not_reach_desktop(action, kwargs):
    ctx, desktop = context()
    view = await mac.mac_control._func(ctx, "inspect")
    assert "error" in await mac.mac_control._func(
        ctx, action, snapshot_id=view["snapshot_id"], **kwargs
    )
    assert len(desktop.events) == 1


@pytest.mark.asyncio
async def test_mac_only_and_permission_failure(monkeypatch):
    monkeypatch.setattr(mac.sys, "platform", "linux")
    assert "Mac" in (await mac._request({}, {"action": "inspect"}))["error"]
    monkeypatch.setattr(mac.sys, "platform", "darwin")
    monkeypatch.setattr(mac, "_run_mac", Mock(side_effect=OSError("denied")))
    assert "Accessibility" in (await mac._request({}, {"action": "inspect"}))["error"]


@pytest.mark.asyncio
async def test_timeout_consumes_snapshot_without_replay():
    ctx, _ = context()
    view = await mac.mac_control._func(ctx, "inspect")

    def timed_out(req):
        raise subprocess.TimeoutExpired("osascript", 30)

    ctx.session.userdata["_mac_simulator"] = timed_out
    result = await mac.mac_control._func(
        ctx, "click", snapshot_id=view["snapshot_id"], element_id="e0"
    )
    assert "may have occurred" in result["error"]
    assert "mac_snapshot" not in ctx.session.userdata


def test_native_controls_bypass_apple_event_ui_scan(monkeypatch):
    native = Mock(return_value={"elements": []})
    monkeypatch.setattr(mac, "run_native", native)
    subprocess_call = Mock(side_effect=AssertionError("No osascript UI scans"))
    monkeypatch.setattr(mac.subprocess, "run", subprocess_call)
    assert mac._run_mac({"action": "inspect"}) == {"elements": []}
    native.assert_called_once_with({"action": "inspect"})


def test_open_app_keeps_name_out_of_script(monkeypatch):
    runner = Mock(return_value=SimpleNamespace(returncode=0, stdout='{"success":true}'))
    monkeypatch.setattr(mac.subprocess, "run", runner)
    name = 'Spotify"; shell command'
    assert mac._run_mac({"action": "open", "app_name": name})["success"]
    argv = runner.call_args.args[0]
    assert name not in argv[4]
    assert name in __import__("json").loads(argv[5])["app_name"]
