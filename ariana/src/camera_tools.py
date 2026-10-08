"""Existing voice tools with explicit cloud-image and announcement consent."""

import asyncio
import base64
import io
import warnings
from typing import Literal

from livekit.agents import RunContext, function_tool
from livekit.agents.llm import ImageContent
from PIL import Image, ImageOps

from action_events import observed
from camera_awareness import camera_for, camera_name, read_camera
from camera_delivery import schedule_delivery
from camera_privacy import approval
from frigate_api import CameraError, identifier
from frigate_api import enabled as camera_access_enabled


@function_tool
@observed("Camera awareness")
async def camera_status(
    context: RunContext,
    action: Literal[
        "cameras",
        "health",
        "current",
        "objects",
        "events",
        "alerts",
        "capabilities",
        "subscription",
    ],
    camera: str = "",
    entity_id: str = "",
    minutes: int = 60,
) -> dict:
    """Read Frigate cameras/stream health, fresh HA person counts, historical events or alerts.
    Default camera is the configured bedroom. Current counts require discovered Frigate
    total person-count entities. If ambiguous ask which. Never infer identity or current
    presence from old events. No image retrieval. entity_id selects a discovered sensor.
    """
    return await read_camera(context, action, camera, entity_id, minutes)


def normalized_snapshot(data):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as source:
                if source.width * source.height > 20_000_000 or source.format not in {
                    "JPEG",
                    "PNG",
                    "WEBP",
                }:
                    raise ValueError
                image = ImageOps.exif_transpose(source).convert("RGB")
                image.thumbnail((1280, 1280))
                result = io.BytesIO()
                image.save(result, "JPEG", quality=75)
                if result.tell() > 1_000_000:
                    raise ValueError
                return ImageContent(
                    image="data:image/jpeg;base64,"
                    + base64.b64encode(result.getvalue()).decode()
                )
    except (
        OSError,
        ValueError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        raise CameraError("The camera image could not be decoded safely.") from None


@function_tool
@observed("Camera snapshot permission")
async def camera_snapshot(
    context: RunContext,
    question: str,
    camera: str = "",
    event_id: str = "",
    confirmed: bool = False,
) -> dict:
    """Ask separate explicit permission to send ONE sensitive image to Google Gemini.
    First call previews cloud disclosure; after a NEW affirmative user reply repeat
    identical arguments with confirmed=true. Current frames require healthy fresh stats.
    event_id retrieves a historical event snapshot, never a current view. Do not claim
    visible content until the supplied image was analyzed. No disk or memory storage.
    """
    try:
        client = camera_for(context)
        name = camera_name(camera)
        if not 1 <= len(question.strip()) <= 1000:
            raise CameraError("Provide a short question about the camera image.")
        if event_id:
            identifier(event_id)
        payload = {"camera": name, "question": question, "event_id": event_id}
        if preview := approval(context, "snapshot", payload, confirmed):
            return preview
        lock = context.session.userdata.setdefault("_camera_image_lock", asyncio.Lock())
        if lock.locked():
            raise CameraError("A camera image is already being processed.")
        async with lock:
            if event_id:
                event = await client.api.get("/api/events/" + event_id)
                if not isinstance(event, dict) or event.get("camera") != name:
                    raise CameraError(
                        "This event does not belong to the approved camera."
                    )
                path = "/api/events/" + event_id + "/snapshot.jpg"
            else:
                health = await client.health(name)
                if not health["online"]:
                    raise CameraError("Camera is offline; no current image was sent.")
                path = "/api/" + name + "/latest.jpg"
            data = await client.api.get(
                path, {"height": 720, "quality": 75}, image=True
            )
            image = await asyncio.to_thread(normalized_snapshot, data)
            del data
            schedule_delivery(context, image, name, question, bool(event_id))
            return {
                "image_prepared": True,
                "image_supplied": False,
                "historical": bool(event_id),
                "analyzed": False,
                "instruction": "Say only a brief One moment. The approved image will be delivered after this blocking tool turn finishes, followed by its description. Do not claim to see it yet. No continuous video stream is opened.",
            }
    except CameraError as error:
        return error.result()
    except Exception:
        return {
            "error": "The camera image could not be supplied to Gemini. Do not claim to have seen it; permission must be requested again before retrying.",
            "verified": False,
        }


@function_tool
@observed("Camera announcements permission")
async def camera_announcements(
    context: RunContext, enabled: bool = False, confirmed: bool = False
) -> dict:
    """Enable neutral event announcements only after a preview and NEW explicit approval.
    Requires an operator-configured HA event source. Off is immediate. Session-scoped;
    never changes recording, recognition, lights or any other device. No identity claims.
    """
    bridge = context.session.userdata.get("_camera_events")
    if not enabled:
        if bridge:
            bridge.enabled = False
            if (
                getattr(bridge, "speaking", False)
                and bridge.companion.speech is not None
            ):
                bridge.companion.speech.interrupt()
        context.session.userdata.pop("_camera_consent", None)
        return {"enabled": False, "verified": True}
    if not camera_access_enabled() and not context.session.userdata.get(
        "_camera_simulation"
    ):
        return {
            "error": "Camera access is disabled. No camera announcements were enabled."
        }
    if not bridge:
        return {
            "error": "Camera announcements need ARIANA_CAMERA_EVENTS_ENABLED and an explicitly configured Frigate HA entity; see camera setup documentation."
        }
    if getattr(bridge, "status", "connected") != "connected":
        return {
            "error": "Camera event subscription is not connected. Check subscription status before enabling speech."
        }
    if preview := approval(context, "announcements", {"enabled": True}, confirmed):
        return preview
    bridge.enabled = True
    return {
        "enabled": True,
        "verified": True,
        "scope": "This connected voice session only.",
    }
