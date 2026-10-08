"""Fresh read-only camera awareness; event history never proves occupancy."""

import math
import os
import time
from datetime import datetime

from camera_recognition import recognition_capabilities
from frigate_api import CameraError, FrigateAPI, enabled, identifier
from home_assistant import client_for
from home_assistant_api import HAError
from home_assistant_index import normalized


def timestamp(value):
    try:
        result = (
            float(value)
            if isinstance(value, (int, float))
            else datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        )
        return result if math.isfinite(result) else None
    except (ValueError, TypeError, AttributeError):
        return None


class CameraAwareness:
    def __init__(self, api=None):
        self._api = api

    @property
    def api(self):
        if self._api is None:
            self._api = FrigateAPI.configured()
        return self._api

    async def cameras(self):
        # Stats avoids exporting config, RTSP URLs or camera credentials.
        stats = await self.api.get("/api/stats")
        if not isinstance(stats, dict) or not isinstance(stats.get("cameras"), dict):
            raise CameraError("Frigate camera statistics are unavailable.")
        return {
            "cameras": [identifier(name) for name in list(stats["cameras"])[:100]],
            "verified": True,
        }

    async def health(self, camera):
        stats = await self.api.get("/api/stats")
        if not isinstance(stats, dict):
            raise CameraError("Frigate camera statistics are unavailable.")
        cameras = stats.get("cameras")
        service = stats.get("service")
        if not isinstance(cameras, dict) or not isinstance(service, dict):
            raise CameraError("Frigate camera statistics are invalid.")
        row = cameras.get(camera)
        if not isinstance(row, dict):
            raise CameraError("The requested camera is not available.")
        updated = timestamp(service.get("last_updated"))
        now = time.time()
        if updated is None or not 0 <= now - updated <= 90:
            raise CameraError("Camera statistics are stale; stream status is unknown.")
        fps = row.get("camera_fps")
        if not isinstance(fps, (int, float)) or not math.isfinite(fps) or fps < 0:
            raise CameraError("Camera stream status is unknown.")
        if fps > 0 and "capture_pid" in row and not row["capture_pid"]:
            raise CameraError(
                "The capture process is unavailable; current stream status is unknown."
            )
        return {
            "camera": camera,
            "online": fps > 0,
            "camera_fps": fps,
            "observed_at": updated,
            "verified": True,
        }

    async def current(self, context, camera, entity_id=""):
        # Resolve actual discovered HA metadata, never fabricate sensor IDs.
        ha = client_for(context)
        index = await ha.refresh()
        if entity_id:
            entity = index.entities.get(entity_id)
            if not entity or entity["domain"] not in {"sensor", "binary_sensor"}:
                raise CameraError(
                    "Choose a discovered camera count or occupancy entity."
                )
        else:
            result = await ha.find(camera + " person count", domain="sensor")
            if result.get("status") != "resolved":
                return {
                    **result,
                    "searched": camera + " person count",
                    "current_detection_available": False,
                    "guidance": "Choose the Frigate total person-count sensor (not active-only or a historical counter).",
                }
            entity = ha.index.entities[result["entity"]["entity_id"]]
        metadata = normalized(
            " ".join(
                str(entity.get(key, ""))
                for key in (
                    "name",
                    "entity_name",
                    "original_name",
                    "device",
                    "entity_id",
                )
            )
        )
        if (
            entity.get("platform") != "frigate"
            or not set(normalized(camera).split()).issubset(metadata.split())
            or "person" not in metadata.split()
            or "active" in metadata.split()
            or (entity["domain"] == "sensor" and entity.get("unit") != "objects")
        ):
            raise CameraError(
                "Select a discovered Frigate total person-count or person-occupancy sensor for this camera; active-only counts omit stationary people."
            )
        fresh_registry = await ha.api.registry_entity(entity["entity_id"])
        if (
            fresh_registry.get("platform") != "frigate"
            or fresh_registry.get("id") != entity["registry_id"]
            or fresh_registry.get("disabled_by")
            or fresh_registry.get("hidden_by")
        ):
            raise CameraError(
                "This camera sensor changed since discovery; refresh before trusting its count."
            )
        row = await ha.raw_state(entity)
        if (
            entity["domain"] == "sensor"
            and row["attributes"].get("unit_of_measurement") != "objects"
        ):
            raise CameraError("This sensor is no longer a native Frigate object count.")
        updated = timestamp(row.get("last_reported") or row.get("last_updated"))
        now = time.time()
        if updated is None or not 0 <= now - updated <= 90:
            raise CameraError(
                "Detection data is stale. Current occupancy is unknown; unchanged HA sensors may need fresh MQTT reporting."
            )
        raw = row.get("state")
        if (
            entity["domain"] == "binary_sensor"
            and entity["device_class"] in {"occupancy", "presence"}
            and raw in {"on", "off"}
        ):
            return {
                "camera": camera,
                "person_count": None,
                "occupied": raw == "on",
                "identity": "unknown",
                "source_entity": entity["entity_id"],
                "observed_at": updated,
                "verified": True,
            }
        try:
            count = float(raw)
        except (ValueError, TypeError):
            raise CameraError("Current person-count data is unavailable.") from None
        if not math.isfinite(count) or not count.is_integer() or not 0 <= count <= 100:
            raise CameraError("Current person-count data is invalid.")
        return {
            "camera": camera,
            "person_count": int(count),
            "identity": "unknown",
            "source_entity": entity["entity_id"],
            "observed_at": updated,
            "verified": True,
            "meaning": "Reported detections, not guaranteed physical occupancy or identity.",
        }

    async def objects(self, context, camera):
        ha = client_for(context)
        index = await ha.refresh()
        counts = []
        for entity in index.entities.values():
            words = normalized(
                " ".join(
                    str(entity.get(k, ""))
                    for k in (
                        "name",
                        "entity_name",
                        "original_name",
                        "device",
                        "entity_id",
                    )
                )
            ).split()
            if (
                entity.get("platform") != "frigate"
                or entity["domain"] != "sensor"
                or not set(normalized(camera).split()).issubset(words)
                or "count" not in words
                or "active" in words
                or entity.get("unit") != "objects"
            ):
                continue
            if len(counts) >= 12:
                break
            row = await ha.raw_state(entity)
            updated = timestamp(row.get("last_reported") or row.get("last_updated"))
            try:
                count = float(row.get("state"))
            except (TypeError, ValueError):
                continue
            if (
                updated is not None
                and 0 <= time.time() - updated <= 90
                and math.isfinite(count)
                and count.is_integer()
                and 0 <= count <= 100
            ):
                counts.append(
                    {
                        "name": entity["name"],
                        "entity_id": entity["entity_id"],
                        "count": int(count),
                        "observed_at": updated,
                    }
                )
        if not counts:
            raise CameraError(
                "No fresh discovered Frigate object-count sensors were found for this camera. Current objects are unknown."
            )
        return {
            "counts": counts,
            "complete_inventory": False,
            "identity": "unknown",
            "verified": True,
        }

    async def recent(self, camera, minutes=60, alerts=False):
        now = time.time()
        params = {"limit": 20, "after": now - minutes * 60}
        if alerts:
            params.update(cameras=camera, severity="alert")
        else:
            params.update(camera=camera, include_thumbnails=0)
        rows = await self.api.get("/api/review" if alerts else "/api/events", params)
        if not isinstance(rows, list):
            raise CameraError("Frigate event history is unavailable.")
        events = []
        for row in rows[:20]:
            if (
                not isinstance(row, dict)
                or row.get("camera") != camera
                or row.get("false_positive") is True
            ):
                continue
            start = timestamp(row.get("start_time"))
            if start is None or not now - minutes * 60 <= start <= now:
                continue
            events.append(
                {
                    "id": identifier(row.get("id")),
                    "camera": camera,
                    "label": "alert"
                    if alerts
                    else str(row.get("label", "unknown"))[:40],
                    "start_time": start,
                    "end_time": timestamp(row.get("end_time")),
                    "has_snapshot": row.get("has_snapshot") is True,
                    "identity": "unknown",
                }
            )
        return {
            "events": events,
            "historical": True,
            "complete_history": len(rows) < 20,
            "proves_current_occupancy": False,
            "verified": True,
        }


def camera_for(context):
    if not enabled() and not context.session.userdata.get("_camera_simulation"):
        raise CameraError(
            "Camera access is disabled. Enable ARIANA_CAMERA_ENABLED explicitly."
        )
    state = context.session.userdata
    if "_camera_client" not in state:
        state["_camera_client"] = CameraAwareness()
    return state["_camera_client"]


def camera_name(value):
    return identifier(value or os.getenv("FRIGATE_CAMERA", "bedroom"))


async def read_camera(context, action, camera="", entity_id="", minutes=60):
    try:
        client = camera_for(context)
        name = camera_name(camera)
        if action == "subscription":
            bridge = context.session.userdata.get("_camera_events")
            return {
                "subscription_state": bridge.status if bridge else "disabled",
                "announcements_enabled": bridge.enabled if bridge else False,
                "image_analysis_error": context.session.userdata.get(
                    "_camera_delivery_error"
                ),
                "verified": True,
            }
        if action == "capabilities":
            return await recognition_capabilities(client.api)
        if action == "objects":
            return await client.objects(context, name)
        if action == "cameras":
            return await client.cameras()
        if action == "health":
            return await client.health(name)
        if action == "current":
            return await client.current(context, name, entity_id)
        if action in {"events", "alerts"} and 1 <= minutes <= 1440:
            return await client.recent(name, minutes, action == "alerts")
        raise CameraError("Choose a supported read and a lookback of 1-1440 minutes.")
    except (CameraError, HAError) as error:
        return error.result()
