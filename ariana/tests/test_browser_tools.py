import asyncio
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from livekit.agents.llm import ToolError

import browser_tools as module
from browser_tools import BrowserToolset, validate_url
from simulation_tools import SafariFixture


def context(backend):
    return SimpleNamespace(
        session=SimpleNamespace(userdata={"_safari_simulator": backend})
    )


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "javascript:alert(1)",
        "https://user:secret@example.com",
        "https://example.com\n",
        "invalid",
    ],
)
def test_invalid_urls_rejected(url):
    with pytest.raises(ToolError):
        validate_url(url)


def test_requested_local_pages_are_supported():
    assert (
        validate_url("http://homeassistant.local:8123")
        == "http://homeassistant.local:8123"
    )


@pytest.mark.asyncio
async def test_search_opens_safari_once_and_reads_verified_content():
    fixture = SafariFixture()
    browser = BrowserToolset()
    result = await browser.browser_search(context(fixture.run), "library & hours")
    assert result["verified"] and "09:00" in result["text"]
    assert fixture.events[0]["url"] == "https://duckduckgo.com/?q=library%20%26%20hours"
    assert [e["action"] for e in fixture.events] == ["open", "read"]
    assert browser._target["expected_url"] == result["url"]


@pytest.mark.asyncio
async def test_permissions_do_not_fall_back_or_retry(monkeypatch):
    fixture = SafariFixture(denied=True)
    native = Mock(
        side_effect=AssertionError("No native reads after Automation failure")
    )
    monkeypatch.setattr(module, "run_native", native)
    result = await BrowserToolset().browser_open(
        context(fixture.run), "https://example.com"
    )
    assert result["code"] == "safari_automation"
    assert len(fixture.events) == 1
    native.assert_not_called()


@pytest.mark.asyncio
async def test_page_polling_never_repeats_navigation(monkeypatch):
    backend = Mock(
        side_effect=lambda req: {
            "window_id": 4,
            "tab_index": 1,
            "url": "https://example.com",
            "text": "",
            "ready": "loading",
        }
    )
    result = await BrowserToolset().browser_open(
        context(backend), "https://example.com"
    )
    assert not result["verified"]
    assert [call.args[0]["action"] for call in backend.call_args_list].count(
        "open"
    ) == 1
    assert backend.call_count == 5


@pytest.mark.asyncio
async def test_accessibility_read_requires_same_foreground_tab(monkeypatch):
    native = Mock(return_value={"verified": True, "text": "accessible text"})
    monkeypatch.setattr(module, "run_native", native)
    page = {"window_id": 4, "tab_index": 1, "url": "https://example.com"}
    backend = Mock(
        side_effect=[{**page, "read_unavailable": True}, {**page, "window_id": 5}]
    )
    result = await BrowserToolset().browser_read(context(backend))
    assert result["read_unavailable"] and not result["verified"]
    native.assert_not_called()
    backend.side_effect = [{**page, "read_unavailable": True}, page]
    assert (await BrowserToolset().browser_read(context(backend)))[
        "text"
    ] == "accessible text"
    native.assert_called_once_with({"action": "read_page", "expected_url": page["url"]})


@pytest.mark.asyncio
async def test_accessibility_failure_is_clear_and_not_an_exception(monkeypatch):
    monkeypatch.setattr(
        module, "run_native", Mock(side_effect=OSError("private native failure"))
    )
    page = {
        "window_id": 4,
        "tab_index": 1,
        "url": "https://example.com",
        "read_unavailable": True,
    }
    result = await BrowserToolset().browser_read(context(lambda req: page))
    assert not result["verified"] and "private" not in result["message"]


@pytest.mark.asyncio
async def test_tab_selection_keeps_url_guard_and_refuses_unknown_id():
    page = {
        "window_id": 4,
        "tab_index": 2,
        "url": "https://example.com",
        "title": "Example",
    }
    backend = Mock(
        side_effect=[
            {"tabs": [page]},
            {**page, "verified": True},
            {"error": "Tab changed", "code": "stale_tab"},
        ]
    )
    browser = BrowserToolset()
    ctx = context(backend)
    assert "error" in await browser.browser_select_tab(ctx, "invented")
    assert (await browser.browser_tabs(ctx))["tabs"][0]["tab_id"] == "t0"
    await browser.browser_select_tab(ctx, "t0")
    assert (await browser.browser_read(ctx))["code"] == "stale_tab"
    assert backend.call_args.args[0]["expected_url"] == page["url"]


@pytest.mark.asyncio
async def test_session_operations_are_serialized():
    import time

    active = 0
    peak = 0

    def backend(req):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        time.sleep(0.01)
        active -= 1
        return {"error": "test unavailable"}

    browser = BrowserToolset()
    ctx = context(backend)
    await asyncio.gather(browser.browser_read(ctx), browser.browser_read(ctx))
    assert peak == 1


def test_safari_subprocess_uses_literal_arguments_and_hides_errors(monkeypatch):
    monkeypatch.setattr(module.sys, "platform", "darwin")
    runner = Mock(return_value=SimpleNamespace(returncode=1, stderr="secret"))
    monkeypatch.setattr(module.subprocess, "run", runner)
    assert "secret" not in str(
        module._run_safari({"action": "open", "url": "https://example.com"})
    )
    runner.side_effect = subprocess.TimeoutExpired("osascript", 12)
    assert module._run_safari({"action": "open"})["uncertain"]
    monkeypatch.setattr(module.sys, "platform", "linux")
    assert module._run_safari({"action": "open"})["code"] == "mac_required"
