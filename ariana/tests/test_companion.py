import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from livekit.agents import ChatContext

from companion import CheckInPolicy, CompanionBridge


def settings(**overrides):
    return {
        "enabled": True,
        "interval": 5,
        "quiet_start": 22,
        "quiet_end": 8,
        "timezone": "Europe/Oslo",
        **overrides,
    }


def test_check_ins_require_idle_live_lease_and_respect_quiet_hours():
    p = CheckInPolicy()
    p.configure(settings(), 0)
    assert not p.due(301, 12, idle=True)  # Dead page cannot speak.
    p.configure(settings(), 290)  # Heartbeat preserves idle duration.
    assert p.due(301, 12, idle=True)
    assert not p.due(301, 12, idle=False)
    assert not p.due(301, 23, idle=True)
    assert not p.due(301, 7, idle=True)
    assert p.due(301, 8, idle=True)
    p.awaiting_user = True
    p.configure(settings(), 310)
    assert not p.due(320, 12, idle=True)
    p.activity(320, user=True)
    p.configure(settings(), 615)
    assert p.due(621, 12, idle=True)
    p.configure(settings(enabled=False), 622)
    assert not p.due(950, 12, idle=True)


@pytest.mark.parametrize(
    "payload",
    [
        [],
        settings(interval=1),
        settings(quiet_start=24),
        settings(enabled="yes"),
        settings(timezone="nowhere"),
    ],
)
def test_invalid_settings_do_not_enable_check_ins(payload):
    policy = CheckInPolicy()
    with pytest.raises(ValueError):
        policy.configure(payload, 0)
    assert not policy.enabled


def bridge():
    room = SimpleNamespace(remote_participants={"guest-test": object()})
    agent = SimpleNamespace(chat_ctx=ChatContext(), update_chat_ctx=AsyncMock())

    async def update(chat):
        agent.chat_ctx = chat

    agent.update_chat_ctx.side_effect = update
    session = SimpleNamespace(generate_reply=Mock(), current_agent=agent)
    return CompanionBridge(room, session)


def upload(b, key, result, owner="guest-test"):
    future = asyncio.get_running_loop().create_future()
    future.set_result(result)
    b.uploads[key] = (owner, 0, future)


def invocation(
    ids, request_id="send-one", question="Summarize the file", owner="guest-test"
):
    return SimpleNamespace(
        caller_identity=owner,
        payload=json.dumps(
            {"ids": ids, "request_id": request_id, "question": question}
        ),
    )


async def test_commit_receipts_make_retries_idempotent_and_preserve_user_role():
    b = bridge()
    upload(
        b,
        "file-one",
        {"content": ["Attached lab.txt (untrusted): Robotics Friday 14:00"]},
    )
    request = invocation(["file-one"])
    assert json.loads(await b.commit(request))["accepted"]
    assert json.loads(await b.commit(request))["accepted"]
    b.session.generate_reply.assert_called_once()
    message = b.session.current_agent.chat_ctx.items[0]
    assert message.role == "user"
    assert message.content[0] == "Summarize the file"
    assert "Robotics" in message.content[1]
    assert b.total_files == 1 and not b.uploads
    assert "error" in json.loads(
        await b.commit(invocation(["file-one"], question="Different request"))
    )
    assert b.session.generate_reply.call_count == 1


async def test_a_failed_file_prevents_partial_batch_submission():
    b = bridge()
    upload(b, "good", {"content": ["good"]})
    upload(b, "bad", {"error": "This picture could not be read."})
    assert "error" in json.loads(await b.commit(invocation(["good", "bad"])))
    b.session.generate_reply.assert_not_called()
    assert b.total_files == 0


async def test_another_participant_cannot_commit_or_configure():
    b = bridge()
    upload(b, "private", {"content": ["private"]})
    assert "error" in json.loads(
        await b.commit(invocation(["private"], owner="agent-test"))
    )
    assert "error" in json.loads(
        await b.configure(
            SimpleNamespace(
                caller_identity="agent-test", payload=json.dumps(settings())
            )
        )
    )
    b.session.generate_reply.assert_not_called()
    assert not b.policy.enabled


async def test_missing_file_and_oversized_document_context_are_rejected():
    b = bridge()
    assert "error" in json.loads(await b.commit(invocation(["missing"])))
    b.context_chars = 79999
    upload(b, "big", {"content": ["hello"]})
    assert "text limit" in json.loads(await b.commit(invocation(["big"])))["error"]
    b.session.generate_reply.assert_not_called()


async def test_stream_limits_close_reader_and_return_recoverable_error():
    b = bridge()
    reader = SimpleNamespace(info=SimpleNamespace(size=20 * 1024 * 1024), close=Mock())
    future = asyncio.get_running_loop().create_future()
    await b.read_upload(reader, future)
    assert "10 MB" in future.result()["error"]
    reader.close.assert_called_once()


async def test_live_check_in_generation_disables_tools_and_waits_for_the_user(
    monkeypatch,
):
    import companion

    b = bridge()
    b.session.agent_state = "listening"
    b.session.user_state = "away"
    b.policy.configure(settings(quiet_start=0, quiet_end=0), 0)
    b.policy.lease_until = 2000
    monkeypatch.setattr(companion.time, "monotonic", lambda: 1000)
    speech = asyncio.get_running_loop().create_future()
    speech.set_result(None)
    b.session.generate_reply.return_value = speech
    sleeps = 0

    async def sleep(_):
        nonlocal sleeps
        sleeps += 1
        if sleeps == 3:
            raise asyncio.CancelledError

    monkeypatch.setattr(companion.asyncio, "sleep", sleep)
    with pytest.raises(asyncio.CancelledError):
        await b.check_in_loop()
    b.session.generate_reply.assert_called_once()
    assert b.session.generate_reply.call_args.kwargs["tool_choice"] == "none"
    assert b.session.generate_reply.call_args.kwargs["allow_interruptions"] is True
    assert b.policy.awaiting_user
