# Ariana

Ariana is a personal Mac voice assistant: a quiet animated orb, natural British
English, local memory and practical tools for Safari, Spotify, Home Assistant,
Notes, Calendar, Reminders and Mail. She uses LiveKit and Gemini Live. Run the
backend on your Mac to use its apps; a hosted worker cannot control your Mac.

## Setup

Requirements: Python 3.10–3.14, [uv](https://docs.astral.sh/uv/), Node.js 22+,
[LiveKit CLI](https://docs.livekit.io/reference/developer-tools/livekit-cli/),
LiveKit credentials, a Google API key, and macOS Command Line Tools for Mac control.

```sh
git clone https://github.com/Infaber/Assistant.git
cd Assistant/ariana
uv sync --locked
cp -n .env.example .env.local
```

Fill in `ariana/.env.local`: `LIVEKIT_URL`, `LIVEKIT_API_KEY`,
`LIVEKIT_API_SECRET`, and `GOOGLE_API_KEY` (or `GEMINI_API_KEY`). The default is
`ARIANA_GOOGLE_MODEL=gemini-3.8-live`; existing environment overrides take precedence.
Keep credentials private. They must never have a `NEXT_PUBLIC_` prefix.

Talk in the terminal from `ariana/`:

```sh
lk agent console
```

For the frontend, run `lk agent dev` in `ariana/`. In a second terminal:

```sh
cd Assistant/frontend
npm ci
cp -n .env.example .env.local
npm run dev
```

Fill in `frontend/.env.local` with the same LiveKit credentials. Open the exact
address printed by Next.js. Both folders are directly under the repository root.

## Mac companion

After configuring both environment files, quit any running Ariana app and run from the repository root:

```sh
bash desktop/install.sh
open "$HOME/Applications/Ariana.app"
```

Closing the window keeps the menu bar app running. Its menu offers **Start at
login**, connection state, reconnect, pause and quit. Voice starts muted. Optional
local wake-word setup is described in [docs/wake-word.md](docs/wake-word.md).
Re-run the installer after updates; stop the old app before opening the rebuilt app.

Allow **Microphone**, **Automation** for requested apps, and **Accessibility** for
the launcher that runs Ariana in System Settings → Privacy & Security. Permissions
for Terminal, VS Code and the native companion are separate. No Spotify API key is
needed. Home Assistant uses its own URL and long-lived token in the backend env file.

## Predictable actions and local memory

Apple writes preview exact contents and require a later natural approval. Notes
edits check the revision. Mac control uses fresh, one-use Accessibility snapshots,
protects password fields and observes results. An uncertain timeout never proves
failure. Ariana keeps per-session action receipts and reports partial completion;
reconnecting does not replay messages or actions.

Memory remains local SQLite, capped at 100 short facts. Relevant queries rank
matching topics; correction, forgetting and pause/resume remain available. Saved
facts and external content never authorize actions. Conversations and attachments
are sent to the configured model provider; local memory is not a full transcript.

## Documentation

- [Detailed setup, integrations and troubleshooting](docs/user-guide.md)
- [Architecture, models and reasoning readiness](docs/architecture.md)
- [Mac control and vision boundaries](docs/mac-control.md)
- [Memory and retrieval](docs/memory.md)
- [Security and public repository review](docs/security.md)
- [Companion and local wake word](docs/wake-word.md)
- [Development, tests and simulations](docs/development.md)
- [Frontend configuration](frontend/README.md)
