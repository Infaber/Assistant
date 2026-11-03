"""Pinned free English wake model, downloaded once outside the repository."""

import os
from pathlib import Path

MODEL_NAME = "sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01"
MODEL_URL = f"https://github.com/k2-fsa/sherpa-onnx/releases/download/kws-models/{MODEL_NAME}.tar.bz2"
MODEL_SHA256 = "f170013b4716e41b62b9bfd809687c207cef798ef9bc6534d524e17af9b6561a"
STEM = "epoch-12-avg-2-chunk-16-left-64"


def model_directory():
    default = Path.home() / "Library/Application Support/Ariana/wake-word"
    return Path(os.getenv("ARIANA_WAKE_WORD_MODEL_DIR") or default).expanduser()


def model_files(directory):
    directory = Path(directory)
    return {
        "encoder": directory / f"encoder-{STEM}.int8.onnx",
        "decoder": directory / f"decoder-{STEM}.int8.onnx",
        "joiner": directory / f"joiner-{STEM}.int8.onnx",
        "tokens": directory / "tokens.txt",
        "keywords_file": directory / "ariana-keywords.txt",
    }


def configured_phrase(directory):
    import hashlib
    import json

    try:
        directory = Path(directory)
        metadata = json.loads((directory / "wake-phrase.json").read_text())
        phrase = metadata["phrase"]
        if (
            not isinstance(phrase, str)
            or not 1 <= len(phrase) <= 60
            or not all(c.isalpha() or c == " " for c in phrase)
        ):
            return "Custom phrase"
        digest = hashlib.sha256(
            model_files(directory)["keywords_file"].read_bytes()
        ).hexdigest()
        return phrase if metadata.get("keywords_sha256") == digest else "Custom phrase"
    except (OSError, ValueError, KeyError, TypeError):
        return "Custom phrase"
