from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from livekit.agents.llm import ChatContext

import tools


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool,args",
    [
        (
            tools.calendar_create_event,
            ["Dentist", "October 6, 2026 at 10:00 AM", "October 6, 2026 at 11:00 AM"],
        ),
        (tools.reminders_create, ["Buy milk", ""]),
        (tools.mail_send, ["alex@example.com", "Hello", "Message"]),
    ],
)
async def test_every_apple_write_requires_later_user_and_single_use(
    monkeypatch, tool, args
):
    monkeypatch.setattr(tools.sys, "platform", "darwin")
    run = Mock(return_value="Written")
    monkeypatch.setattr(tools, "_run_osascript", run)
    history = ChatContext()
    history.add_message(role="user", content="Please do this")
    ctx = SimpleNamespace(session=SimpleNamespace(userdata={}, history=history))
    assert "NEW user reply" in await tool._func(ctx, *args, confirmed=True)
    run.assert_not_called()
    history.add_message(role="user", content="Go ahead")
    assert await tool._func(ctx, *args, confirmed=True) == "Written"
    assert "error" in await tool._func(ctx, *args, confirmed=True)
    assert run.call_count == 1
