import asyncio
import logging
import os
import subprocess
import sys
from html import escape
from urllib.parse import urlparse

import httpx
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


@function_tool
async def calendar_today(context: RunContext) -> str:
    """List today's events from the local macOS Calendar app."""
    if sys.platform != "darwin":
        return (
            "Apple Calendar tools are available only when Ariana runs locally on a Mac."
        )

    script = """
on run
    set dayStart to (current date)
    set time of dayStart to 0
    set dayEnd to dayStart + (1 * days)
    set results to {}
    tell application "Calendar"
        repeat with calendarItem in calendars
            repeat with eventItem in (every event of calendarItem whose start date < dayEnd and end date > dayStart)
                set end of results to (summary of eventItem) & " at " & (start date of eventItem as text)
            end repeat
        end repeat
    end tell
    if results is {} then return "No events scheduled for today."
    set AppleScript's text item delimiters to linefeed
    return results as text
end run
"""
    try:
        output = await asyncio.to_thread(_run_osascript, script, [])
    except OSError:
        return "I couldn't access Apple Calendar. Check macOS Automation permissions for Ariana."
    return output or "No events scheduled for today."


@function_tool
async def calendar_create_event(
    context: RunContext,
    title: str,
    start_time: str,
    end_time: str,
    confirmed: bool = False,
) -> str:
    """Create a Calendar event only after the user explicitly confirms it."""
    if sys.platform != "darwin":
        return (
            "Apple Calendar tools are available only when Ariana runs locally on a Mac."
        )
    if not confirmed:
        return (
            f"I can add '{title}' from {start_time} to {end_time}. "
            "Please confirm before I create it."
        )
    if not title.strip() or not start_time.strip() or not end_time.strip():
        return "I need a title, start time, and end time before creating the event."

    script = """
on run argv
    set eventTitle to item 1 of argv
    set eventStart to item 2 of argv
    set eventEnd to item 3 of argv
    tell application "Calendar"
        set targetCalendar to first calendar
        tell targetCalendar
            make new event with properties {summary:eventTitle, start date:date eventStart, end date:date eventEnd}
        end tell
    end tell
    return "Calendar event created."
end run
"""
    try:
        return await asyncio.to_thread(
            _run_osascript,
            script,
            [title.strip(), start_time.strip(), end_time.strip()],
        )
    except OSError:
        return "I couldn't access Apple Calendar. Check macOS Automation permissions for Ariana."


@function_tool
async def reminders_today(context: RunContext) -> str:
    """List incomplete reminders due today from the local macOS Reminders app."""
    if sys.platform != "darwin":
        return "Apple Reminders tools are available only when Ariana runs locally on a Mac."

    script = """
on run
    set dayStart to (current date)
    set time of dayStart to 0
    set dayEnd to dayStart + (1 * days)
    set results to {}
    tell application "Reminders"
        repeat with listItem in lists
            repeat with reminderItem in (reminders of listItem whose completed is false)
                if due date of reminderItem is not missing value then
                    if due date of reminderItem < dayEnd and due date of reminderItem >= dayStart then
                        set end of results to (name of reminderItem) & " at " & (due date of reminderItem as text)
                    end if
                end if
            end repeat
        end repeat
    end tell
    if results is {} then return "No reminders due today."
    set AppleScript's text item delimiters to linefeed
    return results as text
end run
"""
    try:
        output = await asyncio.to_thread(_run_osascript, script, [])
    except OSError:
        return "I couldn't access Apple Reminders. Check macOS Automation permissions for Ariana."
    return output or "No reminders due today."


@function_tool
async def reminders_create(
    context: RunContext,
    title: str,
    due_time: str = "",
    confirmed: bool = False,
) -> str:
    """Create a reminder only after the user explicitly confirms it."""
    if sys.platform != "darwin":
        return "Apple Reminders tools are available only when Ariana runs locally on a Mac."
    if not confirmed:
        due_text = f" due {due_time}" if due_time.strip() else ""
        return f"I can create the reminder '{title}'{due_text}. Please confirm before I create it."
    if not title.strip():
        return "I need a title before creating the reminder."

    script = """
on run argv
    set reminderTitle to item 1 of argv
    set reminderDue to item 2 of argv
    tell application "Reminders"
        set targetList to first list
        if reminderDue is "" then
            make new reminder at end of reminders of targetList with properties {name:reminderTitle}
        else
            make new reminder at end of reminders of targetList with properties {name:reminderTitle, due date:date reminderDue}
        end if
    end tell
    return "Reminder created."
end run
"""
    try:
        return await asyncio.to_thread(
            _run_osascript,
            script,
            [title.strip(), due_time.strip()],
        )
    except OSError:
        return "I couldn't access Apple Reminders. Check macOS Automation permissions for Ariana."


@function_tool
async def mail_unread(context: RunContext) -> str:
    """List a concise summary of recent unread messages from local macOS Mail."""
    if sys.platform != "darwin":
        return "Apple Mail tools are available only when Ariana runs locally on a Mac."

    script = """
on run
    set results to {}
    tell application "Mail"
        repeat with messageItem in (messages of inbox whose read status is false)
            set end of results to (sender of messageItem) & " | " & (subject of messageItem)
            if (count of results) is 10 then exit repeat
        end repeat
    end tell
    if results is {} then return "No unread messages."
    set AppleScript's text item delimiters to linefeed
    return results as text
end run
"""
    try:
        output = await asyncio.to_thread(_run_osascript, script, [])
    except OSError:
        return "I couldn't access Apple Mail. Check macOS Automation permissions for Ariana."
    return output or "No unread messages."


@function_tool
async def mail_send(
    context: RunContext,
    recipient: str,
    subject: str,
    body: str,
    confirmed: bool = False,
) -> str:
    """Send an email only after the user explicitly confirms its contents."""
    if sys.platform != "darwin":
        return "Apple Mail tools are available only when Ariana runs locally on a Mac."
    if not confirmed:
        return (
            f"I can send an email to {recipient} with the subject '{subject}'. "
            "Please confirm before I send it."
        )
    if not recipient.strip() or not subject.strip() or not body.strip():
        return "I need a recipient, subject, and message before sending the email."

    script = """
on run argv
    set recipientAddress to item 1 of argv
    set messageSubject to item 2 of argv
    set messageBody to item 3 of argv
    tell application "Mail"
        set outgoingMessage to make new outgoing message with properties {subject:messageSubject, content:messageBody}
        tell outgoingMessage
            make new to recipient at end of to recipients with properties {address:recipientAddress}
        end tell
        send outgoingMessage
    end tell
    return "Email sent."
end run
"""
    try:
        return await asyncio.to_thread(
            _run_osascript,
            script,
            [recipient.strip(), subject.strip(), body.strip()],
        )
    except OSError:
        return "I couldn't send the email through Apple Mail. Check macOS Automation permissions for Ariana."


@function_tool
async def notes_create(context: RunContext, title: str, body: str) -> str:
    """Create a new Apple Notes note when the user explicitly asks to save a note.

    Supply a concise title and the requested plain-text contents. Creates in the
    default Notes account and folder on the Mac running Ariana. Does not read,
    edit, or delete existing notes.
    """
    if sys.platform != "darwin":
        return "Apple Notes tools are available only when Ariana runs locally on a Mac."
    title, body = title.strip(), body.strip()
    if not title or not body:
        return "I need a title and contents before creating the note."

    # Notes expects HTML. Escape user text and pass it as arguments, never code.
    html_body = (
        f"<h1>{escape(title)}</h1><div>{escape(body).replace(chr(10), '<br>')}</div>"
    )
    script = """
on run argv
    set noteTitle to item 1 of argv
    set noteBody to item 2 of argv
    tell application "Notes"
        set targetFolder to default folder of default account
        make new note at targetFolder with properties {name:noteTitle, body:noteBody}
    end tell
    return "Note created."
end run
"""
    try:
        return await asyncio.to_thread(_run_osascript, script, [title, html_body], 30)
    except subprocess.TimeoutExpired:
        return "Notes did not respond in time. Check the Notes app before trying again; the note may already exist."
    except OSError:
        return "I couldn't create the note. Check that Notes has an account and allow access in macOS System Settings > Privacy & Security > Automation."


def _run_osascript(
    script: str, arguments: list[str], timeout: float | None = None
) -> str:
    result = subprocess.run(
        ["osascript", "-l", "AppleScript", "-e", script, *arguments],
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise OSError(result.stderr.strip() or "AppleScript failed")
    return result.stdout.strip()
