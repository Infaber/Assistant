"""Download local speech weights from sherpa-onnx's official release assets."""

import hashlib
import os
import tarfile
import tempfile
from pathlib import Path

import httpx

ASSETS = [
    (
        "asr-models",
        "sherpa-onnx-whisper-base.en",
        "475bc7052ce299c007f6d5d5407ba8601f819a2867f6eecee510ed17df581542",
    ),
    (
        "tts-models",
        "kokoro-multi-lang-v1_0",
        "60703707bc05ccd48d60e1eb723f38b07d6e474795a0b6a588d7220400e0f7a4",
    ),
]


def main():
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env.local")
    root = Path(
        os.getenv(
            "ARIANA_LOCAL_VOICE_PATH",
            Path.home() / "Library/Application Support/Ariana/local-voice",
        )
    )
    root.mkdir(parents=True, exist_ok=True)
    with httpx.Client(follow_redirects=True, timeout=90) as client:
        for release, name, expected in ASSETS:
            if (root / name).is_dir():
                print(name, "already installed", flush=True)
                continue
            url = f"https://github.com/k2-fsa/sherpa-onnx/releases/download/{release}/{name}.tar.bz2"
            print("Downloading", name, flush=True)
            with tempfile.TemporaryDirectory(dir=root) as temporary:
                archive = Path(temporary) / "model.tar.bz2"
                digest = hashlib.sha256()
                with client.stream("GET", url) as response:
                    response.raise_for_status()
                    with archive.open("wb") as output:
                        for block in response.iter_bytes(1024 * 1024):
                            output.write(block)
                            digest.update(block)
                if expected and digest.hexdigest() != expected:
                    raise ValueError("Speech model checksum mismatch")
                with tarfile.open(archive) as package:
                    # Reject links/traversal, even in a trusted upstream archive.
                    for item in package.getmembers():
                        if (
                            item.issym()
                            or item.islnk()
                            or Path(item.name).is_absolute()
                            or ".." in Path(item.name).parts
                        ):
                            raise ValueError("Unsafe speech-model archive")
                    package.extractall(temporary, filter="data")
                (Path(temporary) / name).rename(root / name)
                print("Installed", name, "SHA256", digest.hexdigest(), flush=True)


if __name__ == "__main__":
    main()
