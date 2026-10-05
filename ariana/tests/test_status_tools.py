import json

import pytest

import status_tools


@pytest.mark.asyncio
async def test_configuration_diagnostics_never_return_secrets(monkeypatch):
    monkeypatch.setattr(status_tools.sys, "platform", "linux")
    for name in (
        "LIVEKIT_URL",
        "LIVEKIT_API_KEY",
        "LIVEKIT_API_SECRET",
        "GOOGLE_API_KEY",
        "HOME_ASSISTANT_URL",
        "HOME_ASSISTANT_TOKEN",
    ):
        monkeypatch.setenv(name, "private-value-never-returned")
    report = await status_tools.assistant_status._func()
    assert report["home_assistant_configured"] and report["google_configured"]
    assert "private-value-never-returned" not in json.dumps(report)
    assert not report["local_mac"]
