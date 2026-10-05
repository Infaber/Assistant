import json
import shutil
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from livekit.agents import AgentSession

import spotify_tools as spotify
from mac_simulation import SpotifyFixture


@pytest.mark.asyncio
async def test_search_play_pause_uses_direct_backend():
    fixture = SpotifyFixture()
    ctx = SimpleNamespace(
        session=SimpleNamespace(userdata={"_spotify_simulator": fixture.run})
    )
    fn = spotify.spotify_control._func
    assert (await fn(ctx, "search", " Dave "))["query"] == "Dave"
    assert (await fn(ctx, "play"))["player_state"] == "playing"
    assert (await fn(ctx, "pause"))["player_state"] == "paused"
    assert [event["action"] for event in fixture.events] == ["search", "play", "pause"]


@pytest.mark.asyncio
async def test_invalid_requests_never_reach_backend():
    runner = Mock()
    ctx = SimpleNamespace(
        session=SimpleNamespace(userdata={"_spotify_simulator": runner})
    )
    for action, query in [("execute", ""), ("search", " "), ("search", "x" * 501)]:
        assert "error" in await spotify.spotify_control._func(ctx, action, query)
    runner.assert_not_called()


@pytest.mark.asyncio
async def test_unset_real_session_and_timeout_do_not_claim_success(monkeypatch):
    monkeypatch.setattr(spotify.sys, "platform", "darwin")
    runner = Mock(side_effect=subprocess.TimeoutExpired("osascript", 8))
    monkeypatch.setattr(spotify, "_run_spotify", runner)
    result = await spotify.spotify_control._func(
        SimpleNamespace(session=AgentSession()), "play"
    )
    assert "error" in result and "success" not in result
    assert runner.call_count == 1


def test_search_encodes_query_as_one_url_argument(monkeypatch):
    runner = Mock(return_value=SimpleNamespace(returncode=0))
    monkeypatch.setattr(spotify.subprocess, "run", runner)
    result = spotify._run_spotify(
        {"action": "search", "query": 'Dave & "music" / live'}
    )
    assert result["success"]
    assert runner.call_args.args[0] == [
        "/usr/bin/open",
        "-a",
        "Spotify",
        "spotify:search:Dave%20%26%20%22music%22%20%2F%20live",
    ]
    assert "track" not in result


@pytest.mark.parametrize(
    "action,start,responds",
    [
        ("play", "paused", True),
        ("play", "playing", True),
        ("pause", "playing", True),
        ("play", "paused", False),
        ("pause", "playing", False),
    ],
)
def test_actual_spotify_script_verifies_state_without_toggle(action, start, responds):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node needed to exercise JXA API fixture")
    fixture = r"""
const assert=require('node:assert/strict');
let state=START, calls=[], pending=null;
function delay(seconds) {assert.equal(seconds,0.1);if(RESPONDS)state=pending;}
function Application(name) {assert.equal(name,'Spotify');return {
    play:()=>{calls.push('play');pending='playing';},
    pause:()=>{calls.push('pause');pending='paused';},
    playerState:()=>state,
    currentTrack:()=>({name:()=> 'Track',artist:()=> 'Artist'})
};}
const out=JSON.parse(run([JSON.stringify({action:ACTION})]));
assert.deepEqual(calls,[ACTION]);
assert.equal(out.player_state,state);
assert.equal(Boolean(out.success),RESPONDS);
assert.equal(Boolean(out.error),!RESPONDS);
"""
    prefix = (
        "const ACTION="
        + json.dumps(action)
        + ", START="
        + json.dumps(start)
        + ", RESPONDS="
        + json.dumps(responds)
        + ";\n"
    )
    result = subprocess.run(
        [node, "-e", prefix + spotify.SPOTIFY_JXA + fixture],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
