import React from 'react';
import {createRoot} from 'react-dom/client';
import type {LocalParticipant} from 'livekit-client';
import VoiceControls from '../../components/voice-controls';

const calls: Record<string, unknown>[] = [];
Object.assign(window, {voiceCalls:calls});
let preferences: Record<string,string> = {google_voice:'Leda',warmth:'balanced'};
const participant = {performRpc: async ({payload}:{payload:string}) => {
  const request = JSON.parse(payload);
  calls.push(request);
  if (request.action === 'status') return JSON.stringify({
    preferences, voices:['Sulafat','Leda'], styles:{warmth:['low','balanced','high']},
    active_voice:'Sulafat', active_settings:{google_voice:'Sulafat',warmth:'balanced',turn_end_pause:'provider',local_speed:'1.0'},
    effective:{google_voice:preferences.google_voice || 'Sulafat',warmth:preferences.warmth || 'balanced',turn_end_pause:'provider',local_speed:'1.0'},
    configured_default_voice:'Sulafat',local_speeds:['0.8','1.0','1.2'],sample_text:'Neutral',samples:{neutral:'Neutral sample',serious:'Serious sample'},diagnostics:{e2e_latency:{samples:20,median_ms:400,p95_ms:900}},
  });
  if (request.action === 'save') {
    if ((window as unknown as {holdSave?:boolean}).holdSave) await new Promise<void>(resolve => Object.assign(window,{releaseSave:resolve}));
    preferences={...preferences,...request.values};
    for (const key of request.reset || []) delete preferences[key];
    return JSON.stringify({saved:true,preferences,applies:'next_connection'});
  }
  if (request.action === 'sample') return JSON.stringify({started:true,voice:'Sulafat'});
  return JSON.stringify({standby:true});
}} as unknown as LocalParticipant;

const root = createRoot(document.getElementById('root')!);
const render = (ready:boolean) => root.render(<VoiceControls participant={participant} destination={ready ? "fixture-agent" : undefined} ready={ready} busy={false} onStandby={()=>{}} wakeState="Standby" localTimings={()=>[]} />);
Object.assign(window,{disconnectVoiceFixture:()=>render(false)});
render(true);
