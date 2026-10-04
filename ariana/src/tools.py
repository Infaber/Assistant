import asyncio
import logging
import os
from urllib.parse import urlparse

import httpx
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


@function_tool
async def home_assistant_request(context: RunContext, request: str) -> str:
    """Send a natural-language smart-home request to Home Assistant."""
    base_url = os.environ.get("HOME_ASSISTANT_URL", "").strip().rstrip("/")
    token = os.environ.get("HOME_ASSISTANT_TOKEN", "").strip()

    if not base_url or not token:
        return (
            "Home Assistant is not configured. Set HOME_ASSISTANT_URL and "
            "HOME_ASSISTANT_TOKEN before using smart-home controls."
        )

    parsed_url = urlparse(base_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        return "Home Assistant is misconfigured. HOME_ASSISTANT_URL must be an HTTP or HTTPS URL."
    if parsed_url.username or parsed_url.password:
        return "Home Assistant is misconfigured. HOME_ASSISTANT_URL cannot contain credentials."

    request = request.strip()
    if not request:
        return "Tell me what you want Home Assistant to do."

    endpoint = f"{base_url}/api/conversation/process"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                endpoint,
                headers=headers,
                json={"text": request},
            )
        response.raise_for_status()
    except httpx.HTTPStatusError as error:
        if error.response.status_code in {401, 403}:
            return "Home Assistant rejected the request. Check the access token."
        return f"Home Assistant returned an HTTP {error.response.status_code} error."
    except httpx.RequestError:
        return "I couldn't reach Home Assistant right now. Check that it is online and the URL is correct."

    try:
        payload = response.json()
        speech = payload["response"]["speech"]["plain"]["speech"]
    except (ValueError, KeyError, TypeError):
        return "Home Assistant returned an unexpected response."

    if not isinstance(speech, str) or not speech.strip():
        return "Home Assistant did not return a spoken response."
    return speech.strip()


@function_tool
async def weather_forecast(context: RunContext, location: str) -> str:
    """Get the current forecast for a place using YR's location forecast API."""
    location = location.strip()
    if not location:
        return "Tell me which place you want the weather for."

    headers = {"User-Agent": "Ariana/1.0 local voice assistant"}
    try:
        async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
            geocode_response = await client.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": location, "format": "jsonv2", "limit": 1},
            )
            geocode_response.raise_for_status()
            places = geocode_response.json()
            if not places:
                return f"I couldn't find a location called {location}."

            latitude = places[0]["lat"]
            longitude = places[0]["lon"]
            display_name = places[0].get("display_name", location).split(",")[0]
            forecast_response = await client.get(
                "https://api.met.no/weatherapi/locationforecast/2.0/compact",
                params={"lat": latitude, "lon": longitude},
            )
            forecast_response.raise_for_status()
            forecast = forecast_response.json()
            current = forecast["properties"]["timeseries"][0]
            details = current["data"]["instant"]["details"]
            temperature = details["air_temperature"]
            wind_speed = details["wind_speed"]
            symbol = (
                current["data"]
                .get("next_1_hours", {})
                .get("summary", {})
                .get("symbol_code", "")
            )
    except httpx.HTTPStatusError:
        return "The weather service returned an error. Please try again shortly."
    except (httpx.RequestError, KeyError, IndexError, TypeError, ValueError):
        return "I couldn't retrieve the weather right now. Please try again shortly."

    conditions = (
        symbol.replace("_", " ") if symbol else "current conditions unavailable"
    )
    return (
        f"In {display_name}, it's {temperature:.0f} degrees Celsius with {conditions}. "
        f"Wind is around {wind_speed:.0f} meters per second."
    )
