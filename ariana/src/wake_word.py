"""Optional local Porcupine helper. Only wake/state events leave this process."""

import json
import os
import queue
import sys
import threading
import time
from contextlib import suppress
from pathlib import Path


class WakeDetector:
    def __init__(
        self, engine, recorder, emit, clock=time.monotonic, state_changed=None
    ):
        self.engine, self.recorder, self.emit, self.clock = (
            engine,
            recorder,
            emit,
            clock,
        )
        self.enabled = False
        self.state_changed = state_changed
        self.last_detection = float("-inf")

    def enable(self, enabled):
        if enabled == self.enabled:
            return
        if enabled:
            self.recorder.start()
        else:
            self.recorder.stop()
        self.enabled = enabled
        if self.state_changed:
            self.state_changed(enabled)

    def frame(self):
        if not self.enabled:
            return
        detected = self.engine.process(self.recorder.read()) >= 0
        now = self.clock()
        if detected and now - self.last_detection >= 3:
            self.last_detection = now
            # Stop capture immediately; native state must explicitly re-arm us.
            self.enable(False)
            self.emit({"event": "wake"})

    def close(self):
        if self.enabled:
            self.recorder.stop()
        self.recorder.delete()
        self.engine.delete()


def output(message):
    print(json.dumps(message), flush=True)


def main():
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env.local")
    key = os.getenv("PORCUPINE_ACCESS_KEY", "")
    model = Path(os.getenv("ARIANA_WAKE_WORD_MODEL", ""))
    if not key or model.suffix != ".ppn" or not model.is_file():
        output({"event": "error", "code": "setup"})
        return 2
    engine = recorder = detector = None
    try:
        import pvporcupine
        from pvrecorder import PvRecorder

        engine = pvporcupine.create(access_key=key, keyword_paths=[str(model)])
        recorder = PvRecorder(device_index=-1, frame_length=engine.frame_length)
        detector = WakeDetector(
            engine,
            recorder,
            output,
            state_changed=lambda enabled: output(
                {"event": "listening", "enabled": enabled}
            ),
        )
        commands = queue.Queue()

        def receive():
            for line in sys.stdin:
                try:
                    message = json.loads(line)
                    if isinstance(message, dict) and isinstance(
                        message.get("enabled"), bool
                    ):
                        commands.put(message["enabled"])
                except (ValueError, TypeError):
                    pass
            commands.put(None)

        threading.Thread(target=receive, daemon=True).start()
        output({"event": "ready"})
        while True:
            try:
                # No recorder reads or polling spin while disabled.
                enabled = commands.get(timeout=0 if detector.enabled else None)
                if enabled is None:
                    break
                detector.enable(enabled)
            except queue.Empty:
                detector.frame()
        return 0
    except Exception:
        # SDK/device exceptions can contain private configuration; never forward them.
        output({"event": "error", "code": "microphone_or_setup"})
        return 2
    finally:
        if detector:
            with suppress(Exception):
                detector.close()
        else:
            if recorder:
                with suppress(Exception):
                    recorder.delete()
            if engine:
                with suppress(Exception):
                    engine.delete()


if __name__ == "__main__":
    raise SystemExit(main())
