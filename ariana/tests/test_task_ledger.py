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
