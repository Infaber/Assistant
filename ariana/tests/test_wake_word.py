from types import SimpleNamespace

import pytest

from wake_word import WakeDetector


class Recorder:
    def __init__(self):
        self.events = []

    def start(self):
        self.events.append("start")

    def stop(self):
        self.events.append("stop")

    def read(self):
        self.events.append("read")
        return [0] * 512

    def delete(self):
        self.events.append("delete")


def test_disabled_never_captures_and_detection_disarms():
    recorder, events = Recorder(), []
    now = [10.0]
    engine = SimpleNamespace(
        process=lambda frame: 0, delete=lambda: None, reset=lambda: None
    )
    detector = WakeDetector(engine, recorder, events.append, lambda: now[0])
    detector.frame()
    assert recorder.events == []
    detector.enable(True)
    detector.frame()
    assert events == [{"event": "wake"}] and not detector.enabled
    detector.enable(True)
    now[0] = 11
    detector.frame()
    assert len(events) == 1
    now[0] = 14
    detector.frame()
    assert len(events) == 2 and not detector.enabled
    detector.close()
    assert recorder.events[-1] == "delete"


def test_microphone_permission_error_does_not_mark_enabled():
    recorder = Recorder()

    def denied():
        raise PermissionError("microphone denied")

    recorder.start = denied
    detector = WakeDetector(
        SimpleNamespace(reset=lambda: None), recorder, lambda event: None
    )
    with pytest.raises(PermissionError):
        detector.enable(True)
    assert not detector.enabled


def test_capture_state_reports_only_successful_changes():
    recorder, states = Recorder(), []
    engine = SimpleNamespace(
        process=lambda frame: -1, delete=lambda: None, reset=lambda: None
    )
    detector = WakeDetector(
        engine, recorder, lambda event: None, state_changed=states.append
    )
    detector.enable(True)
    detector.enable(True)
    detector.enable(False)
    assert states == [True, False]


def test_rearming_discards_decoder_history():
    history = []
    engine = SimpleNamespace(
        reset=lambda: history.clear(), process=lambda frame: history.append(frame) or -1
    )
    detector = WakeDetector(engine, Recorder(), lambda event: None)
    detector.enable(True)
    detector.frame()
    assert history
    detector.enable(False)
    detector.enable(True)
    assert not history


def test_microphone_closed_on_stop_and_failed_start(monkeypatch):
    import sys

    from wake_word import Microphone

    calls = []
    stream = SimpleNamespace(
        start=lambda: calls.append("start"),
        abort=lambda: calls.append("abort"),
        close=lambda: calls.append("close"),
    )
    monkeypatch.setitem(
        sys.modules, "sounddevice", SimpleNamespace(InputStream=lambda **kwargs: stream)
    )
    microphone = Microphone()
    assert calls == []
    microphone.start()
    microphone.stop()
    microphone.delete()
    assert calls == ["start", "abort", "close"]

    def denied():
        raise PermissionError("denied")

    stream.start = denied
    with pytest.raises(PermissionError):
        microphone.start()
    assert calls[-1] == "close" and microphone.stream is None


def test_microphone_overflow_is_not_processed_as_valid_audio():
    from wake_word import Microphone

    microphone = Microphone()
    microphone.stream = SimpleNamespace(read=lambda n: (None, True))
    with pytest.raises(OSError, match="overflow"):
        microphone.read()


def test_helper_disabled_starts_without_opening_microphone(monkeypatch, capsys):
    import io
    import sys

    import dotenv

    import wake_word

    calls = []
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *args: None)
    monkeypatch.setattr(sys, "stdin", io.StringIO('{"enabled": false}\n'))
    monkeypatch.setattr(
        wake_word,
        "KeywordEngine",
        lambda path: SimpleNamespace(delete=lambda: calls.append("engine_closed")),
    )
    monkeypatch.setattr(
        wake_word,
        "Microphone",
        lambda: SimpleNamespace(delete=lambda: calls.append("mic_closed")),
    )
    assert wake_word.main() == 0
    assert calls == ["mic_closed", "engine_closed"]
    assert '"event": "ready"' in capsys.readouterr().out


def test_helper_setup_failure_is_redacted(monkeypatch, capsys):
    import dotenv

    import wake_word

    monkeypatch.setattr(dotenv, "load_dotenv", lambda *args: None)

    def fail(path):
        raise FileNotFoundError("private-location-or-secret")

    monkeypatch.setattr(wake_word, "KeywordEngine", fail)
    assert wake_word.main() == 2
    output = capsys.readouterr().out
    assert '"event": "error"' in output
    assert "private-location-or-secret" not in output


def test_model_check_never_constructs_microphone(monkeypatch, capsys):
    import dotenv

    import wake_word

    closed = []
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *args: None)
    monkeypatch.setattr(
        wake_word,
        "KeywordEngine",
        lambda path: SimpleNamespace(delete=lambda: closed.append(True)),
    )

    def forbidden():
        raise AssertionError("model check must not open a device")

    monkeypatch.setattr(wake_word, "Microphone", forbidden)
    assert wake_word.main(check=True) == 0
    assert closed == [True]
    assert '"mode": "model_check"' in capsys.readouterr().out
