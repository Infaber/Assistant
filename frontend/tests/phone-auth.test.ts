import {test} from 'node:test';
import assert from 'node:assert/strict';
import {phonePairing} from '../lib/phone-auth';
import {createConnection} from '../lib/connection';
const env={NODE_ENV:'production',ARIANA_PHONE_ACCESS:'1',APP_ORIGIN:'https://mac.fixture.ts.net:8443',ARIANA_ACCESS_CODE:'fixture_'.repeat(7),LIVEKIT_URL:'wss://example.livekit.cloud',LIVEKIT_API_KEY:'test-key',LIVEKIT_API_SECRET:'test-secret-with-at-least-32-characters'};
const request=(method='POST',headers:Record<string,string>={})=>new Request('http://127.0.0.1:3031/api/phone-pairing',{method,headers:{origin:env.APP_ORIGIN,...headers}});
test('pairing requires private-server opt-in, exact origin and the QR key',()=>{
 assert.equal(phonePairing(request(),{...env,ARIANA_PHONE_ACCESS:''}).status,404);
 assert.equal(phonePairing(request(),env).status,401);
 assert.equal(phonePairing(request('POST',{authorization:'Bearer wrong'}),env).status,401);
 assert.equal(phonePairing(request('POST',{origin:'https://attacker.example',authorization:`Bearer ${env.ARIANA_ACCESS_CODE}`}),env).status,403);
});
test('pairing creates a persistent secure HttpOnly host cookie for Home Screen installation',async()=>{
 const response=phonePairing(request('POST',{authorization:`Bearer ${env.ARIANA_ACCESS_CODE}`}),env);
 assert.equal(response.status,200);const cookie=response.headers.get('set-cookie')!;
 for(const flag of ['__Host-ariana-phone=','Secure','HttpOnly','SameSite=Strict','Path=/','Max-Age=2592000'])assert.ok(cookie.includes(flag));
 assert.ok(!cookie.includes('Domain='));assert.ok(!(await response.text()).includes(env.ARIANA_ACCESS_CODE));assert.equal(response.headers.get('cache-control'),'no-store');
});
test('copied phone cookies authenticate sessions only on the explicitly enabled phone server',async()=>{
 const headers={origin:env.APP_ORIGIN,cookie:`__Host-ariana-phone=${env.ARIANA_ACCESS_CODE}`};
 assert.equal((await createConnection(request('POST',headers),env)).status,201);
 assert.equal((await createConnection(request('POST',{...headers,authorization:'Bearer wrong'}),env)).status,401);
 assert.equal((await createConnection(request('POST',headers),{...env,ARIANA_PHONE_ACCESS:''})).status,401);
 assert.equal((await createConnection(request('POST',headers),{...env,ARIANA_ACCESS_CODE:'rotated-key'})).status,401);
 assert.equal((await createConnection(request('POST',{...headers,origin:'https://attacker.example'}),env)).status,403);
});
test('forgetting phone pairing clears its cookie while preserving origin checks',()=>{
 assert.equal(phonePairing(request('DELETE',{origin:'https://attacker.example'}),env).status,403);
 const response=phonePairing(request('DELETE'),env);assert.equal(response.status,200);assert.ok(response.headers.get('set-cookie')?.includes('Max-Age=0'));
});
