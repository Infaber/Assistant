import pytest
from livekit.agents.llm import ToolError

from browser_tools import BrowserToolset, _clean_text, _is_private_address


@pytest.mark.asyncio
async def test_browser_toolset_starts_and_closes_webkit() -> None:
    browser = BrowserToolset(headless=True)

    await browser.setup()
    try:
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
