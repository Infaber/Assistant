import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from livekit.agents.llm import ToolError

import browser_tools
from browser_tools import BrowserToolset, _clean_text, _is_private_address


@pytest.mark.asyncio
async def test_browser_toolset_starts_and_closes_webkit() -> None:
    browser = BrowserToolset(headless=True)

    await browser.setup()
    try:
        assert browser._browser is None  # Browser is optional until a tool needs it.
        async with browser._page_lock:
            page = await browser._ensure_page()
        await page.set_content("<title>Test page</title><body>Hello Ariana</body>")
        assert await browser.browser_read(None) == {
            "url": "about:blank",
            "title": "Test page",
            "text": "Hello Ariana",
        }
        assert browser._browser is not None
        assert browser._context is not None
        assert browser._page is not None
        assert {tool.id for tool in browser.tools} == {
            "browser_current_page",
            "browser_links",
            "browser_open",
            "browser_read",
            "browser_search",
        }
    finally:
        await browser.aclose()

    assert browser._browser is None
    assert browser._context is None
    assert browser._page is None


@pytest.mark.asyncio
async def test_browser_blocks_private_hosts() -> None:
    browser = BrowserToolset()

    with pytest.raises(ToolError, match="Local and internal hosts are blocked"):
        await browser._validate_url("http://localhost:8080")

    with pytest.raises(ToolError, match="Private and internal network addresses"):
        await browser._validate_url("http://127.0.0.1")


@pytest.mark.asyncio
async def test_browser_blocks_unsupported_urls() -> None:
    browser = BrowserToolset()

    with pytest.raises(ToolError, match="Only public HTTP and HTTPS"):
        await browser._validate_url("file:///tmp/example.html")

    with pytest.raises(ToolError, match="usernames or passwords"):
        await browser._validate_url("https://user:password@example.com")


def test_browser_helpers_bound_and_normalize_text() -> None:
    assert _is_private_address("127.0.0.1")
    assert _is_private_address("10.0.0.1")
    assert not _is_private_address("8.8.8.8")
    assert _clean_text("  hello\n\n world  ") == "hello world"


@pytest.fixture
def runtime(monkeypatch):
    page = Mock()
    page.is_closed.return_value = False
    page.url = "https://example.com"
    page.title = AsyncMock(return_value="Example")
    page.goto = AsyncMock(return_value=SimpleNamespace(status=200))
    page.locator.return_value.inner_text = AsyncMock(return_value="hello world")
    context = Mock(
        close=AsyncMock(), route=AsyncMock(), new_page=AsyncMock(return_value=page)
    )
    engine = Mock(close=AsyncMock(), new_context=AsyncMock(return_value=context))
    playwright = Mock(stop=AsyncMock())
    playwright.webkit.launch = AsyncMock(return_value=engine)
    start = AsyncMock(return_value=playwright)
    monkeypatch.setattr(
        browser_tools, "async_playwright", lambda: SimpleNamespace(start=start)
    )
    monkeypatch.setattr(browser_tools, "_resolve_addresses", lambda host: ["8.8.8.8"])
    return SimpleNamespace(
        page=page, context=context, engine=engine, playwright=playwright, start=start
    )


@pytest.mark.asyncio
async def test_setup_does_not_launch_a_browser(runtime) -> None:
    browser = BrowserToolset()
    await browser.setup()
    await browser.aclose()
    runtime.start.assert_not_awaited()


@pytest.mark.asyncio
async def test_concurrent_tools_share_one_browser(runtime) -> None:
    browser = BrowserToolset(headless=True)
    await browser.setup()
    try:
        results = await asyncio.gather(
            browser.browser_open(None, "https://example.com"),
            browser.browser_open(None, "https://example.com"),
        )
        assert all(result["text"] == "hello world" for result in results)
        runtime.start.assert_awaited_once()
        runtime.engine.new_context.assert_awaited_once_with(service_workers="block")
    finally:
        await browser.aclose()


@pytest.mark.asyncio
async def test_failed_launch_releases_driver_and_can_retry(runtime) -> None:
    runtime.playwright.webkit.launch.side_effect = RuntimeError("missing binary")
    browser = BrowserToolset()
    await browser.setup()
    with pytest.raises(ToolError, match="browser could not start"):
        await browser.browser_open(None, "https://example.com")
    runtime.playwright.stop.assert_awaited_once()
    assert browser._playwright is None
    runtime.playwright.webkit.launch.side_effect = None
    try:
        assert (await browser.browser_open(None, "https://example.com"))[
            "status"
        ] == 200
    finally:
        await browser.aclose()


@pytest.mark.asyncio
async def test_failed_page_creation_releases_all_resources(runtime) -> None:
    runtime.context.new_page.side_effect = RuntimeError("page failed")
    browser = BrowserToolset()
    with pytest.raises(ToolError, match="browser could not start"):
        await browser.browser_open(None, "https://example.com")
    runtime.context.close.assert_awaited_once()
    runtime.engine.close.assert_awaited_once()
    runtime.playwright.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_cleanup_continues_after_a_close_failure(runtime) -> None:
    browser = BrowserToolset()
    await browser.browser_open(None, "https://example.com")
    runtime.context.close.side_effect = RuntimeError("close failed")
    await browser.aclose()
    await browser.aclose()  # Repeated cleanup is harmless.
    runtime.engine.close.assert_awaited_once()
    runtime.playwright.stop.assert_awaited_once()
    with pytest.raises(ToolError, match="session has ended"):
        await browser.browser_open(None, "https://example.com")


@pytest.mark.asyncio
async def test_cancelled_start_releases_driver(runtime) -> None:
    runtime.playwright.webkit.launch.side_effect = asyncio.CancelledError()
    browser = BrowserToolset()
    with pytest.raises(asyncio.CancelledError):
        await browser.browser_open(None, "https://example.com")
    runtime.playwright.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_navigation_failure_is_a_friendly_tool_error(runtime) -> None:
    runtime.page.goto.side_effect = RuntimeError("sensitive query or browser internals")
    browser = BrowserToolset()
    try:
        with pytest.raises(ToolError, match="Could not open that page") as error:
            await browser.browser_open(None, "https://example.com")
        assert "sensitive" not in str(error.value)
    finally:
        await browser.aclose()


@pytest.mark.asyncio
async def test_private_redirect_is_not_returned(runtime, monkeypatch) -> None:
    def redirect(*args, **kwargs):
        runtime.page.url = "http://127.0.0.1"
        return SimpleNamespace(status=200)

    runtime.page.goto.side_effect = redirect
    monkeypatch.setattr(
        browser_tools,
        "_resolve_addresses",
        lambda host: ["127.0.0.1"] if host == "127.0.0.1" else ["8.8.8.8"],
    )
    browser = BrowserToolset()
    try:
        with pytest.raises(ToolError, match="Private and internal"):
            await browser.browser_open(None, "https://example.com")
        runtime.page.locator.assert_not_called()
    finally:
        await browser.aclose()


@pytest.mark.asyncio
async def test_request_filter_aborts_private_subresources(monkeypatch) -> None:
    monkeypatch.setattr(browser_tools, "_resolve_addresses", lambda host: ["10.0.0.1"])
    route = SimpleNamespace(
        request=SimpleNamespace(url="https://private.example.com"),
        abort=AsyncMock(),
        continue_=AsyncMock(),
    )
    await BrowserToolset()._route_request(route)
    route.abort.assert_awaited_once_with("blockedbyclient")
    route.continue_.assert_not_awaited()


@pytest.mark.asyncio
async def test_request_filter_allows_public_requests(monkeypatch) -> None:
    monkeypatch.setattr(browser_tools, "_resolve_addresses", lambda host: ["8.8.8.8"])
    route = SimpleNamespace(
        request=SimpleNamespace(url="https://example.com"),
        abort=AsyncMock(),
        continue_=AsyncMock(),
    )
    await BrowserToolset()._route_request(route)
    route.continue_.assert_awaited_once()
    route.abort.assert_not_awaited()


@pytest.mark.asyncio
async def test_allowlist_accepts_subdomains_but_not_lookalikes(monkeypatch) -> None:
    monkeypatch.setenv("ARIANA_BROWSER_ALLOWED_HOSTS", "example.com")
    monkeypatch.setattr(browser_tools, "_resolve_addresses", lambda host: ["8.8.8.8"])
    browser = BrowserToolset()
    await browser._validate_url("https://news.example.com")
    with pytest.raises(ToolError, match="allowlist"):
        await browser._validate_url("https://notexample.com")


@pytest.mark.asyncio
async def test_mixed_public_private_dns_answers_are_blocked(monkeypatch) -> None:
    monkeypatch.setattr(
        browser_tools, "_resolve_addresses", lambda host: ["8.8.8.8", "10.0.0.1"]
    )
    with pytest.raises(ToolError, match="Private and internal"):
        await BrowserToolset()._validate_url("https://example.com")


@pytest.mark.asyncio
async def test_page_preview_is_bounded(runtime, monkeypatch) -> None:
    monkeypatch.setenv("ARIANA_BROWSER_MAX_TEXT_LENGTH", "5")
    browser = BrowserToolset()
    try:
        assert (await browser.browser_open(None, "https://example.com"))[
            "text"
        ] == "hello"
    finally:
        await browser.aclose()
