"""Optional vision advice boundary. Never yields executable coordinates.

Not connected to screenshot capture or input. A future integration must redact
secure content before capture and resolve hints against a fresh Accessibility
snapshot. If no accessible target is found, ask the user; do not guess a click.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class VisionRequest:
    app: str
    snapshot_id: str
    screenshot: bytes
    secure_content_absent: bool

    def __post_init__(self):
        if not self.secure_content_absent:
            raise ValueError("Secure content must be excluded before vision analysis.")
        if not self.app or not self.snapshot_id or len(self.screenshot) > 5_000_000:
            raise ValueError(
                "Vision advice needs a bounded image and fresh app snapshot."
            )


@dataclass(frozen=True)
class VisionHint:
    accessible_label: str
    explanation: str
    # No x/y, click callable, confirmed flag, credential or tool authorization.


class VisionAdvisor(Protocol):
    async def describe(self, request: VisionRequest) -> tuple[VisionHint, ...]: ...
