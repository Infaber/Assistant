"""Authenticated UI controls. Voice changes are saved for a fresh connection."""

import asyncio
import json
import time

from performance import for_session
from personality import STYLE_CHOICES
from preferences_tools import PreferencesStore
from voice_options import SAMPLE, VOICES

METHOD = "ariana.voice-settings"
SETTINGS = STYLE_CHOICES.keys() | {"google_voice", "turn_end_pause"}


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
                return json.dumps(
                    {
                        "preferences": {
                            key: value
                            for key, value in (
                                await asyncio.to_thread(self.store.read)
                            ).items()
                            if key in SETTINGS
                        },
                        "voices": sorted(VOICES),
                        "styles": {
                            key: sorted(value) for key, value in STYLE_CHOICES.items()
                        },
                        "active_voice": getattr(
                            self.session.current_agent, "voice_name", "unknown"
                        ),
                        "sample_text": SAMPLE,
                        "diagnostics": for_session(self.session).summary(),
                        "backchannel_audio_supported": False,
                    }
                )
            if action == "save":
                values = request.get("values")
                if not isinstance(values, dict) or not values or set(values) - SETTINGS:
                    raise ValueError("Choose supported voice/style settings.")
                result = await asyncio.to_thread(
                    self.store.run, {"action": "configure", "values": values}
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
                        + SAMPLE,
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
                        "sample_text": SAMPLE,
                    }
                )
            raise ValueError("Choose status, save, sample or standby.")
        except (ValueError, TypeError, AttributeError, OSError, RuntimeError):
            return json.dumps(
                {
                    "error": "Could not apply voice controls. No automatic retry or reconnect was made."
                }
            )
