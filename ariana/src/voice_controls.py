"""Authenticated UI controls. Voice changes are saved for a fresh connection."""

import asyncio
import json
import os
import time

from performance import for_session
from personality import STYLE_CHOICES, STYLE_END, STYLE_START, effective_style
from preferences_tools import PreferencesStore
from voice_options import SAMPLE, SAMPLES, VOICES

METHOD = "ariana.voice-settings"
SETTINGS = STYLE_CHOICES.keys() | {"google_voice", "turn_end_pause", "local_speed"}


class VoiceControls:
    def __init__(self, room, session, store=None, clock=time.monotonic):
        self.room, self.session = room, session
        self.store = store or PreferencesStore()
        self.clock = clock
        self.last_sample = -float("inf")
        self.lock = asyncio.Lock()

    def start(self):
        self.room.local_participant.register_rpc_method(METHOD, self.rpc)

    async def close(self):
        self.room.local_participant.unregister_rpc_method(METHOD)

    def idle(self):
        from ai_modes import action_running
        from camera_delivery import delivery_pending

        companion = self.session.userdata.get("_companion_bridge")
        return (
            not (companion and (companion.uploads or companion.lock.locked()))
            and not self.session.userdata.get("_mode_switching")
            and self.session.agent_state in {"idle", "listening"}
            and self.session.user_state != "speaking"
            and not action_running(self.session)
            and not delivery_pending(self.session)
        )

    async def rpc(self, invocation):
        if (
            invocation.caller_identity not in self.room.remote_participants
            or not invocation.caller_identity.startswith("guest-")
        ):
            return json.dumps(
                {"error": "Only the connected user can change voice settings."}
            )
        try:
            request = json.loads(invocation.payload)
            action = request.get("action")
            if action == "status":
                preferences = await asyncio.to_thread(self.store.read)
                default_voice = (
                    os.getenv("ARIANA_GOOGLE_VOICE", "").strip() or "Sulafat"
                )
                active = dict(getattr(self.session.current_agent, "voice_settings", {}))
                # Read actual active instructions: saved preferences may be pending,
                # while spoken style updates can already have changed this agent.
                instructions = (
                    getattr(self.session.current_agent, "instructions", "") or ""
                )
                block = instructions.partition(STYLE_START)[2].partition(STYLE_END)[0]
                for line in block.splitlines():
                    key, separator, value = line.partition(": ")
                    if (
                        separator
                        and key in STYLE_CHOICES
                        and value in STYLE_CHOICES[key]
                    ):
                        active[key] = value
                return json.dumps(
                    {
                        "preferences": {
                            key: value
                            for key, value in preferences.items()
                            if key in SETTINGS
                        },
                        "local_speeds": ["0.8", "1.0", "1.2"],
                        "effective": {
                            "local_speed": preferences.get("local_speed", "1.0"),
                            **effective_style(preferences),
                            "google_voice": preferences.get(
                                "google_voice", default_voice
                            ),
                            "turn_end_pause": preferences.get(
                                "turn_end_pause", "provider"
                            ),
                        },
                        "active_settings": active,
                        "mode": getattr(
                            self.session.current_agent, "ai_mode", "normal"
                        ),
                        "configured_default_voice": default_voice,
                        "samples": SAMPLES,
                        "voices": sorted(VOICES),
                        "styles": {
                            key: sorted(value) for key, value in STYLE_CHOICES.items()
                        },
                        "active_voice": getattr(
                            self.session.current_agent, "voice_name", "unknown"
                        ),
                        "sample_text": SAMPLE,
                        "diagnostics": for_session(self.session).summary(),
                        "response_times_ms": [
                            row["milliseconds"]
                            for row in for_session(self.session).samples
                            if row["stage"] == "e2e_latency"
                        ],
                        "backchannel_audio_supported": False,
                    }
                )
            if action == "save":
                values = request.get("values")
                reset = request.get("reset", [])
                if (
                    not isinstance(reset, list)
                    or any(key != "google_voice" for key in reset)
                    or not isinstance(values, dict)
                    or (not values and not reset)
                    or set(values) - SETTINGS
                    or set(reset) & set(values)
                ):
                    raise ValueError("Choose supported voice/style settings.")
                result = await asyncio.to_thread(
                    self.store.run,
                    {"action": "configure", "values": values, "reset": reset},
                )
                return json.dumps(
                    {
                        "saved": True,
                        "preferences": {
                            key: value
                            for key, value in result["preferences"].items()
                            if key in SETTINGS
                        },
                        "applies": "next_connection",
                    }
                )
            if action == "standby":
                await self.session.interrupt()
                for key in (
                    "notes_pending",
                    "mac_snapshot",
                    "_camera_consent",
                    "_ha_fallback_turn",
                ):
                    self.session.userdata.pop(key, None)
                return json.dumps({"standby": True})
            if action == "sample":
                sample_id = request.get("sample", "neutral")
                if sample_id not in SAMPLES:
                    raise ValueError("Choose a fixed evaluation sample.")
                sample = SAMPLES[sample_id]
                if (
                    self.lock.locked()
                    or not self.idle()
                    or self.clock() - self.last_sample < 15
                ):
                    return json.dumps(
                        {
                            "error": "Wait until the conversation is idle and 15 seconds after the last sample."
                        }
                    )
                async with self.lock:
                    self.last_sample = self.clock()
                    self.session.generate_reply(
                        instructions="Read only this fixed voice-comparison sample, naturally and without introduction. Do not call tools or refer to conversation history. "
                        + sample,
                        tools=[],
                        tool_choice="none",
                        allow_interruptions=True,
                    )
                return json.dumps(
                    {
                        "started": True,
                        "voice": getattr(
                            self.session.current_agent, "voice_name", "unknown"
                        ),
                        "sample_text": sample,
                    }
                )
            raise ValueError("Choose status, save, sample or standby.")
        except (ValueError, TypeError, AttributeError, OSError, RuntimeError):
            return json.dumps(
                {
                    "error": "Could not apply voice controls. No automatic retry or reconnect was made."
                }
            )
