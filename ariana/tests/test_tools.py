import asyncio
import logging
from unittest.mock import Mock

import pytest
from livekit.agents.llm import ToolError

import tools


@pytest.mark.asyncio
async def test_search_returns_results_without_logging_content(monkeypatch, caplog):
    provider = Mock()
    provider.run.return_value = "private result text"
    monkeypatch.setattr(tools, "DuckDuckGoSearchRun", lambda: provider)
    with caplog.at_level(logging.INFO, logger="tools"):
        assert (
            await tools.search_web(None, "  private query  ") == "private result text"
        )
    provider.run.assert_called_once_with(tool_input="private query")
    assert "Web search completed" in caplog.text
    assert "private query" not in caplog.text
    assert "private result text" not in caplog.text


@pytest.mark.asyncio
async def test_empty_search_does_not_contact_provider(monkeypatch):
    provider = Mock()
    monkeypatch.setattr(tools, "DuckDuckGoSearchRun", provider)
    with pytest.raises(ToolError, match="what you want to search"):
        await tools.search_web(None, "   ")
    provider.assert_not_called()


@pytest.mark.asyncio
async def test_search_failure_hides_provider_details(monkeypatch, caplog):
    provider = Mock()
    provider.run.side_effect = RuntimeError("private query and provider details")
    monkeypatch.setattr(tools, "DuckDuckGoSearchRun", lambda: provider)
    with pytest.raises(ToolError, match="could not verify") as error:
        await tools.search_web(None, "private query")
    assert "private query" not in str(error.value)
    assert "private query" not in caplog.text


@pytest.mark.asyncio
async def test_slow_search_times_out(monkeypatch):
    cancelled = asyncio.Event()

    async def stalled_provider(*args):
        try:
            await asyncio.Future()
        finally:
            cancelled.set()

    monkeypatch.setattr(tools.asyncio, "to_thread", stalled_provider)
    monkeypatch.setattr(tools, "_search_timeout", lambda: 0.01)
    with pytest.raises(ToolError, match="timed out"):
        await tools.search_web(None, "opening hours")
    assert cancelled.is_set()


@pytest.mark.parametrize("value, expected", [("3", 3), ("0", 1), ("invalid", 15)])
def test_search_timeout_configuration(monkeypatch, value, expected):
    monkeypatch.setenv("ARIANA_SEARCH_TIMEOUT_SECONDS", value)
    assert tools._search_timeout() == expected
