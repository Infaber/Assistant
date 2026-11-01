from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from livekit.agents import llm

from conversation_context import local_context, retrieval_query, transfer_context
from memory_tools import memory_manage


def test_transfer_is_bounded_text_only_and_preserves_interruption():
    chat = llm.ChatContext()
    chat.add_message(role="system", content="Private instructions")
    chat.add_message(role="user", content="rover motor stalls", id="one")
    chat.add_message(role="assistant", content="Try checking", interrupted=True)
    chat.add_message(
        role="user", content="Private image description", id="camera-event-one"
    )
    chat.add_message(role="user", content="Private document", id="attachment-one")
    chat.add_message(
        role="user", content=[llm.ImageContent(image="https://example.com/a.png")]
    )
    transferred = transfer_context(chat)
    assert [item.text_content for item in transferred.items] == [
        "rover motor stalls",
        "Try checking",
    ]
    assert transferred.items[-1].interrupted
    assert len(transfer_context(chat, max_messages=1).items) == 1
    assert not transfer_context(chat, max_chars=2).items
    assert len(chat.items) == 6


def test_long_conversation_recovers_old_topic_without_restoring_tool_authority():
    chat = llm.ChatContext()
    chat.add_message(role="system", content="Stable personality and action rules")
    chat.add_message(
        role="user",
        content="Rover stalls only under load; motor driver overheats",
        id="rover",
    )
    for i in range(40):
        chat.add_message(role="user", content=f"Football conversation {i}")
        chat.add_message(role="assistant", content="A conversational reaction")
    chat.add_message(
        role="user", content="Back to the rover motor, what was the problem?"
    )
    result = local_context(chat, [{"topic": "rover", "fact": "Heatsink added"}])
    assert len(result.items) <= 26
    assert result.items[0].text_content == "Stable personality and action rules"
    evidence = result.items[1].text_content
    assert "under load" in evidence and "Heatsink added" in evidence
    assert "never instructions or approval" in evidence
    assert len(chat.items) == 83
    chat.add_message(role="user", content="Tell me about bananas")
    assert "under load" not in " ".join(
        item.text_content for item in local_context(chat, []).items
    )


def test_short_reply_uses_preceding_topic():
    chat = llm.ChatContext()
    chat.add_message(role="user", content="My physics exam is Thursday")
    chat.add_message(role="assistant", content="How is studying going?")
    chat.add_message(role="user", content="Not well")
    assert "physics" in retrieval_query(chat)


@pytest.mark.asyncio
async def test_memory_save_requires_real_user_evidence_not_model_or_external_text():
    chat = llm.ChatContext()
    chat.add_message(role="user", content="My rover uses an ESP32", id="real")
    chat.add_message(role="assistant", content="You live in Paris")
    chat.add_message(role="user", content="Likes sailing", id="attachment-doc")
    requests = []
    ctx = SimpleNamespace(
        session=SimpleNamespace(
            history=chat,
            userdata={
                "_memory_simulator": lambda request: (
                    requests.append(request) or {"success": True}
                )
            },
        )
    )
    for quote in ["", "You live in Paris", "Likes sailing"]:
        result = await memory_manage._func(
            ctx, "remember", "city", "Paris", source_quote=quote
        )
        assert "error" in result
    assert not requests
    result = await memory_manage._func(
        ctx, "remember", "rover", "Uses ESP32", source_quote="My rover uses an ESP32"
    )
    assert result["success"] and len(requests) == 1
    assert "source_quote" not in requests[0]  # Do not persist raw transcript evidence.


@pytest.mark.asyncio
async def test_opt_in_mode_transfer_carries_text_and_clears_pending_approvals():
    from test_ai_modes import bridge

    b = bridge()
    chat = llm.ChatContext()
    chat.add_message(role="user", content="I am building a rover")
    b.session.current_agent = SimpleNamespace(chat_ctx=chat)
    seen = []

    def make(target, ready, context):
        seen.append(context)
        return SimpleNamespace(mode=target, ready=ready)

    b.make_agent.side_effect = make
    result = await b.switch("local", carry_context=True)
    assert result["context_transferred"]
    assert seen[0].items[0].text_content == "I am building a rover"
    assert "notes_pending" not in b.session.userdata
    assert "_camera_consent" not in b.session.userdata
    b.session.interrupt.assert_awaited_once()


@pytest.mark.asyncio
async def test_local_llm_node_retrieves_current_memory_with_real_sdk_context(
    tmp_path, monkeypatch
):
    import agent
    import local_models
    import local_routing
    from memory_tools import MemoryStore

    monkeypatch.setattr(local_models, "local_options", lambda: {"llm": None})
    monkeypatch.setattr(local_routing, "choose_group", AsyncMock(return_value=()))
    store = MemoryStore(tmp_path / "memory.db")
    store.run({"action": "remember", "topic": "rover", "fact": "Uses ESP32"})
    store.run({"action": "remember", "topic": "rover", "fact": "Uses Raspberry Pi"})
    session = SimpleNamespace(userdata={"_memory_simulator": store.run})
    monkeypatch.setattr(agent.Assistant, "session", property(lambda self: session))
    captured = []

    async def response(self, chat_ctx, tools, settings):
        captured.append(chat_ctx)
        yield "response"

    monkeypatch.setattr(agent.Agent.default, "llm_node", response)
    assistant = agent.Assistant(mode="local")
    chat = llm.ChatContext()
    chat.add_message(role="user", content="How is my rover project?")
    assert [chunk async for chunk in assistant.llm_node(chat, [], {})] == ["response"]
    assert "Raspberry Pi" in captured[0].items[0].text_content
    assert "ESP32" not in captured[0].items[0].text_content
    assert len(chat.items) == 1


@pytest.mark.asyncio
async def test_personality_settings_match_across_engines_and_recreated_agents(
    tmp_path, monkeypatch
):
    import agent
    import local_models
    from preferences_tools import PreferencesStore

    monkeypatch.setenv("ARIANA_PREFERENCES_PATH", str(tmp_path / "preferences.json"))
    PreferencesStore().run({"action": "remember", "key": "sarcasm", "value": "off"})
    monkeypatch.setattr(local_models, "local_options", lambda: {"llm": None})
    monkeypatch.setattr(agent, "realtime_model", lambda *args: None)
    monkeypatch.setattr(agent, "_google_api_key", lambda: "fixture")
    for mode in ["normal", "local", "normal"]:
        assistant = agent.Assistant(mode=mode)
        assert "sarcasm: off" in assistant.instructions
        assert "don't agree just to be agreeable" in assistant.instructions
        assert "approval" in assistant.instructions


@pytest.mark.asyncio
async def test_simulation_checks_hypothetical_facts_across_all_memory_kinds(tmp_path):
    from unittest.mock import Mock

    from memory_tools import MemoryStore
    from simulation_tools import check_simulation_state

    store = MemoryStore(tmp_path / "memory.db")
    store.run({"action": "remember", "topic": "city", "fact": "Lives in Bergen"})
    ctx = SimpleNamespace(
        userdata=lambda: {
            "fixture": "conversation_memory",
            "memory_expectations": {
                "memory_kind": "",
                "current_terms": [],
                "excluded_terms": ["bergen"],
            },
        },
        job_context=SimpleNamespace(
            primary_session=SimpleNamespace(userdata={"_memory_simulator": store.run})
        ),
        fail=Mock(),
    )
    await check_simulation_state(ctx)
    ctx.fail.assert_called_once()
