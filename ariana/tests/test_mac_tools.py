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


def test_open_app_passes_name_as_literal_argument(monkeypatch):
    runner = Mock(return_value=SimpleNamespace(returncode=0))
    monkeypatch.setattr(mac.subprocess, "run", runner)
    name = 'Spotify"; shell command'
    assert mac._run_mac({"action": "open", "app_name": name})["success"]
    assert runner.call_args.args[0] == ["/usr/bin/open", "-a", name]


@pytest.mark.asyncio
async def test_direct_browser_search_does_not_need_accessibility():
    ctx, desktop = context()
    desktop.denied = True
    r = await mac.mac_control._func(
        ctx, "browser_search", app_name="Safari", query='LiveKit & "agents"'
    )
    assert r["success"] and desktop.app == "Safari"
    assert desktop.url == "https://duckduckgo.com/?q=LiveKit%20%26%20%22agents%22"
    assert [e["action"] for e in desktop.events] == ["browser_search"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "javascript:alert(1)",
        "https://user:secret@example.com",
        "https://example.com\n",
        "not a url",
    ],
)
async def test_invalid_browser_urls_never_dispatch(url):
    ctx, desktop = context()
    assert "error" in await mac.mac_control._func(ctx, "browser_open", url=url)
    assert not desktop.events


@pytest.mark.asyncio
async def test_focused_field_replacement_and_snapshot_consumption():
    ctx, desktop = context()
    desktop.query = "Old search"
    r = await mac.mac_control._func(ctx, "inspect")
    assert (
        await mac.mac_control._func(
            ctx, "type", snapshot_id=r["snapshot_id"], text="New search", replace=True
        )
    )["success"]
    assert desktop.query == "New search" and not desktop.searched
    assert "mac_snapshot" not in ctx.session.userdata


@pytest.mark.asyncio
async def test_unfocused_typing_is_refused():
    ctx, desktop = context()
    r = await mac.mac_control._func(ctx, "inspect")
    ctx.session.userdata["mac_snapshot"]["data"]["elements"][1]["focused"] = False
    assert "error" in await mac.mac_control._func(
        ctx, "type", snapshot_id=r["snapshot_id"], text="No target"
    )
    assert len(desktop.events) == 1


@pytest.mark.asyncio
async def test_shortcut_aliases_and_function_keys():
    ctx, desktop = context()
    r = await mac.mac_control._func(ctx, "inspect")
    assert (
        await mac.mac_control._func(
            ctx,
            "shortcut",
            snapshot_id=r["snapshot_id"],
            key="F5",
            modifiers=["cmd", "alt"],
        )
    )["success"]
    assert desktop.events[-1]["key_code"] == 96
    assert desktop.events[-1]["modifiers"] == ["command", "option"]


@pytest.mark.asyncio
async def test_window_selection_preserves_server_side_target():
    ctx, _ = context()
    events = []

    def backend(req):
        events.append(req)
        if req["action"] == "windows":
            return {
                "pid": 77,
                "windows": [
                    {
                        "id": "w0",
                        "index": 0,
                        "signature": "private",
                        "title": "Document",
                    }
                ],
                "elements": [],
            }
        return {"success": True}

    ctx.session.userdata["_mac_simulator"] = backend
    r = await mac.mac_control._func(ctx, "windows")
    assert (
        await mac.mac_control._func(
            ctx, "focus_window", snapshot_id=r["snapshot_id"], window_id="w0"
        )
    )["success"]
    assert events[-1]["window_target"]["signature"] == "private"
    assert "signature" not in r["windows"][0]


def test_browser_navigation_uses_literal_url_argument(monkeypatch):
    runner = Mock(return_value=SimpleNamespace(returncode=0))
    monkeypatch.setattr(mac.subprocess, "run", runner)
    r = mac._run_browser(
        {"app_name": "Safari", "url": "https://example.com/?q=hello%20world"}
    )
    assert r["success"] and "contents have not been verified" in r["message"]
    assert runner.call_args.args[0] == ["/usr/bin/open", "-a", "Safari", r["url"]]


@pytest.mark.asyncio
async def test_parallel_inspections_are_serialized(monkeypatch):
    import asyncio
    import time

    ctx, _ = context()
    active = 0
    peak = 0

    def backend(req):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        time.sleep(0.02)
        active -= 1
        return {"pid": 1, "window": "Test", "elements": []}

    ctx.session.userdata["_mac_simulator"] = backend
    await asyncio.gather(
        mac.mac_control._func(ctx, "inspect"), mac.mac_control._func(ctx, "inspect")
    )
    assert peak == 1


@pytest.mark.asyncio
async def test_saved_browser_is_used_only_without_explicit_browser(monkeypatch):
    ctx = SimpleNamespace(session=SimpleNamespace(userdata={}))
    monkeypatch.setattr(mac.sys, "platform", "darwin")
    preferences = Mock(return_value={"default_browser": "Firefox"})
    backend = Mock(return_value={"success": True})
    monkeypatch.setattr(mac, "read_preferences", preferences)
    monkeypatch.setattr(mac, "_run_browser", backend)
    assert (await mac.mac_control._func(ctx, "browser_search", query="LiveKit"))[
        "success"
    ]
    assert backend.call_args.args[0]["app_name"] == "Firefox"
    assert (
        await mac.mac_control._func(
            ctx, "browser_search", app_name="Safari", query="LiveKit"
        )
    )["success"]
    assert backend.call_args.args[0]["app_name"] == "Safari"
    assert preferences.call_count == 1
