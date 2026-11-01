import json
from types import SimpleNamespace

import pytest
from livekit.agents import AgentSession
from livekit.agents.llm import ChatMessage
from livekit.agents.voice.events import ConversationItemAddedEvent

from performance import Performance, install_performance


def test_monotonic_measurement_records_failed_work_without_swallowing_error():
    ticks = iter([2, 2.125])
    performance = Performance(clock=lambda: next(ticks))
    with pytest.raises(TimeoutError), performance.measure("local_router"):
        raise TimeoutError("private payload")
    assert performance.summary() == {
        "local_router": {"samples": 1, "mean_ms": 125.0, "max_ms": 125.0}
    }
    assert "private" not in json.dumps(list(performance.samples))


def test_storage_is_bounded_and_invalid_provider_timings_are_ignored():
    performance = Performance()
    for value in [-1, float("nan"), float("inf"), "secret", True, None]:
        performance.record("e2e_latency", value)
    assert not performance.samples
    for _ in range(120):
        performance.record("e2e_latency", 0.5)
    assert len(performance.samples) == 100


@pytest.mark.asyncio
async def test_real_sdk_event_wiring_records_only_allowlisted_numbers(caplog):
    session = AgentSession(userdata={})
    performance = install_performance(session)
    with caplog.at_level("INFO", logger="ariana.performance"):
        session.emit(
            "conversation_item_added",
            ConversationItemAddedEvent(
                item=ChatMessage(
                    role="assistant",
                    content=["private personal note"],
                    metrics={
                        "e2e_latency": 0.4,
                        "tts_node_ttfb": 0.1,
                        "provider_request_ids": ["secret"],
                        "llm_metadata": {"model_name": "private-model"},
                    },
                )
            ),
        )
    assert set(performance.summary()) == {"e2e_latency", "tts_node_ttfb"}
    assert "private" not in caplog.text and "secret" not in caplog.text


@pytest.mark.asyncio
async def test_missing_metrics_do_not_break_non_message_events():
    session = AgentSession(userdata={})
    performance = install_performance(session)
    session.emit("conversation_item_added", SimpleNamespace(item=object()))
    assert performance.summary() == {}


@pytest.mark.asyncio
async def test_sdk_tool_timing_handles_parallel_end_and_cancel_without_payload(caplog):
    from livekit.agents.llm import FunctionCall
    from livekit.agents.voice.events import (
        ToolCallEnded,
        ToolCallStarted,
        ToolExecutionUpdatedEvent,
    )

    session = AgentSession(userdata={})
    ticks = iter([1, 2, 3, 4])
    performance = Performance(clock=lambda: next(ticks))
    session.userdata["_performance"] = performance
    install_performance(session)

    def send(update):
        session.emit("tool_execution_updated", ToolExecutionUpdatedEvent(update=update))

    with caplog.at_level("INFO", logger="ariana.performance"):
        for key in ["one", "two"]:
            send(
                ToolCallStarted(
                    function_call=FunctionCall(
                        call_id=key, name="private_name", arguments='{"body":"secret"}'
                    )
                )
            )
        send(
            ToolCallEnded(
                id="two_final",
                call_id="two",
                status="cancelled",
                message="private result",
            )
        )
        send(
            ToolCallEnded(
                id="one", call_id="one", status="done", message="private result"
            )
        )
        send(ToolCallEnded(id="one", call_id="one", status="done"))
    assert list(performance.samples) == [
        {"stage": "tool_execution", "milliseconds": 1000},
        {"stage": "tool_execution", "milliseconds": 3000},
    ]
    assert "private" not in caplog.text and "secret" not in caplog.text


@pytest.mark.asyncio
async def test_real_sdk_state_timings_measure_events_without_claiming_acoustic_latency():
    from livekit.agents.voice.events import (
        AgentStateChangedEvent,
        UserStateChangedEvent,
    )

    ticks = iter([1, 2, 2.4, 3, 3.08])
    session = AgentSession(
        userdata={"_performance": Performance(clock=lambda: next(ticks))}
    )
    metrics = install_performance(session)
    session.emit(
        "user_state_changed",
        UserStateChangedEvent(old_state="listening", new_state="speaking"),
    )
    session.emit(
        "user_state_changed",
        UserStateChangedEvent(old_state="speaking", new_state="listening"),
    )
    session.emit(
        "agent_state_changed",
        AgentStateChangedEvent(old_state="thinking", new_state="speaking"),
    )
    session.emit(
        "user_state_changed",
        UserStateChangedEvent(old_state="listening", new_state="speaking"),
    )
    session.emit(
        "agent_state_changed",
        AgentStateChangedEvent(old_state="speaking", new_state="listening"),
    )
    summary = metrics.summary()
    assert summary["sdk_user_end_to_speaking_state"]["mean_ms"] == 400
    assert summary["sdk_overlap_to_speaking_state_stop"]["mean_ms"] == 80
    assert "first_audible_audio" not in summary
