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
    engine = SimpleNamespace(process=lambda frame: 0, delete=lambda: None)
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
    detector = WakeDetector(None, recorder, lambda event: None)
    with pytest.raises(PermissionError):
        detector.enable(True)
    assert not detector.enabled


def test_capture_state_reports_only_successful_changes():
    recorder, states = Recorder(), []
    engine = SimpleNamespace(process=lambda frame: -1, delete=lambda: None)
    detector = WakeDetector(
        engine, recorder, lambda event: None, state_changed=states.append
    )
    detector.enable(True)
    detector.enable(True)
    detector.enable(False)
    assert states == [True, False]
