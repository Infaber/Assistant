import pytest

import tools


async def call_unread() -> str:
    return await tools.mail_unread._func(None)


async def call_send(*args, **kwargs) -> str:
    return await tools.mail_send._func(None, *args, **kwargs)


@pytest.mark.asyncio
async def test_mail_unread_returns_summaries(monkeypatch) -> None:
    monkeypatch.setattr(tools.sys, "platform", "darwin")
    monkeypatch.setattr(
        tools,
        "_run_osascript",
        lambda script, arguments: "Alex <alex@example.com> | Dinner plans",
    )

    result = await call_unread()

    assert result == "Alex <alex@example.com> | Dinner plans"


@pytest.mark.asyncio
async def test_mail_unread_handles_permissions(monkeypatch) -> None:
    monkeypatch.setattr(tools.sys, "platform", "darwin")

    def fail(script, arguments):
        raise OSError("not authorized")

    monkeypatch.setattr(tools, "_run_osascript", fail)

    result = await call_unread()

    assert "Automation permissions" in result


@pytest.mark.asyncio
async def test_mail_send_requires_confirmation(monkeypatch) -> None:
    monkeypatch.setattr(tools.sys, "platform", "darwin")
    called = False

    def unexpected(script, arguments):
        nonlocal called
        called = True
        return "sent"

    monkeypatch.setattr(tools, "_run_osascript", unexpected)

    result = await call_send("alex@example.com", "Hello", "Hi there")

    assert "No active conversation" in result
    assert not called


@pytest.mark.asyncio
async def test_mail_send_runs_after_confirmation(monkeypatch) -> None:
    monkeypatch.setattr(tools.sys, "platform", "darwin")
    captured = {}

    def fake_run(script, arguments):
        captured["arguments"] = arguments
        return "Email sent."

    monkeypatch.setattr(tools, "_run_osascript", fake_run)

    result = await call_send(
        "alex@example.com",
        "Hello",
        "Hi there",
        confirmed=True,
    )

    assert result == "Email sent."
    assert captured["arguments"] == ["alex@example.com", "Hello", "Hi there"]


@pytest.fixture(autouse=True)
def approval_for_confirmed_script_tests(monkeypatch):
    original = tools.write_approval
    monkeypatch.setattr(
        tools,
        "write_approval",
        lambda context, action, payload, confirmed: (
            None if confirmed else original(context, action, payload, confirmed)
        ),
    )
