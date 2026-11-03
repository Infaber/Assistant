import React, {useState} from 'react';
import {createRoot} from 'react-dom/client';
import SessionPanel from '../../components/session-panel';
import type {LocalParticipant} from 'livekit-client';
const fixture = window as unknown as {release?:()=>void; calls:number};
fixture.calls=0;
const participant = {performRpc:async()=>{fixture.calls++;await new Promise<void>(resolve=>{fixture.release=resolve;});return JSON.stringify({active_voice:'Sulafat',response_times_ms:[900,1400,1000,1100]});}} as unknown as LocalParticipant;
function Fixture(){const [ready,setReady]=useState(true);return <><button onClick={()=>setReady(false)}>Disconnect fixture</button><SessionPanel participant={participant} destination="fixture" ready={ready} mode="normal" microphone={false} wakeState="Standby">Engine controls</SessionPanel></>;}
createRoot(document.getElementById('root')!).render(<Fixture/>);
