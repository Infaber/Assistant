# Ariana frontend

A minimal interface centered on Ariana: one animated blue orb on a pure black
background. Six swappable inner visuals, real microphone/speech levels, optional
captions and brief spoken feedback during longer thinking turns. File sharing,
conversation history, screen sharing and background check-ins remain available.

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
lk agent dev
```

The agent needs its LiveKit credentials and Google/Gemini API key as described in
the agent's README. Its registered agent name must be `ariana`; the frontend
dispatches this name automatically into a new room on each connection.

Then, from `frontend/`:

```sh
npm run dev
```

Open <http://127.0.0.1:3000>. Tap the orb to start a voice conversation. The tiny
microphone button toggles voice input; text connections also play spoken replies.
Tap the orb while connected, type a character, or press `⌘K` / `Ctrl+K` to reveal
the message pill. Escape hides it. Sending hides it after acceptance. Paste or
drop files anywhere, or use the paperclip in the pill.

The settings icon opens appearance, optional captions, spoken thinking feedback,
connection controls, screen sharing, check-ins, and conversation/activity history.
Use **Connect with text** to start with the microphone off. **End session** stops
local media. Screen sharing asks which screen/window/tab to share, without system
audio. If an access code is configured, save it in Settings before connecting.
The code stays in page memory; LiveKit credentials belong on the server.

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
without LiveKit or model credentials. Browser tests cover orb preferences, keyboard input, attachments, audio assets,
access-code submission, error recovery, and cancellation. Token tests verify
authentication, origin checks, room isolation, dispatch, and signed token grants.

For a live check, start the Python worker, connect in voice mode, ask a question,
interrupt a reply, mute/unmute, send text, share/stop sharing a screen, and end the
session. Then reconnect to confirm a new conversation starts. Automated checks
do not validate live audio, model responses, or screen interpretation.

Built with [LiveKit's React frontend APIs](https://docs.livekit.io/frontends/)
and [server-issued session tokens](https://docs.livekit.io/frontends/build/authentication/endpoint/).

## Orb and spoken feedback

Choose flowing mesh, glass bubble, crystal burst, shard vortex, wireframe globe,
or particle swirl in Settings. Appearance, captions and feedback preferences stay
in local browser storage. Captions default off. The canvas uses procedural Canvas2D
with a capped pixel ratio; it pauses in hidden tabs and respects reduced motion.
The visible orb is approximately 55% of the shorter viewport dimension.

Idle slowly breathes and rotates. Listening tightens the ring and reacts to the
microphone; thinking adds turbulence; speaking follows Ariana's output volume.
State changes ease over several hundred milliseconds, and style changes crossfade.

After 1.8 seconds of actual thinking, a short prerecorded acknowledgment in Ariana's
Achernar voice plays. A second cue can play after 15 seconds. Cues stop when Ariana
answers, you begin speaking, or feedback is disabled; a cooldown prevents repeated
acknowledgments between quick tool calls. They are generic status cues, not narrated
reasoning. Browser autoplay permissions apply. The voice assets are bundled locally,
so playback adds no provider request. To regenerate them with your existing Google
key: `cd ariana && uv run python ../frontend/scripts/generate-feedback.py`.

## Sharing files and optional check-ins

Paste clipboard pictures/files, drag files onto the composer, or use the paperclip.
Preview attachments before sending. PNG/JPEG/WebP/GIF, PDF, DOCX and UTF-8 text/code
are supported, up to three files and 10 MB per file. The agent confirms acceptance;
retrying an interrupted receipt checks the same submission rather than duplicating
it. Scanned PDFs need screenshots, and incomplete extraction is labelled.

Check-ins are off by default in a browser. Connect, turn on **Check-ins**, choose an
interval and quiet hours, and keep the page open. Ariana starts a conversation
after silence, avoids speaking over you, and waits for a reply before another
check-in. For background operation with the window closed, install the separate
[Mac companion](../desktop/README.md). The companion auto-connects in text mode,
keeps the microphone off and defaults to check-ins on.

For tests against an existing preview on another port:

```sh
ARIANA_TEST_URL=http://127.0.0.1:3020 npm run test:browser
```

The server-only `LIVEKIT_AGENT_NAME` option overrides the default `ariana`
dispatch name; the companion uses `ariana-desktop` to own its worker separately.
