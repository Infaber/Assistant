"""Local-only inference policy. No arbitrary endpoints, cloud tags or auto downloads."""

import os
from pathlib import Path
from urllib.parse import urlsplit

DEFAULT_LOCAL_MODEL = "ariana-local:8b"


def local_url():
    value = os.getenv("ARIANA_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
    url = urlsplit(value)
    if (
        url.scheme != "http"
        or url.hostname not in {"127.0.0.1", "localhost", "::1"}
        or url.username
        or url.password
        or url.path
        or url.query
        or url.fragment
    ):
        raise ValueError(
            "Ollama must use an HTTP loopback endpoint without credentials or a path."
        )
    return value


def local_model():
    model = os.getenv("ARIANA_LOCAL_MODEL", DEFAULT_LOCAL_MODEL).strip()
    if (
        not model
        or len(model) > 120
        or any(c.isspace() for c in model)
        or "cloud" in model.casefold()
    ):
        raise ValueError("Choose a downloaded local Ollama model, not a cloud model.")
    return model


def voice_path():
    return Path(
        os.getenv(
            "ARIANA_LOCAL_VOICE_PATH",
            Path.home() / "Library/Application Support/Ariana/local-voice",
        )
    )


def voice_files():
    root = voice_path()
    whisper = root / "sherpa-onnx-whisper-base.en"
    kokoro = root / "kokoro-multi-lang-v1_0"
    required = [
        whisper / "base.en-encoder.int8.onnx",
        whisper / "base.en-decoder.int8.onnx",
        whisper / "base.en-tokens.txt",
        kokoro / "model.onnx",
        kokoro / "voices.bin",
        kokoro / "tokens.txt",
        kokoro / "espeak-ng-data",
    ]
    if any(not path.exists() for path in required):
        raise ValueError(
            "Local speech models are missing. Run ariana/scripts/setup_local_voice.py first."
        )
    return whisper, kokoro
