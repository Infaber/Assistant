"""One model policy shared by startup, recovery and session refresh."""

import os

from google.genai import types
from livekit.plugins import google

DEFAULT_MODEL = "gemini-3.8-live"
EXTENDED_MODEL = "gemini-3.8-live-extended-thinking"


def configured_model() -> str:
    return os.getenv("ARIANA_GOOGLE_MODEL", "").strip() or DEFAULT_MODEL


def realtime_model(api_key: str, model_name: str = ""):
    model = model_name.strip() or configured_model()
    if model.removeprefix("models/") == EXTENDED_MODEL:
        raise ValueError(
            "Extended Live thinking is not enabled: the installed adapter must first "
            "support interaction_status and background reasoning safely. Use gemini-3.8-live."
        )
    options = {}
    if model.removeprefix("models/") == DEFAULT_MODEL:
        # Google explicitly supports blocking compatibility for 3.8 Live. Preserve
        # Ariana's serial tool/result flow; never send removed proactive/affective flags.
        options["tool_behavior"] = types.Behavior.BLOCKING
    return google.realtime.RealtimeModel(
        model=model, voice="Achernar", language="en-GB", api_key=api_key, **options
    )
