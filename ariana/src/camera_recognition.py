"""Native recognition preparation only; no enrollment, images or biometric storage."""

import math
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
            or not isinstance(confidence, (int, float))
            or not math.isfinite(confidence)
            or not self.threshold <= confidence <= 1
        ):
            return {"identity": "unknown"}
        return {
            "identity": label[:80],
            "confidence": confidence,
            "source": "native Frigate; advisory, never authorization",
        }


class NativeRecognitionAdmin(Protocol):
    """Future local administrative adapter: every enrollment/removal needs consent.
    Intentionally not registered as an agent tool or implemented using write APIs.
    """

    async def enroll(self, identity: str, image: bytes, consent_receipt: str): ...
    async def remove(self, identity: str, consent_receipt: str): ...


async def recognition_capabilities(api):
    version = await api.get("/api/version", text=True)
    return {
        "version": version,
        "recognition_enabled_by_ariana": False,
        "installed_capability_verified": False,
        "next_step": "Check native Face Recognition settings and runtime hardware compatibility in Frigate. Ariana does not read biometric identities or enroll anyone. Current Frigate documentation requires AVX/AVX2 CPUs; do not assume Apple Silicon ARM64 support.",
        "verified": True,
    }
