from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import tools


@pytest.mark.asyncio
async def test_legacy_search_uses_the_shared_safari_session():
    browser = SimpleNamespace(
        browser_search=AsyncMock(
            return_value={"text": "verified page", "verified": True}
        )
    )
    context = SimpleNamespace(
        session=SimpleNamespace(userdata={"_safari_browser": browser})
    )
    result = await tools.search_web(context, "opening hours")
    assert result["verified"]
    browser.browser_search.assert_awaited_once_with(context, "opening hours")
