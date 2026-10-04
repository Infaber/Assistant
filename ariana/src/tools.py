import asyncio
import logging

from langchain_community.tools import DuckDuckGoSearchRun
from livekit.agents import RunContext, function_tool


@function_tool
async def search_web(context: RunContext, query: str):
    """
    Search the public web for the user's query.

    Use this whenever the user asks to search, look up, find, check current
    information, or show results from the web. Return the search results to
    Ariana so she can summarize them for the user.
    """

    try:
        result = await asyncio.to_thread(
            DuckDuckGoSearchRun().run,
            tool_input=query,
        )
        logging.info(f"Web search result for query '{query}': {result}")
        return result
    except Exception as e:
        logging.error(f"Error during web search for query '{query}': {e}")
        raise
