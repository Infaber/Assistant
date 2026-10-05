"""Direct local Spotify controls; playback does not require a UI tree scan."""

import asyncio
import json
import subprocess
import sys
from urllib.parse import quote

from livekit.agents import RunContext, function_tool

SPOTIFY_JXA = r"""
function run(argv) {
    const req=JSON.parse(argv[0]);
    const app=Application('Spotify');
    if(req.action==='play') app.play();
    else if(req.action==='pause') app.pause();
    else if(req.action==='next') app.nextTrack();
    else if(req.action==='previous') app.previousTrack();
    else if(req.action==='quit') {app.quit();return JSON.stringify({success:true,message:'Spotify quit requested.'});}
    else if(req.action!=='status') return JSON.stringify({error:'Unsupported Spotify action.'});
    let state=String(app.playerState());
    const expected=req.action==='play'?'playing':req.action==='pause'?'paused':null;
    // Spotify acknowledges transport commands before its player state updates.
    // Poll the state only; never resend or toggle the command.
    for(let attempt=0;expected && state!==expected && attempt<15;attempt++) {
        delay(0.1);state=String(app.playerState());
    }
    const result={player_state:state};
    try {const track=app.currentTrack();result.track=track.name();result.artist=track.artist();}catch(e){}
    if(req.action==='play' && result.player_state!=='playing') {
        result.error='Spotify did not start playing. Choose a track in Spotify and check you are signed in.';
    } else if(req.action==='pause' && result.player_state==='playing') {
        result.error='Spotify is still playing; pause was not confirmed.';
    } else result.success=true;
    return JSON.stringify(result);
}
"""


def _run_spotify(request: dict) -> dict:
    if request["action"] == "search":
        uri = "spotify:search:" + quote(request["query"], safe="")
        result = subprocess.run(
            ["/usr/bin/open", "-a", "Spotify", uri],
            capture_output=True,
            text=True,
            check=False,
            timeout=8,
        )
        if result.returncode:
            raise OSError(result.stderr)
        return {
            "success": True,
            "query": request["query"],
            "message": "Spotify search opened. Results have not been read and no track was selected.",
        }
    result = subprocess.run(
        ["osascript", "-l", "JavaScript", "-e", SPOTIFY_JXA, json.dumps(request)],
        capture_output=True,
        text=True,
        check=False,
        timeout=8,
    )
    if result.returncode:
        raise OSError(result.stderr)
    return json.loads(result.stdout)


@function_tool
async def spotify_control(context: RunContext, action: str, query: str = "") -> dict:
    """Control the local Spotify app directly: search, play, pause, next, previous,
    status or quit. Prefer this over mac_control for Spotify search and playback.
    search opens the requested query in Spotify via its URL handler, without
    Accessibility, UI inspection, or invented search results. play resumes the
    currently selected music; it does not select a song from search results. Play
    and pause return the actual player state. Do not claim a specific requested
    song is playing without checking the returned track/artist. Playback/status
    need macOS Automation access to Spotify for the app running Ariana. No Spotify
    API key is needed. Only act when requested; capability questions do not authorize
    playback. If no track is selected, explain that rather than inventing playback.
    """
    if action not in {"search", "play", "pause", "next", "previous", "status", "quit"}:
        return {"error": "Choose search, play, pause, next, previous, status or quit."}
    if action == "search" and (not query.strip() or len(query) > 500):
        return {"error": "Supply a Spotify search query containing 1-500 characters."}
    try:
        state = context.session.userdata
    except ValueError:
        state = {}
    backend = state.get("_spotify_simulator", _run_spotify)
    if backend is _run_spotify and sys.platform != "darwin":
        return {"error": "Local Spotify controls require Ariana to run on your Mac."}
    try:
        return await asyncio.to_thread(
            backend, {"action": action, "query": query.strip()}
        )
    except subprocess.TimeoutExpired:
        return {
            "error": "Spotify did not respond in time. Check its state before retrying; do not assume a connection was lost."
        }
    except (OSError, ValueError):
        return {
            "error": "Could not control Spotify. Check it is installed and allow the app running Ariana to control Spotify in macOS Privacy & Security > Automation."
        }
