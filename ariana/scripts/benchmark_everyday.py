"""Opt-in real-model speech benchmark with fictional apps and temporary local memory.

No microphone, real app operations or personal memory. Measures text submission to
first server audio frame, not microphone-to-speaker latency. Local inference only.
"""

import argparse
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from time import monotonic

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

CASES = [
    ("quick_answer", "What is two plus two? Short answer."),
    ("lights", "Turn my desk lights on."),
    ("music", "Pause Spotify."),
    ("calendar", "What is on my calendar today?"),
    ("memory_save", "Remember my test rover uses an ESP32."),
    ("memory_recall", "Which controller does my test rover use?"),
]


async def benchmark(args):
    from livekit.agents import AgentSession, mock_tools
    from livekit.agents.llm import ToolError, Toolset
    from livekit.agents.llm.tool_context import get_function_info
    from livekit.agents.voice.io import AudioOutput, AudioOutputCapabilities

    from agent import Assistant
    from home_assistant_simulation import fixture_client
    from local_config import local_model
    from local_models import prepare_local
    from mac_simulation import SpotifyFixture
    from memory_tools import MemoryStore
    from performance import install_performance

    class Sink(AudioOutput):
        def __init__(self):
            super().__init__(
                label="synthetic-benchmark",
                capabilities=AudioOutputCapabilities(pause=False),
            )
            self.position, self.first = 0, None

        async def capture_frame(self, frame):
            await super().capture_frame(frame)
            if self.first is None:
                self.first = monotonic()
            self.position += frame.duration

        def flush(self):
            super().flush()
            if self.position:
                self.on_playback_finished(
                    playback_position=self.position, interrupted=False
                )
            self.position = 0

        def clear_buffer(self):
            if self.position:
                self.on_playback_finished(
                    playback_position=self.position, interrupted=True
                )
            self.position = 0

    await prepare_local()
    session = AgentSession(userdata={"_ai_mode": "local"})
    sink = Sink()
    session.output.audio = sink
    performance = install_performance(session)
    client, api = fixture_client("ha_lights")
    spotify = SpotifyFixture()
    spotify.state = "playing"
    session.userdata.update(_ha_client=client, _spotify_simulator=spotify.run)
    calendar_calls, forbidden = [], []

    def calendar(context):
        calendar_calls.append(True)
        return {
            "verified": True,
            "events": [
                {"title": "Fictional robotics lab", "start": "14:00", "end": "15:00"}
            ],
        }

    def blocked(*args, **kwargs):
        forbidden.append(True)
        raise ToolError(
            "This benchmark does not provide this app. No operation occurred."
        )

    ready = asyncio.Event()

    async def on_ready(mode):
        assert mode == "local"
        ready.set()

    agent = Assistant(mode="local", on_ready=on_ready)
    allowed = {
        "memory_manage",
        "task_status",
        "home_assistant_find",
        "home_assistant_inventory",
        "home_assistant_get_state",
        "home_assistant_control",
        "spotify_control",
    }

    def flatten(tools):
        for tool in tools:
            if isinstance(tool, Toolset):
                yield from flatten(tool.tools)
            else:
                yield tool

    mocks = {
        get_function_info(tool).name: blocked
        for tool in flatten(agent.tools)
        if get_function_info(tool).name not in allowed
    }
    mocks["calendar_today"] = calendar
    mock_tools(Assistant, mocks, session=session)
    rows, replies = [], []
    checks_passed = False

    @session.on("conversation_item_added")
    def on_item(event):
        if getattr(event.item, "role", None) == "assistant":
            replies.append(event.item.text_content)

    try:
        await session.start(agent=agent)
        await asyncio.wait_for(ready.wait(), 40)
        for name, prompt in CASES:
            sink.first = None
            replies.clear()
            start = monotonic()
            speech = session.generate_reply(user_input=prompt)
            await asyncio.wait_for(speech, 120)
            if speech.exception():
                raise RuntimeError("Benchmark turn failed")
            row = {
                "case": name,
                "first_audio_seconds": round(sink.first - start, 3)
                if sink.first
                else None,
                "complete_seconds": round(monotonic() - start, 3),
                "reply": " ".join(replies),
            }
            rows.append(row)
            print(json.dumps(row), flush=True)
        assert len([event for event in api.events if event[0] == "POST"]) == 1, (
            "Expected exactly one fake light command"
        )
        assert [event["action"] for event in spotify.events] == ["pause"], (
            "Expected exactly one fake pause"
        )
        assert len(calendar_calls) == 1, "Expected exactly one fake calendar read"
        assert not forbidden, "Attempted an unavailable tool"
        assert "ESP32" in rows[-1]["reply"].upper(), "Fictional memory recall failed"
        memories = MemoryStore().run({"action": "recall", "query": "ESP32"})
        assert "esp32" in json.dumps(memories).lower(), "Fictional memory was not saved"
        checks_passed = True
    finally:
        await session.aclose()
        report = {
            "model": local_model(),
            "scope": "after backend readiness: text submission to first server audio frame; synthetic output and fictional apps",
            "checks_passed": checks_passed,
            "turns": rows,
            "timings": performance.summary(),
            "fake_light_posts": len([e for e in api.events if e[0] == "POST"]),
            "fake_spotify_calls": len(spotify.events),
            "fake_calendar_reads": len(calendar_calls),
        }
        # Create with private permissions before writing any generated content.
        with os.fdopen(
            os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w"
        ) as output:
            os.chmod(args.output, 0o600)
            json.dump(report, output, indent=2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="ariana-everyday-") as folder:
        os.environ.update(
            ARIANA_MEMORY_PATH=folder + "/memory.sqlite3",
            ARIANA_PREFERENCES_PATH=folder + "/preferences.json",
            ARIANA_CAMERA_EVENTS_ENABLED="false",
        )
        asyncio.run(benchmark(args))


if __name__ == "__main__":
    main()
