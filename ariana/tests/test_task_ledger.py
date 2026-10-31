import asyncio
from types import SimpleNamespace

import pytest

from action_events import observed
from task_ledger import ledger_for


@pytest.mark.asyncio
async def test_partial_success_keeps_verified_work_and_blocks_uncertain_write():
    ctx = SimpleNamespace(session=SimpleNamespace(userdata={}))
    count = 0

    @observed("Safari result")
    async def browser_read(context):
        return {"verified": True}

    @observed("Create note")
    async def notes_create(context, title, confirmed=False):
        nonlocal count
        count += 1
        return {"uncertain": True}

    await browser_read(ctx)
    await notes_create(ctx, "Summary", confirmed=True)
    blocked = await notes_create(ctx, "Summary", confirmed=True)
    assert count == 1 and blocked["uncertain"]
    assert [step["status"] for step in ledger_for(ctx).summary()] == [
        "verified",
        "uncertain",
    ]


@pytest.mark.asyncio
async def test_interrupted_consequential_action_cannot_be_replayed():
    ctx = SimpleNamespace(session=SimpleNamespace(userdata={}))

    @observed("Send mail")
    async def mail_send(context, body, confirmed=False):
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await mail_send(ctx, "Hello", confirmed=True)
    result = await mail_send(ctx, "Hello", confirmed=True)
    assert result["previous_status"] == "uncertain"


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", [TimeoutError, asyncio.CancelledError])
async def test_failed_notes_step_keeps_safari_and_blocks_second_dispatch(fault):
    ctx = SimpleNamespace(session=SimpleNamespace(userdata={}))
    calls = {"safari": 0, "notes": 0}

    @observed("Safari result")
    async def browser_read(context):
        calls["safari"] += 1
        return {"verified": True}

    @observed("Create note")
    async def notes_create(context, confirmed=False):
        calls["notes"] += 1
        raise fault()

    await browser_read(ctx)
    with pytest.raises(fault):
        await notes_create(ctx, confirmed=True)
    result = await notes_create(ctx, confirmed=True)
    assert result["previous_status"] == "uncertain"
    assert calls == {"safari": 1, "notes": 1}
    assert [step["status"] for step in ledger_for(ctx).summary()] == [
        "verified",
        "uncertain",
    ]
    assert "tool.notes_create" in ctx.session.userdata["_performance"].summary()
