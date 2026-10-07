# Ariana

Ariana is a personal voice assistant built with LiveKit Agents and Google Gemini,
with a Next.js frontend for voice and text conversations. Run the agent on your
Mac to use its Apple apps and desktop controls.

## What Ariana can do

- Talk through your microphone or the web frontend, with a live transcript.
- Paste, drop or attach pictures, PDFs, Word documents and text/code files.
- Run a Mac menu bar companion that starts its own services and keeps Ariana connected when its window is closed.
- Let Ariana initiate gentle check-ins, with configurable intervals and quiet hours.
- Search, open, and read pages in your real Safari browser.
- Control your Home Assistant devices and get YR weather forecasts.
- Read Apple Calendar, Reminders, Mail, and Notes; create events, reminders, emails,
  and notes when requested and confirmed.
- Find and read notes, then append to or replace a selected note with confirmation.
- Open Mac apps, inspect accessible controls, click, right-click, double-click, type, use shortcuts, and scroll.
- Search Spotify and control playback directly, including Play, Pause, and skipping.
- Find and select existing Safari tabs when requested; follow links from page content.
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
| `desktop/` | Native macOS menu bar companion and installer |
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

A hosted Linux worker can run conversations, Home Assistant and weather tools, but
Safari browsing and Apple app controls require the agent to run on your Mac.

## First-time setup

Clone the repository and install the agent dependencies:

```sh
git clone https://github.com/Infaber/Assistant.git
cd Assistant/ariana
uv sync --locked
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
[frontend guide](../frontend/README.md) for hosting and origin settings.

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

See the [agent guide](../ariana/README.md) and [frontend guide](../frontend/README.md)
for detailed configuration, deployment, tests, and integration limitations.

### Personal memory

Ariana remembers useful, non-sensitive facts you tell her about yourself without a special save phrase. Try “I’m building a personal assistant called Ariana”, then ask about your project in a new conversation. Correct her naturally, ask “What do you remember about me?”, “Forget my side project”, or “Pause remembering things”. Resume with “You can remember things again”. “Don’t remember this” keeps a remark out of memory.

Memory stays on the machine running the Python agent, in `~/Library/Application Support/Ariana/memory.sqlite3` on macOS. It stores up to 100 short facts, with 20 recent facts and a topic index supplied at startup. Relevant queries rank local facts and exclude unmatched topics. Fixed preferences stay in the existing preferences file. This is not a recording or complete conversation archive. Sensitive details, credentials and information read from apps/websites should not be saved. Moving the agent to another machine does not automatically move its memory.

The frontend centers a single animated blue orb on pure black, with six inner styles, microphone/speech reactions, optional captions and spoken thinking feedback. Tap the orb to connect; type or press ⌘K for the message pill. Settings holds conversation history, file sharing guidance, screen sharing and check-ins. It supports mobile layouts and reduced motion. Start it with `cd frontend` then `npm run dev`, and open the localhost address printed in the terminal. Start the Python agent separately for conversations.

## Safari browsing and verified Mac actions

Ariana uses **Safari only** for web browsing. The Python Playwright browser and
separate search provider have been removed. Existing `ARIANA_BROWSER_*` and
`ARIANA_SEARCH_TIMEOUT_SECONDS` settings are no longer used. Saved browser
preferences do not override Safari-only operation.

Allow Safari under **System Settings → Privacy & Security → Automation** for the
app running Ariana. Page reads first try a fixed, read-only Safari script and then
macOS Accessibility. Accessibility reads can omit custom/offscreen content and are
labeled accordingly. For fuller page text, Safari's **Develop → Allow JavaScript
from Apple Events** is optional. Ariana cannot bypass a site's login or CAPTCHA.
New searches/pages open in a separate Safari window; existing tabs are read only
on request. Local HTTP(S) pages are supported when requested. Page contents never
authorize actions.

Mac input uses inspected controls, not guessed screen coordinates. Each input
consumes its snapshot and includes a fresh observation of the same app. Text is
read back when the editable field exposes its value and selection. `verified`
applies to that operation, not an entire multi-step task. Timeouts remain uncertain:
Ariana checks the result rather than automatically repeating a click or write.
Right-click and double-click also require an inspected, unobstructed target.

The frontend's **Settings → Conversation & activity** view shows live action progress, approval requests,
verified results and failures. It retains at most 40 events for the current
connection, in memory only; it does not include tool arguments, page text, notes,
or provider error payloads. Plain-text results from older integrations are marked
“Result returned”, not “Verified”. A disconnected in-flight action becomes
“Needs checking”. Use the conversation for Ariana's explanation.

Provider quota/authentication failures appear with actionable messages. By default,
reconnect explicitly after resolving the problem. Advanced users may set
`ARIANA_FALLBACK_GOOGLE_MODEL` to a compatible Gemini Live model available to their
account: Ariana attempts that backup once per session after a terminal model
failure, carrying conversation context. It does not resubmit the last user turn.
A backup using the same Google project may share the same quota; it is not a quota
workaround. Leave the setting empty unless you have tested that model.

Frontend Playwright remains a **development test dependency** for WebKit UI
checks; Ariana never uses it to browse.

## Attachments

Use the paperclip beside the message field, drag files onto the composer, or paste
pictures/files from the clipboard. Review the preview, optionally type a question,
and press Send. You can stage files before connecting. Ariana accepts up to three
files per message, 10 MB each: PNG, JPEG, WebP, GIF, PDF, DOCX and UTF-8 text/code.
Animated pictures use the first frame. Scanned PDFs without text need screenshots.
PDF extraction covers up to 40 pages, and each document contributes at most 40,000
characters; incomplete extraction is explicitly labelled. Session limits are 20
files and 80,000 characters of attachment context. Start a new conversation for
more. Unsupported, empty, corrupt and locked files report a readable error.

Uploads stay in session memory rather than being saved as local files or personal
memory. Their contents are sent to your configured model provider as conversation
context. Sending waits for an agent receipt; a lost receipt can be retried without
uploading or submitting the accepted message twice. File contents do not authorize
Mac controls, messages, or memory writes.

## Background Mac companion

See [companion and wake-word setup](wake-word.md) for the current installer,
login startup, local wake detector and bounded recovery behavior.
