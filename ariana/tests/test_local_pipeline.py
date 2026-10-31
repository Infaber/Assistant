from unittest.mock import Mock

import httpx
import pytest

import local_models


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["missing", "cloud", "no_tools", "redirect"])
async def test_preflight_rejects_unavailable_remote_or_unsupported_models(
    monkeypatch, fault
):
    monkeypatch.setattr(local_models, "voice_files", lambda: None)
    monkeypatch.setattr("local_speech.engines", lambda: None)
    original = httpx.AsyncClient
    calls = []

    def handle(request):
        calls.append(str(request.url))
        if fault == "missing":
            return httpx.Response(404)
        if fault == "cloud":
            return httpx.Response(
                200,
                json={"capabilities": ["tools"], "remote_host": "https://ollama.com"},
            )
        if fault == "no_tools":
            return httpx.Response(200, json={"capabilities": ["completion"]})
        return httpx.Response(307, headers={"Location": "https://attacker.invalid"})

    monkeypatch.setattr(
        local_models.httpx,
        "AsyncClient",
        lambda **kw: original(transport=httpx.MockTransport(handle), **kw),
    )
    with pytest.raises(ValueError):
        await local_models.prepare_local()
    assert all(url.startswith("http://127.0.0.1:11434/") for url in calls)


@pytest.mark.asyncio
async def test_preflight_warms_only_the_local_model(monkeypatch):
    monkeypatch.setattr(local_models, "voice_files", lambda: None)
    engines = Mock()
    monkeypatch.setattr("local_speech.engines", engines)
    original = httpx.AsyncClient
    calls = []

    def handle(request):
        calls.append(str(request.url))
        return httpx.Response(
            200, json={"capabilities": ["tools"], "parameters": "num_ctx 16384"}
        )

    monkeypatch.setattr(
        local_models.httpx,
        "AsyncClient",
        lambda **kw: original(transport=httpx.MockTransport(handle), **kw),
    )
    await local_models.prepare_local()
    assert calls == [
        "http://127.0.0.1:11434/api/show",
        "http://127.0.0.1:11434/api/chat",
    ]
    engines.assert_called_once()


@pytest.mark.asyncio
async def test_local_camera_request_cannot_capture_or_upload_an_image():
    from types import SimpleNamespace

    from action_events import observed

    calls = []

    @observed("Camera")
    async def camera_snapshot(context):
        calls.append("captured")
        return {"success": True}

    context = SimpleNamespace(session=SimpleNamespace(userdata={"_ai_mode": "local"}))
    result = await camera_snapshot(context)
    assert "no vision support" in result["error"]
    assert not calls


@pytest.mark.asyncio
async def test_mode_switch_gate_prevents_new_actions():
    from types import SimpleNamespace

    from action_events import observed

    calls = []

    @observed("Effect")
    async def effect(context):
        calls.append("executed")
        return {"success": True}

    context = SimpleNamespace(
        session=SimpleNamespace(userdata={"_mode_switching": True})
    )
    assert "No new action" in (await effect(context))["error"]
    assert not calls


@pytest.mark.asyncio
async def test_local_speech_callback_continues_until_cancelled(monkeypatch):
    import threading
    from types import SimpleNamespace

    import numpy as np

    from local_speech import LocalTTS

    def generate(text, *, sid, speed, callback):
        # sherpa's actual callback uses 1=continue; 0 truncated earlier speech.
        assert callback(np.zeros(10), 0.5) == 1
        assert sid == 3
        return SimpleNamespace(
            samples=np.zeros(2400, dtype=np.float32), sample_rate=24000
        )

    monkeypatch.setattr(
        "local_speech.engines",
        lambda: (
            None,
            SimpleNamespace(generate=generate),
            threading.Lock(),
            threading.Lock(),
        ),
    )
    frames = []
    async with LocalTTS().synthesize("First sentence. Second sentence.") as stream:
        async for event in stream:
            frames.append(event.frame)
    assert sum(frame.samples_per_channel for frame in frames) >= 2400
