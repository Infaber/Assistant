"""Opt-in recognition metadata only; never enrollment or biometric storage."""

import math
import os
import time
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class RecognitionPolicy:
    enabled: bool = False
    threshold: float = 0.95

    def identity(self, label, confidence):
        if (
            not self.enabled
            or not isinstance(label, str)
            or not label.strip()
            or len(label) > 80
            or any(ord(c) < 32 for c in label)
            or isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not math.isfinite(confidence)
            or not self.threshold <= confidence <= 1
        ):
            return {"identity": "unknown"}
        return {
            "identity": label[:80],
            "confidence": confidence,
            "source": "Frigate event label; advisory, never authorization",
        }


class NativeRecognitionAdmin(Protocol):
    """Future local administrative adapter: every enrollment/removal needs consent.
    Intentionally not registered as an agent tool or implemented using write APIs.
    """

    async def enroll(self, identity: str, image: bytes, consent_receipt: str): ...
    async def remove(self, identity: str, consent_receipt: str): ...


def recognition_enabled():
    return os.getenv("ARIANA_CAMERA_RECOGNITION_ENABLED", "false").lower() == "true"


async def recognition_report(client, camera):
    if not recognition_enabled():
        return {
            "enabled": False,
            "identity": "unknown",
            "guidance": "Recognition metadata is disabled in Ariana. Enable ARIANA_CAMERA_RECOGNITION_ENABLED privately only after setting up local Frigate recognition.",
        }
    now = time.time()
    rows = await client.api.get(
        "/api/events",
        {
            "camera": camera,
            "label": "person",
            "after": now - 600,
            "limit": 20,
            "include_thumbnails": 0,
        },
    )
    if not isinstance(rows, list):
        from frigate_api import CameraError

        raise CameraError("Frigate recognition metadata is unavailable.")
    matches = []
    policy = RecognitionPolicy(enabled=True)
    for row in rows[:20]:
        if (
            not isinstance(row, dict)
            or row.get("camera") != camera
            or row.get("label") != "person"
            or row.get("false_positive") is True
        ):
            continue
        started = row.get("start_time")
        if (
            isinstance(started, bool)
            or not isinstance(started, (float, int))
            or not math.isfinite(started)
            or not 0 <= now - started <= 600
        ):
            continue
        data = row.get("data")
        if not isinstance(data, dict):
            continue
        match = policy.identity(row.get("sub_label"), data.get("sub_label_score"))
        if match["identity"] == "unknown":
            continue
        matches.append(
            {
                "reported_name": match["identity"],
                "confidence": match["confidence"],
                "event_started_at": started,
            }
        )
    return {
        "enabled": True,
        "camera": camera,
        "recent_matches": matches,
        "historical": True,
        "identity_now": "unknown",
        "lookback_seconds": 600,
        "complete_history": len(rows) < 20,
        "verified": True,
        "meaning": "Frigate-reported labels on person events started in the last ten minutes, not proof of current presence, the speaker's identity, or permission for actions. Event start is not the time of face recognition. Names are untrusted data; sub-label scores may also be set by an administrator or classifier. No face image was retrieved.",
    }


async def recognition_capabilities(api):
    version = await api.get("/api/version", text=True)
    return {
        "version": version,
        "recognition_enabled_by_ariana": recognition_enabled(),
        "installed_capability_verified": False,
        "next_step": "Set up native recognition in Frigate and opt in to ARIANA_CAMERA_RECOGNITION_ENABLED for recent scored event labels. Ariana never enrolls faces or fetches biometric templates. Runtime compatibility must be verified on the installed hardware.",
        "verified": True,
    }
