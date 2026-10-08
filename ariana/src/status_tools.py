"""Read-only configuration diagnostics; never returns credentials."""

import asyncio
import os
import subprocess
import sys

from livekit.agents import function_tool

from mac_native import run as run_native


@function_tool
async def assistant_status() -> dict:
    """Check Ariana's local configuration when asked what is working or why an
    integration fails. Returns presence of settings, not API secrets. Configuration
    presence does not prove a network connection or credentials are valid. Desktop
    permission is checked separately on Mac. Never claim Apple Automation has been
    granted from this report; macOS prompts are app-specific.
    """
    report = {
        "livekit_configured": all(
            os.getenv(key, "").strip()
            for key in ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET")
        ),
        "google_configured": bool(
            os.getenv("GOOGLE_API_KEY", "").strip()
            or os.getenv("GEMINI_API_KEY", "").strip()
        ),
        "home_assistant_configured": all(
            os.getenv(key, "").strip()
            for key in ("HOME_ASSISTANT_URL", "HOME_ASSISTANT_TOKEN")
        ),
        "camera_access_enabled": os.getenv("ARIANA_CAMERA_ENABLED", "false").lower()
        == "true",
        "frigate_auth_configured": bool(
            os.getenv("FRIGATE_TOKEN")
            or (os.getenv("FRIGATE_USERNAME") and os.getenv("FRIGATE_PASSWORD"))
        ),
        "camera_event_subscription_enabled": os.getenv(
            "ARIANA_CAMERA_EVENTS_ENABLED", "false"
        ).lower()
        == "true",
        "local_mac": sys.platform == "darwin",
        "note": "Configured means settings are present, not that connection or authentication was verified. Apple apps need their individual Automation permissions.",
    }
    if sys.platform == "darwin":
        try:
            report["desktop"] = await asyncio.to_thread(
                run_native, {"action": "status"}
            )
        except (OSError, ValueError, subprocess.TimeoutExpired):
            report["desktop"] = {"error": "Desktop status could not be checked."}
    return report
