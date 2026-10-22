import pytest


@pytest.fixture(autouse=True)
def isolate_camera_speech_permission(monkeypatch, tmp_path):
    monkeypatch.setenv(
        "ARIANA_CAMERA_PERMISSION_PATH", str(tmp_path / "camera-permission.json")
    )
