"""Compile and run the small native macOS Accessibility helper once per source version."""

import hashlib
import json
import subprocess
import tempfile
import threading
from pathlib import Path


class NativeBuildError(OSError):
    """Actionable setup failure, safe to return to the caller."""


_BUILD_LOCK = threading.Lock()


def _binary() -> Path:
    source = Path(__file__).with_name("desktop.swift")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()[:20]
    folder = Path(tempfile.gettempdir()) / "ariana-native-mac" / digest
    binary = folder / "desktop"
    with _BUILD_LOCK:
        if not binary.is_file():
            folder.mkdir(parents=True, exist_ok=True)
            result = subprocess.run(
                ["xcrun", "swiftc", str(source), "-o", str(binary)],
                capture_output=True,
                text=True,
                timeout=90,
                check=False,
            )
            if result.returncode:
                raise NativeBuildError(
                    "Native Mac helper could not compile. Install Apple Command Line Tools with xcode-select --install."
                )
    return binary


def run(request: dict) -> dict:
    try:
        binary = _binary()
    except NativeBuildError as error:
        return {"error": str(error), "code": "build_failed"}
    result = subprocess.run(
        [str(binary), json.dumps(request)],
        capture_output=True,
        text=True,
        timeout=8,
        check=False,
    )
    if result.returncode:
        raise OSError(result.stderr.strip() or "Native Mac helper failed")
    return json.loads(result.stdout)
