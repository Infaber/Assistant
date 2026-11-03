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
        assert callback(np.zeros(2400), 0.5) == 1
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


@pytest.mark.asyncio
async def test_local_speech_delivers_first_chunk_before_synthesis_finishes(monkeypatch):
    import asyncio
    import threading
    from types import SimpleNamespace

    import numpy as np

    from local_speech import LocalTTS

    released = threading.Event()

    def generate(text, *, sid, speed, callback):
        assert callback(np.zeros(2400), 0.5) == 1
        assert released.wait(3), "First audio was held until synthesis completed"
        assert callback(np.zeros(2400), 1.0) == 1

    monkeypatch.setattr(
        "local_speech.engines",
        lambda: (
            None,
            SimpleNamespace(generate=generate),
            threading.Lock(),
            threading.Lock(),
        ),
    )
    async with LocalTTS().synthesize("Two sentences.") as stream:
        try:
            await asyncio.wait_for(anext(stream), 2)
        finally:
            released.set()
        async for _ in stream:
            pass


@pytest.mark.asyncio
async def test_router_missing_model_falls_back_locally_and_keeps_context(monkeypatch):
    import json

    from local_routing import choose_group

    requests = []

    def handle(request):
        requests.append(request)
        if request.url.path == "/api/show":
            return httpx.Response(404)
        body = json.loads(request.content)
        assert body["model"] == local_models.local_model()
        assert body["options"]["num_ctx"] == 16384
        return httpx.Response(200, json={"message": {"content": '{"apps":[]}'}})

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: original(transport=httpx.MockTransport(handle), **kw),
    )
    assert await choose_group([{"role": "user", "text": "Hello"}]) == ()
    assert all(request.url.host == "127.0.0.1" for request in requests)


@pytest.mark.asyncio
async def test_router_rejects_cloud_backed_model_before_inference(monkeypatch):
    from local_routing import choose_group

    paths = []

    def handle(request):
        paths.append(request.url.path)
        return httpx.Response(200, json={"remote_host": "https://example.invalid"})

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: original(transport=httpx.MockTransport(handle), **kw),
    )
    with pytest.raises(ValueError, match="Cloud-backed"):
        await choose_group([{"role": "user", "text": "Hello"}])
    assert paths == ["/api/show"]


def test_local_prompt_is_smaller_but_keeps_personality_and_guard_protocols(monkeypatch):
    from instructions import configured_instructions
    from personality import CONVERSATION

    monkeypatch.setenv(
        "ARIANA_PREFERENCES_PATH", "/tmp/ariana-empty-speed-test-prefs.json"
    )
    local = configured_instructions("local")
    assert CONVERSATION in local
    assert len(local) < len(configured_instructions()) * 0.55
    for rule in (
        "LATER real user",
        "confirmed=true",
        "revision",
        "never blindly repeat",
        "untrusted data",
        "No silent cloud fallback",
        "current_presence_verified",
    ):
        assert rule in local


@pytest.mark.asyncio
async def test_prompt_warmup_waits_for_content_and_never_executes_tools(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from livekit.agents import llm

    from local_models import prewarm_local

    router = AsyncMock(return_value=())
    monkeypatch.setattr("local_routing.choose_group", router)
    observed = []

    class Stream:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def __aiter__(self):
            for delta in (
                SimpleNamespace(content=None, tool_calls=[]),
                SimpleNamespace(content="Hi", tool_calls=[]),
            ):
                observed.append(delta.content)
                yield SimpleNamespace(delta=delta)

    class VoiceStream(Stream):
        async def __aiter__(self):
            yield object()

    class FakeTTS:
        def synthesize(self, text):
            assert text == "Ready."
            return VoiceStream()

    monkeypatch.setattr("local_speech.LocalTTS", FakeTTS)
    calls = []

    def chat(**kwargs):
        calls.append(kwargs)
        return Stream()

    agent = SimpleNamespace(
        tools=[], llm=SimpleNamespace(chat=chat), chat_ctx=llm.ChatContext()
    )
    await prewarm_local(agent)
    router.assert_awaited_once_with([{"role": "user", "text": "Hello"}])
    assert observed == [None, "Hi"]
    assert calls[0]["tools"] == []
    assert not agent.chat_ctx.items  # Warmup doesn't become user conversation history.


@pytest.mark.asyncio
async def test_local_readiness_waits_for_warmup(monkeypatch):
    from unittest.mock import AsyncMock

    import agent

    monkeypatch.setattr("local_models.local_options", lambda: {})
    warm = AsyncMock()
    monkeypatch.setattr("local_models.prewarm_local", warm)
    ready = AsyncMock()
    assistant = agent.Assistant(mode="local", on_ready=ready)
    await assistant.on_enter()
    warm.assert_awaited_once_with(assistant)
    ready.assert_awaited_once_with("local")
    warm.side_effect = RuntimeError("Unavailable")
    ready.reset_mock()
    with pytest.raises(RuntimeError):
        await assistant.on_enter()
    ready.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_router_warmup_cancels_other_engines(monkeypatch):
    import asyncio
    from types import SimpleNamespace

    from livekit.agents import llm

    from local_models import prewarm_local

    stopped = []

    class Stream:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def __aiter__(self):
            try:
                await asyncio.Event().wait()
                yield object()
            finally:
                stopped.append(True)

    async def fail(messages):
        await asyncio.sleep(0)
        raise RuntimeError("Router unavailable")

    monkeypatch.setattr("local_routing.choose_group", fail)
    monkeypatch.setattr(
        "local_speech.LocalTTS",
        lambda: SimpleNamespace(synthesize=lambda text: Stream()),
    )
    agent = SimpleNamespace(
        tools=[],
        llm=SimpleNamespace(chat=lambda **kw: Stream()),
        chat_ctx=llm.ChatContext(),
    )
    with pytest.raises(RuntimeError, match="Router unavailable"):
        await prewarm_local(agent)
    assert len(stopped) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("speed", ["0.8", "1.0", "1.2"])
async def test_local_rate_reaches_synthesis_and_is_bounded(monkeypatch, speed):
    import threading
    from types import SimpleNamespace

    import numpy as np

    from local_speech import LocalTTS

    seen = []

    def generate(text, **kwargs):
        seen.append(kwargs["speed"])
        kwargs["callback"](np.zeros(2400), 1.0)

    monkeypatch.setattr(
        "local_speech.engines",
        lambda: (
            None,
            SimpleNamespace(generate=generate),
            threading.Lock(),
            threading.Lock(),
        ),
    )
    async with LocalTTS(speed=speed).synthesize("Hello") as stream:
        async for _ in stream:
            pass
    assert seen == [float(speed)]
    for invalid in ["nan", "inf", "0", "9", True]:
        with pytest.raises(ValueError):
            LocalTTS(speed=invalid)


@pytest.mark.asyncio
async def test_canceled_local_synthesis_drops_late_output_and_yields_to_new_turn(
    monkeypatch,
):
    import asyncio
    import threading
    from types import SimpleNamespace

    import numpy as np

    from local_speech import LocalTTS

    released = threading.Event()
    stopped = threading.Event()
    callbacks = []

    def generate(text, *, sid, speed, callback):
        if text == "old":
            callback(np.zeros(2400), 0.5)
            assert released.wait(3)
            callbacks.append(callback(np.zeros(2400), 1.0))
            stopped.set()
        else:
            callbacks.append(callback(np.zeros(2400), 1.0))

    monkeypatch.setattr("local_speech.engines", lambda: engines)
    engines = (
        None,
        SimpleNamespace(generate=generate),
        threading.Lock(),
        threading.Lock(),
    )
    stream = LocalTTS().synthesize("old")
    await asyncio.wait_for(anext(stream), 2)
    await stream.aclose()
    released.set()
    assert await asyncio.to_thread(stopped.wait, 3)
    async with LocalTTS().synthesize("new") as newest:
        frames = [event async for event in newest]
    assert callbacks == [0, 1]
    assert frames
