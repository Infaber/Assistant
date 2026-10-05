# Ariana frontend

A responsive Next.js frontend for the existing `ariana` LiveKit agent. It includes
voice and text input, a live transcript, audio visualization, microphone controls,
optional screen sharing, transcript copying, and connection/error feedback.

## Run locally

Install Node.js 22 or newer (CI uses Node 24). From the repository root:

```sh
cd frontend
npm ci
cp .env.example .env.local
```

Edit `frontend/.env.local` and fill in `LIVEKIT_URL`, `LIVEKIT_API_KEY`, and
`LIVEKIT_API_SECRET` from the **same LiveKit project as your Python agent**.
These variables are server-only. Never prefix them with `NEXT_PUBLIC_`.

In another terminal, start the existing agent using its own environment file:

```sh
cd ariana
uv sync
uv run playwright install webkit
uv run src/agent.py dev
```

The agent needs its LiveKit credentials and Google/Gemini API key as described in
the agent's README. Its registered agent name must be `ariana`; the frontend
dispatches this name automatically into a new room on each connection.

Then, from `frontend/`:

```sh
npm run dev
```

Open <http://127.0.0.1:3000>. Choose **Voice** or **Text**, then **Start conversation**.
Voice mode requests microphone permission. Text mode starts without a microphone
and still plays Ariana's spoken replies. Suggestion buttons draft a message; press
Send after connecting. Screen sharing asks the browser which screen/window/tab
to share; it does not share system audio. **End session** stops local media.

If `ARIANA_ACCESS_CODE` is configured, enter it using the settings icon in the
left sidebar before connecting. The page keeps it only in memory. No LiveKit
credentials should be entered into the UI.

You can inspect the design without credentials. Starting a conversation will show
a setup error until credentials and the agent are ready. There are no simulated
assistant responses.

## Deployment

Use a Node-compatible Next.js host; the token endpoint requires a server and cannot
be deployed as a static export. Configure the three LiveKit variables plus a strong
`ARIANA_ACCESS_CODE` in the host's server environment. Production refuses to issue
tokens without an access code. Use HTTPS for microphone and screen sharing.

```sh
npm ci
npm run build
npm run start -- --hostname 0.0.0.0
```

Set `APP_ORIGIN` to the exact public origin (for example,
`https://ariana.example.com`, without a trailing slash) if a reverse proxy rewrites
the incoming origin. The Python worker runs separately and must remain available.

This access-code gate is for a personal workspace. For a public multi-user app,
add your identity provider and per-user rate limits before granting session tokens.
Tokens expire after five minutes, can join only their unique room, and dispatch
only Ariana. Conversations are held in browser memory, with an explicit copy
button; refreshing clears the displayed transcript. LiveKit/model providers may
process session data according to your account settings.

## Checks

```sh
npm run typecheck
npm test
npm run build
npx playwright install webkit
npm run test:browser
```

On Linux, use `npx playwright install --with-deps webkit`. CI runs all these checks
without LiveKit or model credentials. Browser tests cover layout, draft prompts,
access-code submission, error recovery, and cancellation. Token tests verify
authentication, origin checks, room isolation, dispatch, and signed token grants.

For a live check, start the Python worker, connect in voice mode, ask a question,
interrupt a reply, mute/unmute, send text, share/stop sharing a screen, and end the
session. Then reconnect to confirm a new conversation starts. Automated checks
do not validate live audio, model responses, or screen interpretation.

Built with [LiveKit's React frontend APIs](https://docs.livekit.io/frontends/)
and [server-issued session tokens](https://docs.livekit.io/frontends/build/authentication/endpoint/).
