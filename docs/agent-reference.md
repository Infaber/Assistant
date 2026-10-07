# Ariana

A personal voice assistant built with LiveKit Agents and Google's Gemini Live
API. Ariana uses `gemini-3.8-live`, the `Achernar` voice, and British
English. Gemini handles speech input, speech output, and turn detection.

Ariana searches and reads through the real Safari app on the Mac running the
agent. It also accepts video input when the frontend supplies it. Audio
enhancement uses ai-coustics with LiveKit Cloud authentication.

## Setup

Install Python (3.14 matches the production image), [uv](https://docs.astral.sh/uv/),
and the [LiveKit CLI](https://docs.livekit.io/intro/basics/cli/), version 2.18.8 or
later for the debugger commands below.

```sh
git clone https://github.com/Infaber/Assistant.git
cd Assistant/ariana
uv sync --locked --dev
cp -n .env.example .env.local
```

Fill in `.env.local` with your LiveKit Cloud project's `LIVEKIT_URL`,
`LIVEKIT_API_KEY`, and `LIVEKIT_API_SECRET`, plus `GOOGLE_API_KEY` from Google AI
Studio. `GEMINI_API_KEY` is accepted as an alternative. Existing environment
variables take precedence over `.env.local`. Never commit credentials.

The CLI can write the LiveKit credentials for your selected project:

```sh
lk cloud auth
lk app env --write --destination .env.local
```

Add the Google key afterward. Ariana reports a clear configuration error if both
Google key variables are missing. See the
[Gemini plugin documentation](https://docs.livekit.io/agents/models/realtime/plugins/gemini/)
for authentication and model options.

## Run

Run from `ariana/`:

```sh
# Talk through the terminal.
lk agent console

# Connect a web/mobile frontend or the LiveKit Agent Console.
lk agent dev

# Production worker.
uv run src/agent.py start
```

The worker registers as `ariana`; configure your frontend's agent dispatch to
target that name. A web frontend can start from the
[Ariana frontend](../frontend/README.md).

## Safari and action feedback

Browsing uses Safari Automation, with a fixed read-only page script and an
Accessibility fallback. Run locally on macOS and allow Automation for Safari and
Accessibility for your launcher. Safari's Develop → Allow JavaScript from Apple
Events is optional for fuller page reads. No headless browser is installed in the
Docker image; Linux reports browsing as unavailable. User-requested local HTTP(S)
pages are supported, and executable URLs/embedded credentials are rejected.

Tools emit bounded, redacted `ariana.activity` events to the connected room. The
frontend distinguishes verified outcomes from dispatched inputs and unverified
legacy results. See the [main README](../README.md#safari-browsing-and-verified-mac-actions)
for permissions, recovery settings, and verification limits.

| Variable | Default | Purpose |
| --- | --- | --- |
| `ARIANA_GOOGLE_MODEL` | `gemini-3.8-live` | Primary Gemini Live model. |
| `ARIANA_FALLBACK_GOOGLE_MODEL` | empty | Optional compatible backup, attempted once after terminal failure. |

## Tests and CI

```sh
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
```

Tests cover Safari navigation, tab identity, permission errors, URL validation,
activity redaction, model recovery and Mac snapshots. They use isolated backends;
no model API keys are required. The opt-in `scripts/check_mac_controls.py` runs
real Mac input against disposable test windows.

Repository-root `.github/workflows/checks.yml` runs these checks on pull requests
and pushes to `main`. Dependencies come from the committed `uv.lock`.

Full conversation scenarios are in `scenarios.yaml`. Run them with:

```sh
lk agent simulate text --scenarios scenarios.yaml
lk agent simulate text --scenarios scenarios-reliability.yaml
```

The search-failure and untrusted-page scenarios use deterministic tool fixtures
selected through simulation userdata. Fixtures are installed only for simulation
jobs; ordinary sessions keep their real tools. Other browser scenarios use public
pages and exercise the real URL filter.

The root `Simulations` workflow runs on merges to `main` and on demand. It spends
real inference and requires repository secrets named `LIVEKIT_URL`,
`LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, and `GOOGLE_API_KEY`. Unit tests do not
replace a live voice check for audio quality and interruptions.

To inspect a conversation interactively:

```sh
lk agent debugger start
lk agent debugger say "Hello, what can you do?"
lk agent debugger restart  # after editing the source
lk agent debugger stop
```

## Docker

From the repository root:

```sh
docker build -t ariana ./ariana
docker run --rm --env-file ariana/.env.local ariana
```

The image runs as a non-root user. Safari and native Mac controls are unavailable
in the Linux container.
For managed deployment, see the
[LiveKit deployment guide](https://docs.livekit.io/deploy/agents/).

## Personal integrations

Ariana includes the restored Home Assistant, YR weather, Apple Calendar, Reminders,
and Mail tools. Set `HOME_ASSISTANT_URL` and `HOME_ASSISTANT_TOKEN` in
`ariana/.env.local` for smart-home requests. Apple tools run on the Mac hosting
the agent and require macOS Automation permission for Calendar, Reminders, and
Mail. They are unavailable on Linux hosts. Event creation, reminder creation,
and email sending retain their confirmation checks.

The integration capability regression is in `scenarios-integrations.yaml` and
runs alongside the existing simulations in CI.

## Apple Notes

Ask Ariana, for example, "Create a note called Grocery list with milk and bread."
The `notes_create` tool creates a new note in the default account's default folder
on the Mac running the agent. Titles, line breaks, and plain-text contents are
preserved. The title comes from the first heading in the body; it is not set a second time through Notes' name property. Ariana can also search note titles (`notes_list`), read a selected note
(`notes_read`), and append or replace its contents (`notes_edit`). It uses stable IDs
so duplicate titles can be disambiguated. There is no delete tool.

Creating or editing always previews the proposed change and waits for a **new user
reply approving the change** (natural phrasing is fine; no required keywords). The code blocks writes in the preview turn and consumes each
confirmation once. Ariana interprets approval in context. Refusals and unrelated replies do not approve a write; changed arguments require a fresh preview.
Existing conversations must be restarted to pick up this behavior.

Appending preserves existing HTML. Replacing uses plain text and removes previous
formatting; Ariana explains that before asking permission. Replacement is blocked
for notes with attachments, and editing shared or locked notes is blocked. Edits
check the revision returned by reading and refuse a note that changed meanwhile.
Note contents are treated as data, never instructions or permission to use tools.

On first use, macOS may ask the app launching Ariana to control Notes. Allow it in
System Settings > Privacy & Security > Automation. Notes must have a configured
account; the integration does not work on a Linux-hosted agent. Restart a running
agent after updating, then start a new conversation.

## Mac desktop control

Ariana can open or switch to apps, list running apps, inspect the foreground
window and menus, click named controls, type into text fields, press keyboard
shortcuts, and scroll up/down using mouse-wheel events. For example:

- "Open Spotify and search for Daft Punk."
- "Open Safari and focus the address bar."
- "Scroll down in this app."

Run the agent locally on your Mac. On first use, allow the app launching Ariana
(usually Terminal or VS Code) in **System Settings > Privacy & Security >
Accessibility**, and allow **Spotify** under **Automation** for direct playback commands.
Restart the agent if macOS asks. Grant permission to the actual launching app;
permission given to Codex does not automatically cover your Terminal session.
These controls use Accessibility, so this feature does not need Screen Recording.

The `mac_control` tool returns labeled element IDs from an inspection. Every
click, typing operation, shortcut or scroll uses a fresh session-local snapshot,
which expires after 60 seconds and is consumed before the action executes. It
refuses a changed foreground app/window or changed target control. Inspect again
instead of retrying an uncertain action. Password fields are redacted and cannot
be clicked or typed into through this tool.

Ordinary requested navigation and search do not require approval on every click.
Ariana asks before sending, deleting, purchasing, executing commands, or changing
account/security settings. Use the direct Notes, Calendar and Mail integrations
for their supported tasks. UI text is treated as untrusted data.

Apps must expose their controls through macOS Accessibility. Custom interfaces
may expose incomplete labels or no editable controls; Ariana reports the problem
instead of guessing mouse coordinates. Screenshots and coordinate-based clicking
are not part of this version. Scrolling sends mouse-wheel events, so behavior depends on
which control has focus. Mac behavior simulations use a fake desktop even in CI;
no real applications are opened or manipulated by them.

Spotify search and playback use `spotify_control` directly, avoiding interface scans.
Search opens Spotify results; Play resumes the selected track. Playback returns the
actual player state, and does not claim a search result was selected automatically.

Interface inspection uses a native Swift Accessibility helper with bounded queries.
It compiles once per source version and caches the executable locally. Apple Command
Line Tools are required (`xcode-select --install` if missing). The first compilation
can take roughly 30 seconds; subsequent scans skip compilation. Unlock your Mac
before inspecting, clicking, typing, or sending shortcuts.

## Desktop navigation and preferences

Use “Search Safari for LiveKit voice agents” or “Open https://docs.livekit.io in
Safari.” The Safari tools open and read the requested page. Legacy `mac_control`
browser navigation also uses Safari, but only confirms dispatch.

Inspection prioritizes the focused field, filters structural noise, includes
menu commands, and supports a label/text query and output limit. For multiple
windows, Ariana can list and raise an inspected window. Typing can insert text
or replace a field's contents without submitting. Keyboard shortcuts respect the
active macOS keyboard layout and support function keys. Scrolling supports all
four directions and can target an inspected scroll area.

When a normal Accessibility press is unsupported, ordinary buttons/links can use
an inspected frame as a fallback. The helper checks that the frame is on a display
and that the actual element at that position belongs to the inspected control.
Covered or moved controls are rejected, as are clicks whose center belongs to a different interactive child. Ariana still cannot operate arbitrary
canvas interfaces or guess locations from screenshots. Mac operations within a
conversation are serialized, and stale targets require a new inspection.

Ask “Remember my preferred browser is Safari” or “Remember my home city is Oslo.”
Supported preferences are display name, home city, browser, reply style
(brief/normal/detailed), and units (metric/imperial). “What do you remember?” reads
them; “Forget my browser preference” removes that entry. Saved browser preferences are retained for compatibility; browsing always uses
Safari. Other saved preferences guide the assistant
when recalled; they do not change macOS settings or the voice model.

Preferences are stored locally in
`~/Library/Application Support/Ariana/preferences.json` on macOS, or
`${XDG_CONFIG_HOME:-~/.config}/Ariana/preferences.json` elsewhere. They persist
across restarts; conversation history and API secrets are not stored there.
Only explicit requests should save or remove a preference.

Ask “Check your integrations” to see which settings are configured and whether
Mac Accessibility is available. This check never returns secrets. Present
settings do not prove a service is reachable or its credentials are valid, and
Apple Automation permissions still need to be granted individually.

The native helper uses Apple's [Accessibility APIs](https://developer.apple.com/documentation/applicationservices/axuielement)
and [keyboard translation API](https://developer.apple.com/documentation/coreservices/1390584-uckeytranslate).

To repeat the real Mac smoke check, unlock your Mac and run from `ariana/`:

```sh
uv run scripts/check_mac_controls.py
```

This opt-in check temporarily opens two dedicated test windows and exercises
replacement, focused Unicode typing, shortcuts, native/fallback clicks, scroll
dispatch and window switching. It closes the test app afterward. It needs
Accessibility permission and Apple Command Line Tools; avoid switching apps while
it runs. It does not open or edit your personal documents.

## General personal memory

Beyond the five fixed preferences, `memory_manage` stores useful self-disclosed interests, routines and ongoing projects automatically. It supports recall, correction by stable topic, explicit forgetting, and pause/resume of saving. Storage is a local SQLite database alongside the preferences file, with atomic transactions, a 100-fact limit and private file permissions. The recent 20 facts are included as untrusted personal context at session startup. Other facts can be searched through the tool. Set `ARIANA_MEMORY_PATH` to use an alternative database, including isolated testing.

Do not save secrets, sensitive details, whole transcripts, third-party private information or facts from app/web content. These constraints are part of the model policy; the storage also rejects common credential labels. Saved facts never authorize actions. Forgetting removes the saved fact, but does not erase an existing conversation transcript or provider logs.

Run `lk agent simulate text --scenarios scenarios-memory.yaml` for the isolated memory conversation checks.
