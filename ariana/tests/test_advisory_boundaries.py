from dataclasses import fields

import pytest

from reasoning import ReasoningAdvice, ReasoningRequest
from vision_fallback import VisionHint, VisionRequest


def test_planner_and_vision_have_no_action_authority():
    for cls in (ReasoningAdvice, VisionHint):
        assert not {"confirmed", "execute", "x", "y", "credentials"} & {
            f.name for f in fields(cls)
        }
    with pytest.raises(ValueError, match="Secure"):
        VisionRequest("App", "snapshot", b"image", False)
    with pytest.raises(ValueError, match="too large"):
        ReasoningRequest("goal", tuple("fact" for _ in range(21)))
