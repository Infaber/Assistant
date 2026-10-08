"""Fictional camera fixtures; never connect to real Frigate or retrieve footage."""

import io
import time
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from PIL import Image

from camera_awareness import CameraAwareness
from home_assistant_simulation import fixture_client


def fixture_camera(session):
    ha, api = fixture_client()
    entity_id = "sensor.bedroom_person_count"
    api.rows[entity_id] = {
        "entity_id": entity_id,
        "state": "2",
        "last_reported": datetime.now(timezone.utc).isoformat(),
        "attributes": {
            "friendly_name": "Bedroom Person Count",
            "unit_of_measurement": "objects",
        },
    }
    api.registry["entity"].append(
        {
            "entity_id": entity_id,
            "id": "fixture-camera-count",
            "platform": "frigate",
            "original_name": "Bedroom Person Count",
        }
    )
    calls = []

    async def get(path, params=None, image=False, text=False):
        calls.append(path)
        if path == "/api/stats":
            return {
                "cameras": {"bedroom": {"camera_fps": 5}},
                "service": {"last_updated": time.time()},
            }
        if path == "/api/bedroom/latest.jpg":
            output = io.BytesIO()
            Image.new("RGB", (640, 480), "blue").save(output, "JPEG")
            return output.getvalue()
        if path in {"/api/events", "/api/review"}:
            return []
        if path == "/api/version":
            return "0.17.0"
        raise ValueError("Unsupported fixture route")

    camera = CameraAwareness(SimpleNamespace(get=AsyncMock(side_effect=get)))
    session.userdata.update(
        _ha_client=ha,
        _camera_client=camera,
        _camera_simulation=True,
        _camera_fixture_calls=calls,
    )
