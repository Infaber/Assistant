import subprocess
from unittest.mock import Mock

import pytest

import tools


@pytest.fixture(autouse=True)
def allow_creation_for_script_tests(monkeypatch):
    # Guard behavior is tested separately against real conversation history.
    monkeypatch.setattr(tools, "write_approval", lambda *args: None)


@pytest.mark.asyncio
async def test_notes_are_mac_only(monkeypatch):
    monkeypatch.setattr(tools.sys, "platform", "linux")
    run = Mock()
    monkeypatch.setattr(tools, "_run_osascript", run)
    assert "locally on a Mac" in await tools.notes_create._func(None, "Title", "Body")
    run.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("title,body", [("", "body"), ("title", "   ")])
async def test_notes_require_title_and_body(monkeypatch, title, body):
    monkeypatch.setattr(tools.sys, "platform", "darwin")
    run = Mock()
    monkeypatch.setattr(tools, "_run_osascript", run)
    assert "need a title and contents" in await tools.notes_create._func(
        None, title, body
    )
    run.assert_not_called()


@pytest.mark.asyncio
async def test_notes_escape_html_and_pass_user_text_as_arguments(monkeypatch):
    monkeypatch.setattr(tools.sys, "platform", "darwin")
    run = Mock(return_value="Note created.")
    monkeypatch.setattr(tools, "_run_osascript", run)
    title = 'Shopping <list> "today"'
    body = "Milk & bread\n<script>bad</script> 📝"
    assert await tools.notes_create._func(None, title, body) == "Note created."
    script, arguments, timeout = run.call_args.args
    assert title not in script and body not in script
    assert arguments[0] == title
    assert (
        arguments[1]
        == "<h1>Shopping &lt;list&gt; &quot;today&quot;</h1><div>Milk &amp; bread<br>&lt;script&gt;bad&lt;/script&gt; 📝</div>"
    )
    assert timeout == 30


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error,expected",
    [
        (OSError("denied"), "Automation"),
        (subprocess.TimeoutExpired("osascript", 30), "may already exist"),
    ],
)
async def test_notes_report_permission_errors_and_uncertain_timeout(
    monkeypatch, error, expected
):
    monkeypatch.setattr(tools.sys, "platform", "darwin")
    monkeypatch.setattr(tools, "_run_osascript", Mock(side_effect=error))
    assert expected in await tools.notes_create._func(None, "Title", "Body")
