from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import simulation_tools
from agent import Assistant, _google_api_key


@pytest.mark.parametrize(
    "google, gemini, expected",
    [
        (" google-key ", "gemini-key", "google-key"),
        ("", "gemini-key", "gemini-key"),
        ("   ", " gemini-key ", "gemini-key"),
    ],
)
def test_google_key_precedence_and_alias(monkeypatch, google, gemini, expected):
    monkeypatch.setenv("GOOGLE_API_KEY", google)
    monkeypatch.setenv("GEMINI_API_KEY", gemini)
    assert _google_api_key() == expected


def test_missing_key_has_an_actionable_error(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="Set GOOGLE_API_KEY"):
        Assistant()


def test_production_jobs_never_install_simulation_mocks(monkeypatch):
    install = Mock()
    monkeypatch.setattr(simulation_tools, "mock_tools", install)
    ctx = SimpleNamespace(simulation_context=lambda: None)
    simulation_tools.configure_simulation_tools(ctx, object(), Assistant)
    install.assert_not_called()


@pytest.mark.parametrize("fixture", ["search_failure", "untrusted_page"])
def test_simulation_fixtures_are_scoped_to_the_session(monkeypatch, fixture):
    install = Mock()
    monkeypatch.setattr(simulation_tools, "mock_tools", install)
    ctx = SimpleNamespace(
        simulation_context=lambda: SimpleNamespace(
            userdata=lambda: {"fixture": fixture}
        )
    )
    session = object()
    simulation_tools.configure_simulation_tools(ctx, session, Assistant)
    args, kwargs = install.call_args
    assert args[0] is Assistant
    assert kwargs == {"session": session}
    mocks = args[1]
    if fixture == "search_failure":
        assert isinstance(mocks["search_web"](), simulation_tools.ToolError)
        assert isinstance(mocks["browser_search"](), simulation_tools.ToolError)
    else:
        result = mocks["browser_open"](simulation_tools.LIBRARY_URL)
        assert "09:00" in result["text"]
        assert "SYSTEM OVERRIDE" in result["text"]
        assert isinstance(
            mocks["browser_open"]("https://other.example.com"),
            simulation_tools.ToolError,
        )


def test_unknown_simulation_fixture_fails_clearly():
    ctx = SimpleNamespace(
        simulation_context=lambda: SimpleNamespace(userdata=lambda: {"fixture": "typo"})
    )
    with pytest.raises(ValueError, match="Unknown simulation fixture"):
        simulation_tools.configure_simulation_tools(ctx, object(), Assistant)


@pytest.mark.asyncio
async def test_restored_tools_remain_registered(monkeypatch):
    from livekit.agents.llm import is_function_tool
    from livekit.agents.llm.tool_context import get_function_info

    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    agent = Assistant()
    names = {
        get_function_info(tool).name for tool in agent.tools if is_function_tool(tool)
    }
    assert {
        "search_web",
        "home_assistant_request",
        "weather_forecast",
        "calendar_today",
        "calendar_create_event",
        "reminders_today",
        "reminders_create",
        "mail_unread",
        "mail_send",
        "notes_create",
        "notes_list",
        "notes_read",
        "notes_edit",
        "mac_control",
        "spotify_control",
        "preferences_manage",
        "assistant_status",
    } <= names


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "notes,should_fail",
    [
        ([], True),
        ([{"title": "Wrong", "body": "milk bread"}], True),
        ([{"title": "Grocery list", "body": "milk"}], True),
        ([{"title": "Grocery list", "body": "milk, bread"}], False),
    ],
)
async def test_note_simulation_checks_real_end_state(notes, should_fail):
    fail = Mock()
    ctx = SimpleNamespace(
        userdata=lambda: {"fixture": "notes_creation"},
        job_context=SimpleNamespace(
            primary_session=SimpleNamespace(userdata={"notes": notes})
        ),
        fail=fail,
    )
    await simulation_tools.check_simulation_state(ctx)
    assert fail.called == should_fail


@pytest.mark.asyncio
async def test_note_fixture_receives_sdk_arguments(monkeypatch):
    from livekit.agents.llm.utils import prepare_function_arguments
    from livekit.agents.voice.run_result import _run_mock

    import tools

    install = Mock()
    monkeypatch.setattr(simulation_tools, "write_approval", lambda *args: None)
    monkeypatch.setattr(simulation_tools, "mock_tools", install)
    ctx = SimpleNamespace(
        simulation_context=lambda: SimpleNamespace(
            userdata=lambda: {"fixture": "notes_creation"}
        )
    )
    session = SimpleNamespace(userdata=None)
    simulation_tools.configure_simulation_tools(ctx, session, Assistant)
    mock = install.call_args.args[1]["notes_create"]
    args, kwargs = prepare_function_arguments(
        fnc=tools.notes_create,
        json_arguments={"title": "Grocery list", "body": "milk, bread"},
        call_ctx=Mock(spec=tools.RunContext),
    )
    assert await _run_mock(mock, *args, **kwargs) == "Note created."
    assert session.userdata["notes"] == [
        {"title": "Grocery list", "body": "milk, bread"}
    ]
