import json
import shutil
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from livekit.agents import AgentSession

import mac_tools as mac
from mac_simulation import DesktopFixture


def context():
    desktop = DesktopFixture()
    ctx = SimpleNamespace(
        session=SimpleNamespace(userdata={"_mac_simulator": desktop.run})
    )
    return ctx, desktop


@pytest.mark.asyncio
async def test_real_sdk_unset_state_is_initialized():
    session = AgentSession()
    assert mac._state(SimpleNamespace(session=session)) == {}
    assert session.userdata == {}


@pytest.mark.asyncio
async def test_full_search_uses_fresh_targets_and_verifies_result():
    ctx, desktop = context()
    fn = mac.mac_control._func
    await fn(ctx, "open", app_name="Spotify")
    view = await fn(ctx, "inspect")
    assert "path" not in view["elements"][0]
    assert "signature" not in view["elements"][0]
    assert (await fn(ctx, "click", snapshot_id=view["snapshot_id"], element_id="e0"))[
        "success"
    ]
    assert "error" in await fn(
        ctx, "type", snapshot_id=view["snapshot_id"], element_id="e1", text="wrong"
    )
    view = await fn(ctx, "inspect")
    assert (
        await fn(
            ctx,
            "type",
            snapshot_id=view["snapshot_id"],
            element_id="e1",
            text="Daft Punk",
        )
    )["success"]
    view = await fn(ctx, "inspect")
    assert (await fn(ctx, "shortcut", snapshot_id=view["snapshot_id"], key="return"))[
        "success"
    ]
    result = await fn(ctx, "inspect")
    assert desktop.app == "Spotify"
    assert desktop.query == "Daft Punk"
    assert result["elements"][2]["value"] == "Daft Punk"


@pytest.mark.asyncio
async def test_snapshot_mismatch_expiry_and_open_invalidate(monkeypatch):
    ctx, desktop = context()
    fn = mac.mac_control._func
    view = await fn(ctx, "inspect")
    assert "error" in await fn(ctx, "click", snapshot_id="invented", element_id="e0")
    stamp = ctx.session.userdata["mac_snapshot"]["time"]
    monkeypatch.setattr(mac.time, "monotonic", lambda: stamp + 61)
    assert "error" in await fn(
        ctx, "click", snapshot_id=view["snapshot_id"], element_id="e0"
    )
    await fn(ctx, "open", app_name="Spotify")
    assert "mac_snapshot" not in ctx.session.userdata
    assert [e["action"] for e in desktop.events] == ["inspect", "open"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "action,kwargs",
    [
        ("click", {"element_id": "missing"}),
        ("type", {"element_id": "e1", "text": ""}),
        ("shortcut", {"key": "arbitrary command"}),
        ("shortcut", {"key": "a", "modifiers": ["bad"]}),
        ("scroll", {"direction": "sideways"}),
        ("scroll", {"amount": 11}),
    ],
)
async def test_invalid_actions_do_not_reach_desktop(action, kwargs):
    ctx, desktop = context()
    view = await mac.mac_control._func(ctx, "inspect")
    assert "error" in await mac.mac_control._func(
        ctx, action, snapshot_id=view["snapshot_id"], **kwargs
    )
    assert len(desktop.events) == 1


@pytest.mark.asyncio
async def test_mac_only_and_permission_failure(monkeypatch):
    monkeypatch.setattr(mac.sys, "platform", "linux")
    assert "Mac" in (await mac._request({}, {"action": "inspect"}))["error"]
    monkeypatch.setattr(mac.sys, "platform", "darwin")
    monkeypatch.setattr(mac, "_run_mac", Mock(side_effect=OSError("denied")))
    assert "Accessibility" in (await mac._request({}, {"action": "inspect"}))["error"]


@pytest.mark.asyncio
async def test_timeout_consumes_snapshot_without_replay():
    ctx, _ = context()
    view = await mac.mac_control._func(ctx, "inspect")

    def timed_out(req):
        raise subprocess.TimeoutExpired("osascript", 30)

    ctx.session.userdata["_mac_simulator"] = timed_out
    result = await mac.mac_control._func(
        ctx, "click", snapshot_id=view["snapshot_id"], element_id="e0"
    )
    assert "may have occurred" in result["error"]
    assert "mac_snapshot" not in ctx.session.userdata


@pytest.mark.parametrize(
    "case",
    [
        "inspect",
        "click",
        "type",
        "focus_changed",
        "target_changed",
        "secure",
        "shortcut",
        "scroll",
    ],
)
def test_actual_jxa_against_fake_accessibility_api(case):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is needed for the fake JavaScript scripting API")
    fixture = r"""
const assert=require('node:assert/strict');
let effects=[];
let focus=false;
const field={role:()=> 'AXTextField',subrole:()=> CASE==='secure'?'AXSecureTextField':'',
    name:()=> 'Search',description:()=> 'Search',enabled:()=> true,
    position:()=> [10,20],size:()=> [100,30],value:()=> 'PRIVATE SECRET',uiElements:()=>[]};
Object.defineProperty(field,'focused',{get:()=>()=>focus,set:v=>{focus=v;}});
const win={name:()=> 'Music',role:()=> 'AXWindow',subrole:()=>'',description:()=> 'Music',
    enabled:()=>true,position:()=>[0,0],size:()=>[800,600],uiElements:()=>[field],value:()=>''};
const proc={name:()=> 'Spotify',unixId:()=> CASE==='focus_changed'?2:1,windows:()=>[win],menuBars:()=>[]};
const se={applicationProcesses:{whose:()=>()=>[proc]},click:n=>{assert.equal(n,field);effects.push('click');},
    keystroke:(text,options)=>effects.push(['type',text,options]),keyCode:(code,options)=>effects.push(['key',code,options])};
function Application(name){assert.equal(name,'System Events');return se;}
const signature=JSON.stringify(['AXTextField',CASE==='secure'?'AXSecureTextField':'','Search','Search',[10,20],[100,30]]);
let req={action:CASE==='inspect'||CASE==='secure'?'inspect':CASE==='type'?'type':CASE==='shortcut'?'shortcut':CASE==='scroll'?'scroll':'click',
    pid:1,window:'Music',target:{path:['window',0,0],signature:CASE==='target_changed'?'old':signature},text:'Daft Punk',
    key:'l',key_code:null,modifiers:['command'],direction:'down',amount:2};
if(req.action==='shortcut'||req.action==='scroll') delete req.target;
const out=JSON.parse(run([JSON.stringify(req)]));
if(CASE==='secure') {assert.ok(!JSON.stringify(out).includes('PRIVATE SECRET'));assert.equal(out.elements[1].secure,true);}
else if(CASE==='inspect') {assert.equal(out.elements[1].name,'Search');assert.deepEqual(out.elements[1].path,['window',0,0]);}
else if(CASE==='focus_changed'||CASE==='target_changed') {assert.ok(out.error);assert.equal(effects.length,0);}
else if(CASE==='type') {assert.equal(focus,true);assert.equal(effects[0][1],'Daft Punk');}
else if(CASE==='click') assert.deepEqual(effects,['click']);
else if(CASE==='shortcut') assert.deepEqual(effects[0],['type','l',{using:['command down']}]);
else if(CASE==='scroll') {assert.equal(effects.length,2);assert.equal(effects[0][1],121);}
"""
    result = subprocess.run(
        [node, "-e", "const CASE=" + json.dumps(case) + ";\n" + mac.MAC_JXA + fixture],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
