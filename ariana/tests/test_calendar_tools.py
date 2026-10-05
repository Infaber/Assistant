import pytest

import tools


async def call_today() -> str:
    return await tools.calendar_today._func(None)


async def call_create(*args, **kwargs) -> str:
    return await tools.calendar_create_event._func(None, *args, **kwargs)


@pytest.mark.asyncio
async def test_calendar_today_returns_events(monkeypatch) -> None:
    monkeypatch.setattr(tools.sys, "platform", "darwin")
    monkeypatch.setattr(
        tools,
        "_run_osascript",
        lambda script, arguments: "Dentist at 10:00\nLunch at 12:30",
    )

    result = await call_today()

    assert result == "Dentist at 10:00\nLunch at 12:30"


@pytest.mark.asyncio
async def test_calendar_today_handles_permissions(monkeypatch) -> None:
    monkeypatch.setattr(tools.sys, "platform", "darwin")

    def fail(script, arguments):
        raise OSError("not authorized")

    monkeypatch.setattr(tools, "_run_osascript", fail)

    result = await call_today()

    assert "Automation permissions" in result


@pytest.mark.asyncio
async def test_calendar_create_requires_confirmation(monkeypatch) -> None:
    monkeypatch.setattr(tools.sys, "platform", "darwin")
    called = False

    def unexpected(script, arguments):
        nonlocal called
        called = True
        return "created"

    monkeypatch.setattr(tools, "_run_osascript", unexpected)

    result = await call_create(
        "Dentist",
        "October 6, 2026 at 10:00 AM",
        "October 6, 2026 at 11:00 AM",
    )

    assert "Please confirm" in result
    assert not called


@pytest.mark.asyncio
async def test_calendar_create_runs_after_confirmation(monkeypatch) -> None:
    monkeypatch.setattr(tools.sys, "platform", "darwin")
    captured = {}

    def fake_run(script, arguments):
        captured["arguments"] = arguments
        return "Calendar event created."

    monkeypatch.setattr(tools, "_run_osascript", fake_run)

    result = await call_create(
        "Dentist",
        "October 6, 2026 at 10:00 AM",
        "October 6, 2026 at 11:00 AM",
        confirmed=True,
    )

    assert result == "Calendar event created."
    assert captured["arguments"] == [
        "Dentist",
        "October 6, 2026 at 10:00 AM",
        "October 6, 2026 at 11:00 AM",
    ]
