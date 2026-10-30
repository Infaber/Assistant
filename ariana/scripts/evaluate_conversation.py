"""Small opt-in Gemini Live comparison using fictional turns, no app tools or mic.

Pass the previous composed instructions with --before. The default is eight model
turns total. Output is private; audio export is optional and needs human listening.
"""

import argparse
import asyncio
import json
import os
import sys
import tempfile
import wave
from pathlib import Path

from dotenv import load_dotenv

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))


async def compare(args):
    from livekit.agents import Agent, AgentSession
    from livekit.agents.voice.io import AudioOutput, AudioOutputCapabilities

    from instructions import configured_instructions
    from model_config import realtime_model

    class Sink(AudioOutput):
        def __init__(self):
            super().__init__(
                label="fictional-evaluation",
                capabilities=AudioOutputCapabilities(pause=False),
            )
            self.frames = []
            self.position = 0
            self.rate = 24000
            self.channels = 1

        async def capture_frame(self, frame):
            await super().capture_frame(frame)
            self.frames.append(bytes(frame.data))
            self.rate = frame.sample_rate
            self.channels = frame.num_channels
            self.position += frame.samples_per_channel / frame.sample_rate

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

    cases = json.loads((PROJECT / "evaluations/conversations.json").read_text())
    selected = [row for row in cases if row["id"] in args.case]
    if (
        len(selected) != len(set(args.case))
        or sum(len(row["turns"]) for row in selected) > 8
    ):
        raise ValueError(
            "Choose existing case IDs totalling at most eight turns per version."
        )
    key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not key:
        raise ValueError("Set GOOGLE_API_KEY in the environment or ariana/.env.local.")
    results = []
    for version, instructions in [
        ("before", args.before.read_text()),
        ("after", configured_instructions()),
    ]:
        for case in selected:
            session = AgentSession(userdata={})
            sink = Sink()
            session.output.audio = sink
            replies = []

            @session.on("conversation_item_added")
            def on_item(event, replies=replies):
                if getattr(event.item, "role", None) == "assistant":
                    replies.append(event.item.text_content)

            try:
                await session.start(
                    agent=Agent(
                        instructions=instructions, llm=realtime_model(key), tools=[]
                    )
                )
                for index, turn in enumerate(case["turns"]):
                    replies.clear()
                    sink.frames.clear()
                    speech = session.generate_reply(user_input=turn)
                    await asyncio.wait_for(speech, 45)
                    if speech.exception():
                        raise RuntimeError("Evaluation turn did not complete")
                    row = {
                        "version": version,
                        "case": case["id"],
                        "user": turn,
                        "assistant": " ".join(replies),
                    }
                    results.append(row)
                    print(json.dumps(row, ensure_ascii=False), flush=True)
                    if args.audio_dir:
                        args.audio_dir.mkdir(parents=True, exist_ok=True)
                        audio = (
                            args.audio_dir / f"{version}-{case['id']}-{index + 1}.wav"
                        )
                        with wave.open(str(audio), "wb") as output:
                            output.setnchannels(sink.channels)
                            output.setsampwidth(2)
                            output.setframerate(sink.rate)
                            output.writeframes(b"".join(sink.frames))
                        audio.chmod(0o600)
            finally:
                await session.aclose()
                # Preserve completed turns even when a later provider request fails.
                args.output.write_text(
                    json.dumps(results, indent=2, ensure_ascii=False)
                )
                args.output.chmod(0o600)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", required=True, type=Path)
    parser.add_argument("--case", action="append", default=[])
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--audio-dir", type=Path)
    args = parser.parse_args()
    args.case = args.case or ["venting", "disagreement"]
    load_dotenv(PROJECT / ".env.local")
    with tempfile.TemporaryDirectory(prefix="ariana-evaluation-") as isolated:
        os.environ["ARIANA_PREFERENCES_PATH"] = str(Path(isolated) / "preferences.json")
        asyncio.run(compare(args))


if __name__ == "__main__":
    main()
