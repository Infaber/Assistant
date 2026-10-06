# Ariana frontend

A futuristic command-centre frontend for the existing `ariana` LiveKit agent. It includes
voice and text input, a live transcript, audio visualization, microphone controls,
optional screen sharing, file/picture attachments, optional check-ins, transcript copying, and connection/error feedback.

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

## Command centre

The procedural particle globe reacts to Ariana’s actual audio level; connecting/thinking uses amber, and errors use red. The session panel displays real connection, microphone, screen-sharing and message state. Decorative rings are not performance gauges.

Capability shortcuts and quick-start buttons draft requests without sending them. Use the expand button for focus mode; `⌘K` on Mac or `Ctrl+K` returns to the command input. Animations respect reduced-motion settings, and the canvas stops drawing in background tabs. The UI works without external fonts, images or additional rendering libraries.

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
