"""Regenerate the short, non-personal thinking cues using Ariana's Achernar voice.
Run from ariana: uv run python ../frontend/scripts/generate-feedback.py
Google TTS API: https://ai.google.dev/gemini-api/docs/generate-content/speech-generation
"""

import io
import os
import wave
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

root = Path(__file__).resolve().parents[2]
load_dotenv(root / "ariana/.env.local")
client = genai.Client(
    api_key=os.getenv("GOOGLE_API_KEY") or os.environ["GEMINI_API_KEY"]
)
for name, text in [
    ("thinking", "Let me think for a moment."),
    ("moment", "One moment."),
    ("still-here", "I'm still here. Just taking a little longer."),
]:
    result = client.models.generate_content(
        model="gemini-2.5-flash-preview-tts",
        contents=f"Say this in a soft, calm, natural British voice, with no extra words: {text}",
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name="Achernar"
                    )
                )
            ),
        ),
    )
    part = next(
        p.inline_data for p in result.candidates[0].content.parts if p.inline_data
    )
    data = part.data
    if not data.startswith(b"RIFF"):
        output = io.BytesIO()
        with wave.open(output, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(24000)
            wav.writeframes(data)
        data = output.getvalue()
    with wave.open(io.BytesIO(data)) as wav:
        seconds = wav.getnframes() / wav.getframerate()
        assert 0.2 < seconds < 8
    (root / f"frontend/public/audio/{name}.wav").write_bytes(data)
    print(f"{name}: {seconds:.1f}s")
client.close()
