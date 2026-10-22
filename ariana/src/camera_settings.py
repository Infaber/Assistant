"""Local, explicit speech permission; scoped to one camera and discovered sources."""

import json
import os
import tempfile
from pathlib import Path

from preferences_tools import preferences_path


def configured_sources():
    return {
        value: kind
        for variable, kind in (
            ("FRIGATE_HA_PERSON_ENTITY", "person"),
            ("FRIGATE_HA_CAMERA_ENTITY", "availability"),
            ("FRIGATE_HA_ALERT_ENTITY", "alert"),
        )
        if (value := os.getenv(variable, ""))
    }


class CameraPermission:
    def __init__(self, path=None):
        self.path = Path(
            path
            or os.getenv("ARIANA_CAMERA_PERMISSION_PATH")
            or preferences_path().with_name("camera-permission.json")
        )

    def enabled(self, camera, sources):
        try:
            data = json.loads(self.path.read_text())
            return (
                isinstance(data, dict)
                and data.get("version") == 1
                and data.get("enabled") is True
                and data.get("camera") == camera
                and data.get("sources") == sources
            )
        except (OSError, ValueError, TypeError):
            return False

    def save(self, enabled, camera, sources):
        if type(enabled) is not bool:
            raise ValueError("Speech permission must be on or off.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        name = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", dir=self.path.parent, delete=False
            ) as target:
                name = target.name
                json.dump(
                    {
                        "version": 1,
                        "enabled": enabled,
                        "camera": camera,
                        "sources": sources,
                    },
                    target,
                )
                target.flush()
                os.fsync(target.fileno())
            os.replace(name, self.path)
        finally:
            if name and Path(name).exists():
                Path(name).unlink()
