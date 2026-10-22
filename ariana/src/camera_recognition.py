"""Opt-in recognition metadata only; never enrollment or biometric storage."""

import math
import os
import time
from dataclasses import dataclass
from typing import Protocol

from frigate_api import CameraError
from home_assistant_api import HAError


@dataclass(frozen=True)
class RecognitionPolicy:
    enabled: bool = False
    threshold: float = 0.95

    def identity(self, label, confidence):
        if (
            not self.enabled
            or not isinstance(label, str)
            or not label.strip()
            or label.strip().casefold() == "unknown"
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


async def recognition_report(client, camera, context=None):
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
    current = await current_identity(client, camera, context)
    return {
        "enabled": True,
        "camera": camera,
        "recent_matches": matches,
        "historical": not current.get("current_presence_verified", False),
        "identity_now": "unknown",
        **current,
        "recent_matches_are_historical": True,
        "lookback_seconds": 600,
        "complete_history": len(rows) < 20,
        "verified": True,
        "meaning": "Use current_recognized_people only for who appears to be in the room now: these labels belong to ongoing person tracks cross-checked against fresh total counts or live Frigate activity and healthy stream data. recent_matches are historical events and never current-presence evidence. Recognition is probabilistic, never proof of the speaker's identity or permission for actions. Event start is not recognition time. Labels may also be set by an administrator or classifier. No face image was retrieved.",
    }


async def current_identity(client, camera, context):
    result = {
        "current_recognized_people": [],
        "current_identity_status": "unavailable",
        "identity_now": "unknown",
        "current_presence_verified": False,
    }
    if context is None:
        return result
    try:
        count = await client.current(context, camera)
        number = count.get("person_count")
        if type(number) is not int or number < 0:
            return result
        health = await client.health(camera)
        if not health.get("online"):
            return result
        rows = await client.api.get(
            "/api/events",
            {
                "camera": camera,
                "label": "person",
                "in_progress": 1,
                "include_thumbnails": 0,
                "limit": 20,
            },
        )
        if not isinstance(rows, list):
            raise CameraError("Current tracked identities are unavailable.")
        now = time.time()
        tracks = {}
        for row in rows:
            if (
                not isinstance(row, dict)
                or row.get("camera") != camera
                or row.get("label") != "person"
                or row.get("end_time") is not None
                or row.get("false_positive") is True
            ):
                continue
            event_id = row.get("id")
            started = row.get("start_time")
            if (
                not isinstance(event_id, str)
                or not event_id
                or type(started) not in {float, int}
                or not math.isfinite(started)
                or started > now
            ):
                continue
            if event_id in tracks:
                raise CameraError("Current person tracks are inconsistent.")
            tracks[event_id] = row
        # An incomplete/truncated or conflicting track list cannot identify the
        # person counted by HA. Never fill missing identities from ended history.
        live_ids = count.get("person_track_ids")
        if (
            len(rows) >= 20
            or len(tracks) != number
            or (live_ids is not None and set(live_ids) != set(tracks))
        ):
            result["current_identity_reason"] = (
                "Fresh total count and ongoing tracks disagree; wait for the next detection update."
            )
            return result
        people = []
        for row in tracks.values():
            data = row.get("data") or {}
            match = RecognitionPolicy(enabled=True).identity(
                row.get("sub_label"),
                data.get("sub_label_score") if isinstance(data, dict) else None,
            )
            if match["identity"] != "unknown":
                people.append(
                    {
                        "reported_name": match["identity"],
                        "confidence": match["confidence"],
                    }
                )
        return {
            "current_identity_reason": ""
            if len(people) == number
            else "Some current person tracks have no reliable recognized name yet; a clear face view may be needed.",
            "current_recognized_people": people,
            "person_count": number,
            "unknown_person_count": number - len(people),
            "current_identity_status": "empty"
            if number == 0
            else "known"
            if len(people) == number
            else "partial"
            if people
            else "unknown",
            "current_presence_verified": True,
            "identity_now": people[0]["reported_name"]
            if number == 1 and len(people) == 1
            else "unknown",
            "current_observed_at": min(count["observed_at"], health["observed_at"]),
        }
    except (CameraError, HAError):
        result["current_identity_reason"] = (
            "Current person tracking could not be verified; recent matches remain historical."
        )
        return result


async def recognition_capabilities(api):
    version = await api.get("/api/version", text=True)
    return {
        "version": version,
        "recognition_enabled_by_ariana": recognition_enabled(),
        "installed_capability_verified": False,
        "next_step": "Set up native recognition in Frigate and opt in to ARIANA_CAMERA_RECOGNITION_ENABLED for current tracked identities and recent scored event labels. Ariana never enrolls faces or fetches biometric templates. Runtime compatibility must be verified on the installed hardware.",
        "verified": True,
    }
