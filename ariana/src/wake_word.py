"""Optional local Sherpa-ONNX helper. Only wake/state events leave this process."""

import json
import queue
import sys
import threading
import time
from contextlib import suppress
from pathlib import Path

from wake_config import model_directory, model_files


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
            self.engine.reset()
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


class KeywordEngine:
    """One CPU inference thread; stream state never crosses an arm/mute boundary."""

    def __init__(self, directory):
        import sherpa_onnx

        files = model_files(directory)
        if not all(path.is_file() for path in files.values()):
            raise FileNotFoundError("Run scripts/setup_wake_word.py first")
        self.spotter = sherpa_onnx.KeywordSpotter(
            **{key: str(value) for key, value in files.items()},
            num_threads=1,
            provider="cpu",
            keywords_score=1.0,
            keywords_threshold=0.35,
            num_trailing_blanks=2,
        )
        self.reset()

    def reset(self):
        self.stream = self.spotter.create_stream()

    def process(self, samples):
        self.stream.accept_waveform(16000, samples)
        detected = False
        while self.spotter.is_ready(self.stream):
            self.spotter.decode_stream(self.stream)
            if self.spotter.get_result(self.stream):
                detected = True
                self.spotter.reset_stream(self.stream)
        return 0 if detected else -1

    def delete(self):
        self.stream = None
        self.spotter = None


class Microphone:
    """Open the default mic only while armed; no audio files or network access."""

    def __init__(self):
        self.stream = None

    def start(self):
        import sounddevice

        stream = sounddevice.InputStream(
            samplerate=16000, channels=1, dtype="float32", blocksize=1600
        )
        try:
            stream.start()
        except Exception:
            stream.close()
            raise
        self.stream = stream

    def read(self):
        samples, overflow = self.stream.read(1600)
        if overflow:
            raise OSError("Microphone input overflow")
        return samples.reshape(-1)

    def stop(self):
        if self.stream is not None:
            try:
                self.stream.abort()
            finally:
                self.stream.close()
                self.stream = None

    def delete(self):
        self.stop()


def output(message):
    print(json.dumps(message), flush=True)


def main(check=False):
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env.local")
    engine = recorder = detector = None
    try:
        engine = KeywordEngine(model_directory())
        if check:
            output({"event": "ready", "mode": "model_check"})
            return 0
        recorder = Microphone()
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
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Load the model without opening the microphone",
    )
    raise SystemExit(main(check=parser.parse_args().check))
