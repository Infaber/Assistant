# Ariana

Ariana is a personal voice assistant built with LiveKit Agents and Google Gemini,
with a Next.js frontend for voice and text conversations. Run the agent on your
Mac to use its Apple apps and desktop controls.

## What Ariana can do

- Talk through your microphone or the web frontend, with a live transcript.
- Search the web and browse public pages.
- Control your Home Assistant devices and get YR weather forecasts.
- Read Apple Calendar, Reminders, Mail, and Notes; create events, reminders, emails,
  and notes when requested and confirmed.
- Find and read notes, then append to or replace a selected note with confirmation.
- Open Mac apps, inspect accessible controls, click, type, use shortcuts, and scroll.
- Search Spotify and control playback directly, including Play, Pause, and skipping.
- Search or open websites directly in Safari, Chrome, Edge, Brave, or Firefox.
- Remember useful interests, routines and ongoing projects naturally across conversations; correct, forget or pause memory on request.
- Check integration configuration and save explicit browser/response preferences.

Notes writes first show a preview and wait for your natural approval. Editing
checks that the note has not changed since it was read. Mac controls use fresh
inspected targets and protect password fields. Ariana asks before sensitive
operations such as sending messages, deleting data, or changing account settings.

Spotify search opens results; it does not automatically select a song. Play
resumes the currently selected music and verifies the actual player state.
Custom app interfaces may not expose usable Accessibility controls.

## Project layout

| Folder | Purpose |
| --- | --- |
| `ariana/` | Python voice agent, integrations, tools, and backend tests |
| `frontend/` | Next.js voice/text interface and connection-token endpoint |
| `.github/workflows/` | Backend checks, frontend checks, and conversation simulations |

Both `ariana/` and `frontend/` are directly inside the repository root. The
frontend is **not** inside `ariana/`.

## Requirements

- Python and [uv](https://docs.astral.sh/uv/). CI uses Python 3.14.
- [LiveKit CLI](https://docs.livekit.io/reference/developer-tools/livekit-cli/).
- A LiveKit project and a Google/Gemini API key.
- Node.js 22 or newer for the frontend; CI uses Node.js 24.
- macOS for Apple apps, local Spotify, and desktop controls. The native desktop
  helper needs Apple Command Line Tools: `xcode-select --install` if missing.

A hosted Linux worker can run conversations and web tools, but cannot control
your Mac or its Apple apps remotely.

## First-time setup

Clone the repository and install the agent dependencies:

```sh
git clone https://github.com/Infaber/Assistant.git
cd Assistant/ariana
uv sync --locked
uv run playwright install webkit
cp -n .env.example .env.local
```

Edit `ariana/.env.local` with your own values:

```dotenv
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=your-livekit-api-key
LIVEKIT_API_SECRET=your-livekit-api-secret
GOOGLE_API_KEY=your-google-api-key
```

The Google key is separate from your LiveKit credentials. `GEMINI_API_KEY` is
accepted as an alternative to `GOOGLE_API_KEY`. Keep `.env.local` private; it is
ignored by Git. The copy command preserves an existing environment file.

## Talk in the terminal

From the repository root:

```sh
cd ariana
lk agent console
```

Allow microphone access if macOS asks. Stop with **Ctrl+C**. Restart after pulling
code changes or changing environment values, then start a new conversation.

## Use the web frontend

In the first terminal, run the agent from `ariana/` and keep it running:

```sh
lk agent dev
```

In a second terminal, start from the repository root:

```sh
cd frontend
npm ci
cp -n .env.example .env.local
```

Edit `frontend/.env.local` with the **same** `LIVEKIT_URL`, `LIVEKIT_API_KEY`, and
`LIVEKIT_API_SECRET` as the agent. The Google key belongs in the agent's file.
LiveKit keys stay on the frontend server; do not prefix them with `NEXT_PUBLIC_`.

```sh
npm run dev
```

Open the exact URL printed in the terminal, choose Voice or Text, and click
**Start conversation**. If port 3000 is occupied, Next.js may choose 3001 instead.
Both the Python agent and frontend must be running.

For production, configure `ARIANA_ACCESS_CODE` and HTTPS; see the
[frontend guide](frontend/README.md) for hosting and origin settings.

## Enable personal integrations

### Home Assistant

Add these values to `ariana/.env.local`:

```dotenv
HOME_ASSISTANT_URL=http://homeassistant.local:8123
HOME_ASSISTANT_TOKEN=your-long-lived-access-token
```

The URL must be reachable from the Mac running Ariana. If `homeassistant.local`
does not resolve, use your Home Assistant server's local IP address. Use your own
long-lived access token. Restart Ariana after saving the file.

### Apple apps, Mac controls, and Spotify

In **System Settings → Privacy & Security**, grant permission to the app that
actually launches Ariana, such as Terminal or VS Code:

- **Microphone** for voice conversations.
- **Automation** for the Apple apps you use and Spotify playback, when prompted.
- **Accessibility** for inspecting, clicking, typing, and desktop shortcuts.

Granting Codex permission does not automatically grant Terminal or VS Code the
same access. Unlock your Mac before using desktop controls. The Swift helper
compiles and caches itself on first use; this first compilation can take around
30 seconds. Later inspections reuse the executable.

No Spotify API key is needed. Spotify must be installed and signed in, with music
selected for Play to resume. Apple apps must have their accounts configured.

Try requests such as:

- “Search Spotify for Dave.”
- “Search Safari for LiveKit voice agents.”
- “Remember my preferred browser is Safari.”
- “Check your integrations.”
- “Play my music,” then “Pause it.”
- “Find my Ariana Ideas note.”
- “Add calendar integration to that note.” Approve the preview when asked.
- “What is on my calendar today?”
- “Turn on the living room lights.”

## Get the latest version in VS Code

From the repository root, with your own edits committed or safely stashed:

```sh
git fetch origin
git switch main
git pull --ff-only
```

Then refresh dependencies and restart Ariana:

```sh
cd ariana
uv sync --locked
lk agent console
```

If you use the frontend, run `npm ci` in `frontend/` after dependency changes and
restart its development server. Keep your existing `.env.local` files.

`main` contains the integrated project. Future feature work can use separate
branches and merge back into `main` after checks pass.

## Troubleshooting

| Problem | What to check |
| --- | --- |
| `cd frontend` fails | Run it from the repository root; from `ariana/`, use `cd ../frontend`. |
| `LIVEKIT_URL` is missing | Check `ariana/.env.local` and run the agent from `ariana/`. |
| Google API key is missing | Add `GOOGLE_API_KEY` or `GEMINI_API_KEY` to the agent's environment file. |
| Frontend connects but Ariana stays silent | Start `lk agent dev`; both projects must use the same LiveKit credentials. |
| “This request is not allowed” | Open the exact frontend URL printed by Next.js and check `APP_ORIGIN` if set. |
| Mac control is denied or the Mac is locked | Enable Accessibility for the launcher, unlock the Mac, and restart Ariana. |
| Spotify playback fails | Check Spotify is signed in, a track is selected, and Automation permission is enabled. |
| New tools do not appear | Stop the old console or worker and start a new session after updating. |

Never post API secrets or the contents of your environment files when sharing logs.

## Tests

Backend checks, from `ariana/`:

```sh
uv sync --locked --dev
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
```

Frontend checks, from `frontend/`:

```sh
npm run typecheck
npm test
npm run build
npx playwright install webkit
npm run test:browser
```

Conversation simulations use real inference and require configured credentials.
From `ariana/`:

```sh
lk agent simulate text --scenarios scenarios.yaml
lk agent simulate text --scenarios scenarios-integrations.yaml
lk agent simulate text --scenarios scenarios-mac.yaml
```

Personal-write and Mac/Spotify regression scenarios use isolated fixtures so they
do not manipulate your actual notes, desktop, or playback. Live testing is still
needed for microphone behavior and permissions on your own Mac.

See the [agent guide](ariana/README.md) and [frontend guide](frontend/README.md)
for detailed configuration, deployment, tests, and integration limitations.

### Personal memory

Ariana remembers useful, non-sensitive facts you tell her about yourself without a special save phrase. Try “I’m building a personal assistant called Ariana”, then ask about your project in a new conversation. Correct her naturally, ask “What do you remember about me?”, “Forget my side project”, or “Pause remembering things”. Resume with “You can remember things again”. “Don’t remember this” keeps a remark out of memory.

Memory stays on the machine running the Python agent, in `~/Library/Application Support/Ariana/memory.sqlite3` on macOS. It stores up to 100 short facts, with the 20 most recently updated supplied at startup; she can search the remaining facts. Fixed preferences stay in the existing preferences file. This is not a recording or complete conversation archive. Sensitive details, credentials and information read from apps/websites should not be saved. Moving the agent to another machine does not automatically move its memory.

The frontend uses a dark command-centre design with a procedural holographic globe, audio-reactive animation, capability shortcuts, focus mode, responsive layouts and reduced-motion support. Start it with `cd frontend` then `npm run dev`, and open the localhost address printed in the terminal. Start the Python agent separately for conversations.
