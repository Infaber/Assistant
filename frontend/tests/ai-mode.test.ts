import assert from 'node:assert/strict';
import {test} from 'node:test';
import {TokenVerifier} from 'livekit-server-sdk';
import {parseModeStatus} from '../lib/ai-mode';
import {createConnection} from '../lib/connection';
const env={NODE_ENV:'development',LIVEKIT_URL:'wss://example.livekit.cloud',LIVEKIT_API_KEY:'key',LIVEKIT_API_SECRET:'test-secret-with-at-least-32-characters'};
const request=(mode:string)=>new Request('http://localhost:3000/api/connection',{method:'POST',headers:{origin:'http://localhost:3000','Content-Type':'application/json'},body:JSON.stringify({mode})});
test('mode state requires an explicit backend ready response',()=>{
 assert.equal(parseModeStatus({mode:'local',state:'ready'}),null);
 assert.equal(parseModeStatus({mode:'secret-hosted',state:'ready',model:'x',error:''}),null);
 assert.equal(parseModeStatus({mode:'local',state:'loading',model:'qwen',error:''})?.state,'loading');
});
test('authenticated local selection is encoded in server-owned dispatch metadata',async()=>{
 const result=await createConnection(request('local'),env,async()=>{});
 assert.equal(result.status,201);
 const {participant_token}=await result.json();
 const token=await new TokenVerifier(env.LIVEKIT_API_KEY,env.LIVEKIT_API_SECRET).verify(participant_token);
 assert.deepEqual(JSON.parse(token.roomConfig!.agents![0].metadata),{mode:'local'});
});
test('unavailable local model returns error without issuing a cloud token',async()=>{
 const response=await createConnection(request('local'),env,async()=>{throw new Error('Local model unavailable');});
 assert.equal(response.status,503);
 assert.equal((await response.json()).participant_token,undefined);
});
test('unknown mode is rejected',async()=>{
 assert.equal((await createConnection(request('remote-secret'),env)).status,400);
});
