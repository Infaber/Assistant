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
