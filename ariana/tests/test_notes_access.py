from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from livekit.agents.llm import ChatContext

import notes_tools as notes


def conversation(text="Create a note"):
    history = ChatContext()
    history.add_message(role="user", content=text)
    return SimpleNamespace(session=SimpleNamespace(userdata=None, history=history))


def test_write_needs_preview_and_later_yes_for_identical_payload():
    ctx = conversation()
    payload = {"title": "Ideas", "body": "Spotify"}
    assert notes.write_approval(ctx, "create", payload, True)
    assert notes.write_approval(ctx, "create", payload, True)  # no new user turn
    ctx.session.history.add_message(role="user", content="Yes")
    assert notes.write_approval(ctx, "create", payload, True) is None
    assert notes.write_approval(
        ctx, "create", payload, True
    )  # consumed; cannot duplicate


@pytest.mark.parametrize(
    "reply", ["No", "Can you read my notes?", "Yes but add eggs", "Don't do it"]
)
def test_non_confirmation_and_corrections_never_write(reply):
    ctx = conversation()
    payload = {"title": "Ideas", "body": "Spotify"}
    notes.write_approval(ctx, "create", payload, False)
    ctx.session.history.add_message(role="user", content=reply)
    assert notes.write_approval(ctx, "create", payload, True)


def test_changed_payload_requires_new_preview():
    ctx = conversation()
    notes.write_approval(ctx, "create", {"body": "milk"}, False)
    ctx.session.history.add_message(role="user", content="Yes")
    assert notes.write_approval(ctx, "create", {"body": "eggs"}, True)


def test_expired_preview_cannot_write(monkeypatch):
    ctx = conversation()
    notes.write_approval(ctx, "create", {}, False)
    ctx.session.history.add_message(role="user", content="Yes")
    monkeypatch.setattr(
        notes.time,
        "monotonic",
        lambda: ctx.session.userdata["notes_pending"]["time"] + 301,
    )
    assert notes.write_approval(ctx, "create", {}, True)


@pytest.mark.asyncio
async def test_list_bounds_and_read_id(monkeypatch):
    run = Mock(return_value={"notes": [{"id": "a", "title": "Ideas"}]})
    monkeypatch.setattr(notes, "_run_notes", run)
    monkeypatch.setattr(notes.sys, "platform", "darwin")
    await notes.notes_list._func(None, "Ideas", 100)
    assert run.call_args.args[0] == {"action": "list", "query": "Ideas", "limit": 50}
    await notes.notes_read._func(None, "a")
    assert run.call_args.args[0] == {"action": "read", "note_id": "a"}


@pytest.mark.asyncio
async def test_edit_is_guarded_and_escapes_separate_data(monkeypatch):
    ctx = conversation("Add this to Ideas")
    run = Mock(return_value={"success": True})
    monkeypatch.setattr(notes, "_run_notes", run)
    monkeypatch.setattr(notes.sys, "platform", "darwin")
    args = (ctx, "note-a", "revision-1", "Ideas", "<script> & 📝")
    assert "preview" in await notes.notes_edit._func(*args)
    run.assert_not_called()
    ctx.session.history.add_message(role="user", content="Yes")
    assert (await notes.notes_edit._func(*args, confirmed=True))["success"]
    request = run.call_args.args[0]
    assert request["html"] == "<div>&lt;script&gt; &amp; 📝</div>"
    assert request["revision"] == "revision-1"
    assert request["mode"] == "append"


@pytest.mark.asyncio
async def test_access_reports_failure_and_mac_requirement(monkeypatch):
    monkeypatch.setattr(notes.sys, "platform", "darwin")
    monkeypatch.setattr(notes, "_run_notes", Mock(side_effect=OSError("denied")))
    assert "Automation" in (await notes.notes_read._func(None, "id"))["error"]
    monkeypatch.setattr(notes.sys, "platform", "linux")
    assert "Mac" in (await notes.notes_list._func(None))["error"]


@pytest.mark.parametrize(
    "case",
    [
        "append",
        "stale",
        "locked",
        "shared",
        "attachments",
        "duplicate_titles",
        "read_limit",
    ],
)
def test_notes_script_against_scripting_api_fixture(case):
    """Run the actual JXA logic with a fake API; no access to real Apple Notes."""
    import json
    import shutil
    import subprocess

    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is needed to execute the JavaScript API fixture")
    fixture = r"""
const assert = require('node:assert/strict');
let saved = '<html><body><h1>Ideas</h1><div>Spotify</div></body></html>';
let writes = 0;
const note = {
    id:()=> 'selected', name:()=> 'Ideas', container:()=>({name:()=> 'Notes'}),
    passwordProtected:()=> CASE === 'locked', shared:()=> CASE === 'shared',
    modificationDate:()=> new Date('2026-01-01T00:00:00.000Z'),
    plaintext:()=> CASE === 'read_limit' ? 'x'.repeat(20001) : 'Ideas\nSpotify',
    attachments:()=> CASE === 'attachments' ? [{}] : []
};
Object.defineProperty(note, 'body', {
    get:()=>()=>saved,
    set:value=>{writes++; saved=value;}
});
const other = Object.assign({}, note, {id:()=> 'other'});
const all = ()=> [note,other];
all.byId = id=>{assert.equal(id,'selected'); return note;};
function Application(name) {assert.equal(name,'Notes'); return {notes:all};}
let req = {action:'edit',note_id:'selected',revision:'2026-01-01T00:00:00.000Z',
    mode:'append',html:'<div>Literal $& and $1</div>'};
if (CASE === 'stale') req.revision = 'old';
if (CASE === 'attachments') req.mode = 'replace';
if (CASE === 'duplicate_titles') req = {action:'list',query:'Ideas',limit:20};
if (CASE === 'read_limit') req.action = 'read';
const out = JSON.parse(run([JSON.stringify(req)]));
if (CASE === 'append') {
    assert.equal(writes,1);
    assert.equal(saved,'<html><body><h1>Ideas</h1><div>Spotify</div><div>Literal $& and $1</div></body></html>');
    assert.equal(out.id,'selected');
} else if (CASE === 'duplicate_titles') {
    assert.deepEqual(out.notes.map(n=>n.id),['selected','other']);
    assert.equal(writes,0);
} else if (CASE === 'read_limit') {
    assert.equal(out.body.length,20000);
    assert.equal(out.truncated,true);
    assert.equal(writes,0);
} else {
    assert.ok(out.error);
    assert.equal(writes,0);
}
"""
    result = subprocess.run(
        [
            node,
            "-e",
            "const CASE=" + json.dumps(case) + ";\n" + notes.NOTES_JXA + fixture,
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr


def test_later_unrelated_yes_cannot_authorize_an_old_preview():
    ctx = conversation()
    payload = {"title": "Ideas", "body": "Spotify"}
    notes.write_approval(ctx, "create", payload, False)
    ctx.session.history.add_message(role="user", content="No")
    ctx.session.history.add_message(role="user", content="Yes")
    assert notes.write_approval(ctx, "create", payload, True)


@pytest.mark.asyncio
@pytest.mark.parametrize("initialized", [False, True])
@pytest.mark.parametrize("operation", ["create", "edit"])
async def test_real_sdk_session_previews_then_confirms_once(
    monkeypatch, initialized, operation
):
    from livekit.agents import AgentSession, RunContext

    import tools

    session = AgentSession(userdata={}) if initialized else AgentSession()
    if not initialized:
        with pytest.raises(ValueError, match="userdata is not set"):
            _ = session.userdata
    context = RunContext(
        session=session, speech_handle=Mock(num_steps=1), function_call=Mock()
    )
    session.history.add_message(
        role="user", content="Create Ariana Ideas with Spotify integration"
    )
    monkeypatch.setattr(notes.sys, "platform", "darwin")
    write = Mock(
        return_value="Note created." if operation == "create" else {"success": True}
    )
    if operation == "create":
        monkeypatch.setattr(tools, "_run_osascript", write)
        fn = tools.notes_create._func
        args = (context, "Ariana Ideas", "Spotify integration")
    else:
        monkeypatch.setattr(notes, "_run_notes", write)
        fn = notes.notes_edit._func
        args = (context, "note-a", "v1", "Ariana Ideas", "Spotify integration")
    preview = await fn(*args, confirmed=False)
    assert "Nothing saved" in str(preview)
    write.assert_not_called()
    assert "notes_pending" in session.userdata
    session.history.add_message(role="user", content="Yes")
    result = await fn(*args, confirmed=True)
    assert "created" in str(result) or result.get("success")
    write.assert_called_once()
    assert "notes_pending" not in session.userdata
    await fn(*args, confirmed=True)
    write.assert_called_once()  # A repeated invocation cannot save twice.
