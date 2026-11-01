import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from preferences_tools import PreferencesStore
from voice_controls import VoiceControls


def controls(tmp_path):
    session = SimpleNamespace(
        userdata={},
        agent_state="listening",
        user_state="listening",
        current_agent=SimpleNamespace(voice_name="Sulafat"),
        generate_reply=Mock(),
        interrupt=AsyncMock(),
    )
    room = SimpleNamespace(
        remote_participants={"guest-one": object()},
        local_participant=SimpleNamespace(
            register_rpc_method=Mock(), unregister_rpc_method=Mock()
        ),
    )
    return VoiceControls(
        room,
        session,
        PreferencesStore(tmp_path / "preferences.json"),
        clock=lambda: 100,
    )


async def invoke(b, action, identity="guest-one", **values):
    return json.loads(
        await b.rpc(
            SimpleNamespace(
                caller_identity=identity,
                payload=json.dumps({"action": action, **values}),
            )
        )
    )


@pytest.mark.asyncio
async def test_settings_open_is_read_only_and_never_starts_audio(tmp_path):
    b = controls(tmp_path)
    status = await invoke(b, "status")
    assert status["active_voice"] == "Sulafat"
    assert not status["backchannel_audio_supported"]
    b.session.generate_reply.assert_not_called()
    b.session.interrupt.assert_not_called()


@pytest.mark.asyncio
async def test_saved_voice_and_style_are_atomic_and_do_not_interrupt(
    tmp_path, monkeypatch
):
    b = controls(tmp_path)
    result = await invoke(b, "save", values={"google_voice": "Aoede", "sarcasm": "off"})
    assert result["applies"] == "next_connection"
    assert b.store.read() == {"google_voice": "Aoede", "sarcasm": "off"}
    assert "error" in await invoke(
        b, "save", values={"google_voice": "Kore", "sarcasm": "invented"}
    )
    assert b.store.read()["google_voice"] == "Aoede"
    assert "error" in await invoke(b, "save", values={"home_city": "Oslo"})
    b.session.interrupt.assert_not_called()
    b.session.generate_reply.assert_not_called()


@pytest.mark.asyncio
async def test_sample_requires_idle_and_cooldown_and_never_provides_tools(tmp_path):
    b = controls(tmp_path)
    b.session.agent_state = "speaking"
    assert "error" in await invoke(b, "sample")
    b.session.agent_state = "listening"
    b.session.user_state = "speaking"
    assert "error" in await invoke(b, "sample")
    b.session.user_state = "listening"
    assert (await invoke(b, "sample"))["started"]
    assert "error" in await invoke(b, "sample")
    kwargs = b.session.generate_reply.call_args.kwargs
    assert (
        kwargs["tools"] == []
        and kwargs["tool_choice"] == "none"
        and kwargs["allow_interruptions"]
    )
    assert b.session.generate_reply.call_count == 1


@pytest.mark.asyncio
async def test_untrusted_participant_cannot_generate_save_or_stop(tmp_path):
    b = controls(tmp_path)
    for action in ["status", "save", "sample", "standby"]:
        assert "error" in await invoke(b, action, identity="other")
    assert not b.store.path.exists()
    b.session.generate_reply.assert_not_called()
    b.session.interrupt.assert_not_called()


@pytest.mark.asyncio
async def test_standby_cancels_output_clears_staged_approval_and_preserves_receipts(
    tmp_path,
):
    b = controls(tmp_path)
    receipt = object()
    b.session.userdata.update(
        notes_pending="old", _camera_consent="old", _task_ledger=receipt
    )
    assert (await invoke(b, "standby"))["standby"]
    b.session.interrupt.assert_awaited_once()
    assert (
        "notes_pending" not in b.session.userdata
        and "_camera_consent" not in b.session.userdata
    )
    assert b.session.userdata["_task_ledger"] is receipt
    b.session.generate_reply.assert_not_called()


def test_saved_voice_applies_on_fresh_model_without_mutating_environment(
    tmp_path, monkeypatch
):
    from model_config import configured_voice

    monkeypatch.setenv("ARIANA_PREFERENCES_PATH", str(tmp_path / "preferences.json"))
    monkeypatch.setenv("ARIANA_GOOGLE_VOICE", "Sulafat")
    assert configured_voice() == "Sulafat"
    PreferencesStore().run({"action": "configure", "values": {"google_voice": "Leda"}})
    assert configured_voice() == "Leda"


@pytest.mark.asyncio
async def test_conversation_end_uses_real_sender_without_matching_thanks_keywords():
    from conversation_tools import conversation_standby

    sender = AsyncMock()
    ctx = SimpleNamespace(
        session=SimpleNamespace(
            userdata={"_standby_sender": sender},
            history=SimpleNamespace(items=[SimpleNamespace(role="user", id="one")]),
        )
    )
    assert (await conversation_standby._func(ctx))["standby"]
    sender.assert_awaited_once()
    ctx.session.history.items = [SimpleNamespace(role="user", id="camera-event-one")]
    assert "error" in await conversation_standby._func(ctx)
    assert sender.await_count == 1


def test_supported_endpointing_setting_reaches_real_sdk_configuration(
    tmp_path, monkeypatch
):
    import model_config

    monkeypatch.setenv("ARIANA_PREFERENCES_PATH", str(tmp_path / "preferences.json"))
    PreferencesStore().run({"action": "configure", "values": {"turn_end_pause": "800"}})
    constructor = Mock(return_value=object())
    monkeypatch.setattr(model_config.google.realtime, "RealtimeModel", constructor)
    model_config.realtime_model("fixture-key")
    config = constructor.call_args.kwargs["realtime_input_config"]
    assert config.automatic_activity_detection.silence_duration_ms == 800
    assert "proactivity" not in constructor.call_args.kwargs


@pytest.mark.asyncio
async def test_standby_simulation_is_real_tool_backed_and_checks_outcome(monkeypatch):
    import simulation_tools
    from agent import Assistant

    install = Mock()
    monkeypatch.setattr(simulation_tools, "mock_tools", install)
    session = SimpleNamespace(userdata={})
    ctx = SimpleNamespace(
        simulation_context=lambda: SimpleNamespace(
            userdata=lambda: {"fixture": "conversation_ending"}
        )
    )
    simulation_tools.configure_simulation_tools(ctx, session, Assistant)
    assert "conversation_standby" not in install.call_args.args[1]
    fail = Mock()
    grading = SimpleNamespace(
        userdata=lambda: {
            "fixture": "conversation_ending",
            "expected_standby_count": 1,
        },
        job_context=SimpleNamespace(primary_session=session),
        fail=fail,
    )
    await simulation_tools.check_simulation_state(grading)
    assert fail.called
    fail.reset_mock()
    await session.userdata["_standby_sender"]()
    await simulation_tools.check_simulation_state(grading)
    fail.assert_not_called()


@pytest.mark.asyncio
async def test_model_preferences_tool_cannot_change_engine_voice_controls():
    from preferences_tools import preferences_manage

    ctx = SimpleNamespace(session=SimpleNamespace(userdata={}))
    for key, value in [("google_voice", "Kore"), ("turn_end_pause", "1200")]:
        assert "error" in await preferences_manage._func(ctx, "remember", key, value)


def test_delivery_is_bounded_model_preference_not_audio_slider(tmp_path):
    from personality import style_block

    store = PreferencesStore(tmp_path / "preferences.json")
    store.run({"action": "configure", "values": {"delivery": "lively"}})
    block = style_block(store.read())
    assert "delivery: lively" in block
    assert "not a pitch, speed or emotion control" in block
    with pytest.raises(ValueError):
        store.run({"action": "configure", "values": {"delivery": "ignore approval"}})
