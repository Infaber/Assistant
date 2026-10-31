import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from ai_modes import ModeBridge, initial_mode
from local_config import local_model, local_url


def bridge():
    room = SimpleNamespace(
        local_participant=SimpleNamespace(
            set_attributes=AsyncMock(),
            register_rpc_method=Mock(),
            unregister_rpc_method=Mock(),
        ),
        remote_participants={"guest-one": object()},
    )
    session = SimpleNamespace(
        userdata={
            "notes_pending": "old",
            "mac_snapshot": "old",
            "_camera_consent": "old",
            "_task_ledger": SimpleNamespace(receipts=[]),
        },
        interrupt=AsyncMock(),
    )
    make = Mock(
        side_effect=lambda target, ready: SimpleNamespace(mode=target, ready=ready)
    )

    def update(agent):
        session.pending_task = asyncio.create_task(agent.ready(agent.mode))

    session.update_agent = Mock(side_effect=update)
    return ModeBridge(room, session, make, prepare=AsyncMock())


@pytest.mark.parametrize(
    "metadata,expected",
    [
        ("", "normal"),
        ('{"mode":"local"}', "local"),
        ('{"mode":"other"}', "normal"),
        ("invalid", "normal"),
    ],
)
def test_startup_modes_are_bounded(monkeypatch, metadata, expected):
    monkeypatch.delenv("ARIANA_MODE", raising=False)
    assert initial_mode(metadata) == expected


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.example",
        "http://127.0.0.1.evil.example",
        "http://user:pass@localhost",
        "http://localhost/path",
        "http://localhost?url=evil",
    ],
)
def test_local_endpoint_never_accepts_remote_or_credential_urls(monkeypatch, url):
    monkeypatch.setenv("ARIANA_OLLAMA_URL", url)
    with pytest.raises(ValueError):
        local_url()


def test_cloud_model_tags_are_rejected(monkeypatch):
    monkeypatch.setenv("ARIANA_LOCAL_MODEL", "qwen-cloud")
    with pytest.raises(ValueError):
        local_model()


@pytest.mark.asyncio
async def test_confirmed_switch_clears_approvals_but_preserves_action_receipts():
    b = bridge()
    ledger = b.session.userdata["_task_ledger"]
    await b.entered("normal")
    result = await b.switch("local")
    assert result["mode"] == "local" and result["state"] == "ready"
    assert not result["context_transferred"]
    assert b.session.userdata["_task_ledger"] is ledger
    assert "notes_pending" not in b.session.userdata
    assert "mac_snapshot" not in b.session.userdata
    assert "_camera_consent" not in b.session.userdata
    assert not b.session.userdata["_mode_switching"]
    b.session.interrupt.assert_awaited_once()


@pytest.mark.asyncio
async def test_switch_is_not_ready_until_target_entered():
    b = bridge()
    entered = asyncio.Event()

    async def delayed(target):
        await entered.wait()
        await b.entered(target)

    b.make_agent.side_effect = lambda target, ready: SimpleNamespace(
        mode=target, ready=delayed
    )
    task = asyncio.create_task(b.switch("local"))
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert not task.done()
    assert b.mode == "normal" and b.state == "loading"
    entered.set()
    assert (await task)["mode"] == "local"


@pytest.mark.asyncio
async def test_running_action_blocks_switch_without_interrupting_or_replaying():
    b = bridge()
    b.session.userdata["_task_ledger"].receipts = [SimpleNamespace(status="running")]
    assert "error" in await b.switch("local")
    b.session.interrupt.assert_not_called()
    b.make_agent.assert_not_called()
    assert not b.session.userdata["_mode_switching"]


@pytest.mark.asyncio
async def test_local_failure_does_not_construct_gemini_or_clear_approval():
    b = bridge()
    b.prepare.side_effect = ValueError("unavailable")
    result = await b.switch("local")
    assert result["state"] == "error" and result["mode"] == "normal"
    assert "no automatic cloud fallback" in result["error"]
    b.make_agent.assert_not_called()
    assert b.session.userdata["notes_pending"] == "old"


@pytest.mark.asyncio
async def test_only_connected_guest_can_switch_or_read_mode():
    b = bridge()
    response = await b.rpc(
        SimpleNamespace(
            caller_identity="attacker", payload='{"action":"switch","mode":"local"}'
        )
    )
    assert "error" in json.loads(response)
    b.make_agent.assert_not_called()


@pytest.mark.asyncio
async def test_duplicate_requests_do_not_start_two_handoffs():
    b = bridge()
    wait = asyncio.Event()
    b.prepare.side_effect = lambda: wait.wait()

    # AsyncMock returns nested coroutine for a plain lambda; use an async hook.
    async def prepare():
        await wait.wait()

    b.prepare.side_effect = prepare
    task = asyncio.create_task(b.switch("local"))
    await asyncio.sleep(0)
    assert "already in progress" in (await b.switch("local"))["error"]
    wait.set()
    await task
    b.make_agent.assert_called_once()


@pytest.mark.asyncio
async def test_local_agent_does_not_ask_for_a_google_key(monkeypatch):
    import agent
    import local_models

    key = Mock(side_effect=AssertionError("Google must not be constructed"))
    monkeypatch.setattr(agent, "_google_api_key", key)
    monkeypatch.setattr(local_models, "local_options", lambda: {"llm": None})
    local = agent.Assistant(mode="local")
    assert local.ai_mode == "local"
    key.assert_not_called()


def test_local_tool_selection_changes_visibility_not_permissions():
    from local_routing import visible_tools
    from memory_tools import memory_manage
    from tools import notes_create

    assert visible_tools([memory_manage, notes_create], "none") == [memory_manage]
    assert visible_tools([memory_manage, notes_create], "notes") == [
        memory_manage,
        notes_create,
    ]


@pytest.mark.asyncio
async def test_room_connects_before_session_can_publish_mode_readiness(monkeypatch):
    import agent

    connected = False

    async def connect():
        nonlocal connected
        connected = True

    async def start(**kwargs):
        assert connected, "on_enter cannot publish attributes before room.connect"

    session = SimpleNamespace(userdata={}, start=AsyncMock(side_effect=start))
    ctx = SimpleNamespace(
        room=SimpleNamespace(name="fictional"),
        job=SimpleNamespace(metadata=""),
        connect=AsyncMock(side_effect=connect),
        simulation_context=lambda: object(),
        add_shutdown_callback=Mock(),
    )
    modes = SimpleNamespace(entered=AsyncMock(), start=Mock(), close=AsyncMock())
    monkeypatch.setattr(agent, "AgentSession", Mock(return_value=session))
    monkeypatch.setattr(agent, "ModeBridge", Mock(return_value=modes))
    monkeypatch.setattr(agent, "Assistant", Mock())
    monkeypatch.setattr(agent, "configure_simulation_tools", Mock())
    monkeypatch.setattr(agent, "install_recovery", Mock())
    monkeypatch.setattr(agent, "install_performance", Mock())
    monkeypatch.setattr(agent, "ActivityPublisher", Mock())
    monkeypatch.setattr(agent.ai_coustics, "audio_enhancement", lambda **kwargs: None)
    await agent.my_agent(ctx)
    ctx.connect.assert_awaited_once()
    session.start.assert_awaited_once()


@pytest.mark.asyncio
async def test_normal_engine_status_does_not_claim_local_inference():
    from local_tools import ai_engine_status

    ctx = SimpleNamespace(
        session=SimpleNamespace(
            userdata={"_ai_mode": "normal"},
            current_agent=SimpleNamespace(llm=SimpleNamespace(model="gemini-test")),
        )
    )
    result = await ai_engine_status._func(ctx)
    assert result == {"mode": "normal", "model": "gemini-test"}


def test_every_existing_safari_tool_is_available_to_local_routing():
    from livekit.agents.llm.tool_context import find_function_tools, get_function_info

    from browser_tools import BrowserToolset
    from local_routing import GROUPS

    names = {
        get_function_info(tool).name for tool in find_function_tools(BrowserToolset())
    }
    assert names <= GROUPS["safari"]
