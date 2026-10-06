import { createHash, randomUUID, timingSafeEqual } from 'node:crypto';
import { AccessToken, RoomAgentDispatch, RoomConfiguration, TrackSource } from 'livekit-server-sdk';

type Environment = Record<string, string | undefined>;
const headers = { 'Cache-Control': 'no-store' };
const loopbackHosts = new Set(['localhost', '127.0.0.1', '[::1]']);

function allowedOrigin(request: Request, env: Environment) {
  const origin = request.headers.get('origin');
  const expected = env.APP_ORIGIN || new URL(request.url).origin;
  if (!origin) return false;
  if (origin === expected) return true;
  // Next dev can reconstruct request.url with localhost even when the browser
  // uses 127.0.0.1. Allow loopback aliases only in development, on the same port.
  if (env.APP_ORIGIN || env.NODE_ENV !== 'development') return false;
  try {
    const actual = new URL(origin);
    const target = new URL(expected);
    return actual.origin === origin && loopbackHosts.has(actual.hostname)
      && loopbackHosts.has(target.hostname) && actual.protocol === target.protocol
      && actual.port === target.port;
  } catch { return false; }
}

function error(message: string, status: number) {
  return Response.json({ error: message }, { status, headers });
}

// A personal frontend uses a shared access code. A multi-user deployment should
// replace this gate with its own authenticated user/session check.
export async function createConnection(request: Request, env: Environment = process.env) {
  if (!allowedOrigin(request, env)) return error('This request is not allowed.', 403);

  const code = env.ARIANA_ACCESS_CODE?.trim();
  const local = loopbackHosts.has(new URL(request.url).hostname);
  if (!code && (env.NODE_ENV === 'production' || !local)) {
    return error('Set ARIANA_ACCESS_CODE on the frontend server before connecting.', 503);
  }
  if (code) {
    const supplied = request.headers.get('authorization')?.replace(/^Bearer /, '') || '';
    const digest = (value: string) => createHash('sha256').update(value).digest();
    if (!timingSafeEqual(digest(supplied), digest(code))) {
      return error('Enter the correct access code in Connection settings.', 401);
    }
  }

  const serverUrl = env.LIVEKIT_URL?.trim();
  const apiKey = env.LIVEKIT_API_KEY?.trim();
  const apiSecret = env.LIVEKIT_API_SECRET?.trim();
  if (!serverUrl || !apiKey || !apiSecret) {
    return error('Add your LiveKit credentials to frontend/.env.local, then restart the frontend.', 503);
  }
  try {
    const url = new URL(serverUrl);
    if (!['wss:', 'ws:'].includes(url.protocol)) throw new Error('Invalid protocol');
  } catch {
    return error('LIVEKIT_URL must be a valid ws:// or wss:// address.', 503);
  }

  // Room, identity, and dispatch are server-owned: callers cannot join another
  // user's room or select a different agent by changing a request payload.
  const roomName = `ariana-${randomUUID()}`;
  const token = new AccessToken(apiKey, apiSecret, {
    identity: `guest-${randomUUID()}`, name: 'You', ttl: '5m',
  });
  token.addGrant({
    room: roomName, roomJoin: true, canPublish: true, canSubscribe: true,
    canPublishData: true,
    canPublishSources: [TrackSource.MICROPHONE, TrackSource.SCREEN_SHARE],
  });
  token.roomConfig = new RoomConfiguration({
    agents: [new RoomAgentDispatch({ agentName: env.LIVEKIT_AGENT_NAME?.trim() || 'ariana' })],
    emptyTimeout: 60, departureTimeout: 20, maxParticipants: 2,
  });
  return Response.json({ server_url: serverUrl, participant_token: await token.toJwt() }, {
    status: 201, headers,
  });
}
