import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from action_events import ActivityPublisher, observed, result_state


@pytest.mark.parametrize(
    "result,status",
    [
        ({"error": "private"}, "failed"),
        ({"verified": True}, "verified"),
        ({"uncertain": True, "error": "private"}, "uncertain"),
        ({"preview": "private"}, "approval"),
        ({"success": True}, "returned"),
        ("Error: private text", "returned"),
    ],
)
def test_result_states_do_not_invent_verification(result, status):
    assert result_state(result)[0] == status


@pytest.mark.asyncio
async def test_events_contain_no_arguments_results_or_tracebacks():
    sender = AsyncMock()
    ctx = SimpleNamespace(
        session=SimpleNamespace(userdata={"_activity_sender": sender})
    )

    @observed("Test action")
    async def action(context, secret):
        return {"verified": True, "private": secret}

    assert (await action(ctx, "personal note"))["private"] == "personal note"
    events = [call.args[0] for call in sender.call_args_list]
    assert [e["status"] for e in events] == ["running", "verified"]
    assert events[0]["id"] == events[1]["id"]
    assert "personal note" not in json.dumps(events)

    @observed("Test failure")
    async def fail(context):
        raise RuntimeError("private exception detail")

    with pytest.raises(RuntimeError):
        await fail(ctx)
    assert sender.call_args.args[0]["status"] == "failed"
    assert "private exception detail" not in json.dumps(sender.call_args.args[0])


@pytest.mark.asyncio
async def test_publishing_cannot_block_tool_execution_or_replay():
    sent = asyncio.Event()
    release = asyncio.Event()

    async def network(*args, **kwargs):
        sent.set()
        await release.wait()
        raise RuntimeError("connection closed")

    room = SimpleNamespace(local_participant=SimpleNamespace(publish_data=network))
    publisher = ActivityPublisher(room)
    await publisher.enqueue({"id": "one"})
    await asyncio.wait_for(sent.wait(), 0.2)
    release.set()
    await publisher.close()


@pytest.mark.asyncio
async def test_cancelled_action_is_uncertain_and_not_retried():
    sender = AsyncMock()
    ctx = SimpleNamespace(
        session=SimpleNamespace(userdata={"_activity_sender": sender})
    )
    calls = 0

    @observed("Action")
    async def action(context):
        nonlocal calls
        calls += 1
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await action(ctx)
    assert calls == 1
    assert sender.call_args.args[0]["status"] == "uncertain"
