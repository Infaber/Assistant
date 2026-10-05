import asyncio
import logging
import os

from langchain_community.tools import DuckDuckGoSearchRun
from livekit.agents import RunContext, function_tool
from livekit.agents.llm import ToolError

logger = logging.getLogger(__name__)
DEFAULT_SEARCH_TIMEOUT_SECONDS = 15


def _search_timeout() -> int:
    try:
        return max(1, int(os.environ.get("ARIANA_SEARCH_TIMEOUT_SECONDS", "15")))
    except ValueError:
        return DEFAULT_SEARCH_TIMEOUT_SECONDS


@function_tool
async def search_web(context: RunContext, query: str):
    """
    Search the public web for the user's query.

    Use this whenever the user asks to search, look up, find, check current
    information, or show results from the web. Return the search results to
    Ariana so she can summarize them for the user.
    """

    query = query.strip()
    if not query:
        raise ToolError("Tell me what you want to search for.")

    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(_run_search, query),
            timeout=_search_timeout(),
        )
        logger.info("Web search completed")
        return result
    except asyncio.TimeoutError:
        logger.warning("Web search timed out")
        raise ToolError(
            "The web search timed out. I could not verify that information; try again."
        ) from None
    except Exception:
        logger.warning("Web search failed")
        raise ToolError(
            "The web search is unavailable. I could not verify that information; "
            "try again later."
        ) from None


def _run_search(query: str) -> str:
    return DuckDuckGoSearchRun().run(tool_input=query)
