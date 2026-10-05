import assert from 'node:assert/strict';
import { test } from 'node:test';
import { TokenVerifier } from 'livekit-server-sdk';
import { createConnection } from '../lib/connection';

const env = { NODE_ENV: 'development', LIVEKIT_URL: 'wss://example.livekit.cloud', LIVEKIT_API_KEY: 'test-key', LIVEKIT_API_SECRET: 'test-secret-with-at-least-32-characters' };
function request(headers: Record<string, string> = {}, body?: string) {
  return new Request('http://localhost:3000/api/connection', { method: 'POST', headers: { origin: 'http://localhost:3000', ...headers }, body });
}

test('rejects missing or foreign origins', async () => {
  for (const origin of ['', 'https://attacker.example']) {
    assert.equal((await createConnection(request({ origin }), env)).status, 403);
  }
});

test('production and non-local deployments require an access code', async () => {
  assert.equal((await createConnection(request(), { ...env, NODE_ENV: 'production' })).status, 503);
  const remote = new Request('https://assistant.example/api/connection', { method: 'POST', headers: { origin: 'https://assistant.example' } });
  assert.equal((await createConnection(remote, env)).status, 503);
});

test('checks the access code before issuing a token', async () => {
  const protectedEnv = { ...env, NODE_ENV: 'production', ARIANA_ACCESS_CODE: 'private-code' };
  for (const authorization of ['', 'Bearer wrong-code', 'Basic private-code']) {
    assert.equal((await createConnection(request({ authorization }), protectedEnv)).status, 401);
  }
  assert.equal((await createConnection(request({ authorization: 'Bearer private-code' }), protectedEnv)).status, 201);
});

test('reports missing credentials and invalid LiveKit addresses without secrets', async () => {
  for (const overrides of [{ LIVEKIT_API_SECRET: '' }, { LIVEKIT_URL: 'https://example.com' }, { LIVEKIT_URL: 'invalid' }]) {
    const response = await createConnection(request(), { ...env, ...overrides });
    assert.equal(response.status, 503);
    assert.ok(!(await response.text()).includes(env.LIVEKIT_API_SECRET));
  }
});

test('issues signed short-lived tokens scoped to a fresh room and the Ariana agent', async () => {
  const verifier = new TokenVerifier(env.LIVEKIT_API_KEY, env.LIVEKIT_API_SECRET);
  const rooms = new Set();
  const identities = new Set();
  for (let i = 0; i < 2; i++) {
    const response = await createConnection(request({}, JSON.stringify({ room: 'someone-elses-room', agentName: 'other-agent' })), env);
    assert.equal(response.status, 201);
    assert.equal(response.headers.get('cache-control'), 'no-store');
    const data = await response.json();
    assert.equal(data.server_url, env.LIVEKIT_URL);
    assert.deepEqual(Object.keys(data).sort(), ['participant_token', 'server_url']);
    const token = await verifier.verify(data.participant_token);
    assert.match(token.video!.room!, /^ariana-/);
    assert.equal(token.video?.roomJoin, true);
    assert.equal(token.video?.roomAdmin, undefined);
    assert.deepEqual(token.video?.canPublishSources, ['microphone', 'screen_share']);
    assert.equal(token.roomConfig?.agents?.[0].agentName, 'ariana');
    assert.equal(token.roomConfig?.maxParticipants, 2);
    assert.ok(token.exp! - token.nbf! <= 300);
    rooms.add(token.video?.room);
    identities.add(token.sub);
  }
  assert.equal(rooms.size, 2);
  assert.equal(identities.size, 2);
});

test('honors the configured public origin behind a reverse proxy', async () => {
  const response = await createConnection(request({ origin: 'https://ariana.example.com' }), { ...env, APP_ORIGIN: 'https://ariana.example.com' });
  assert.equal(response.status, 201);
});
