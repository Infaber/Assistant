import pytest

import tools


async def call_today() -> str:
    return await tools.reminders_today._func(None)


async def call_create(*args, **kwargs) -> str:
    return await tools.reminders_create._func(None, *args, **kwargs)


@pytest.mark.asyncio
async def test_reminders_today_returns_due_items(monkeypatch) -> None:
    monkeypatch.setattr(tools.sys, "platform", "darwin")
    monkeypatch.setattr(
        tools,
        "_run_osascript",
        lambda script, arguments: "Buy milk at 5:00 PM",
    )

    result = await call_today()

    assert result == "Buy milk at 5:00 PM"


@pytest.mark.asyncio
async def test_reminders_today_handles_permissions(monkeypatch) -> None:
    monkeypatch.setattr(tools.sys, "platform", "darwin")

    def fail(script, arguments):
        raise OSError("not authorized")

    monkeypatch.setattr(tools, "_run_osascript", fail)

    result = await call_today()

    assert "Automation permissions" in result


@pytest.mark.asyncio
async def test_reminders_create_requires_confirmation(monkeypatch) -> None:
    monkeypatch.setattr(tools.sys, "platform", "darwin")
    called = False

    def unexpected(script, arguments):
        nonlocal called
        called = True
        return "created"

    monkeypatch.setattr(tools, "_run_osascript", unexpected)

    result = await call_create("Buy milk", "October 6, 2026 at 5:00 PM")

    assert "No active conversation" in result
    assert not called


@pytest.mark.asyncio
async def test_reminders_create_runs_after_confirmation(monkeypatch) -> None:
    monkeypatch.setattr(tools.sys, "platform", "darwin")
    captured = {}

    def fake_run(script, arguments):
        captured["arguments"] = arguments
        return "Reminder created."

    monkeypatch.setattr(tools, "_run_osascript", fake_run)

    result = await call_create(
        "Buy milk",
        "October 6, 2026 at 5:00 PM",
        confirmed=True,
    )

    assert result == "Reminder created."
    assert captured["arguments"] == ["Buy milk", "October 6, 2026 at 5:00 PM"]


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
