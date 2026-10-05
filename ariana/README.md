# Ariana

A personal voice assistant built with LiveKit Agents and Google's Gemini Live
API. Ariana uses `gemini-3.1-flash-live-preview`, the `Achernar` voice, and British
English. Gemini handles speech input, speech output, and turn detection.

Ariana can search the public web and open, read, and list links on public pages
using a session-isolated Playwright WebKit browser. It also accepts video input
when a connected frontend supplies it. Audio enhancement uses the ai-coustics
plugin with LiveKit Cloud authentication.

## Setup

Install Python (3.14 matches the production image), [uv](https://docs.astral.sh/uv/),
and the [LiveKit CLI](https://docs.livekit.io/intro/basics/cli/), version 2.18.8 or
later for the debugger commands below.

```sh
git clone https://github.com/Infaber/Assistant.git
cd Assistant/ariana
uv sync --locked --dev
uv run playwright install webkit
cp .env.example .env.local
```

On Linux, install WebKit's system dependencies as well:

```sh
uv run playwright install --with-deps webkit
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
[LiveKit React starter](https://github.com/livekit-examples/agent-starter-react).

## Browser and search settings

| Variable | Default | Purpose |
| --- | --- | --- |
| `ARIANA_BROWSER_HEADLESS` | `0` | Set to `1` on a server without a desktop. |
| `ARIANA_BROWSER_TIMEOUT_MS` | `15000` | Browser operation timeout. |
| `ARIANA_BROWSER_MAX_TEXT_LENGTH` | `8000` | Maximum page text returned to the model. |
| `ARIANA_BROWSER_ALLOWED_HOSTS` | empty | Comma-separated allowed hosts, including their subdomains. |
| `ARIANA_SEARCH_TIMEOUT_SECONDS` | `15` | How long Ariana waits for a web search. |

The browser starts on the first open/search request. Missing browser binaries
produce a tool error while the voice session remains available. A visible window
appears on the **worker's machine**; deploying to a server does not open a browser
on the user's computer. The Docker image uses headless mode.

Browser tools block local/private addresses, embedded URL credentials, and
non-HTTP(S) URLs. Service workers are disabled so requests go through the URL
filter. These checks are defense in depth; use network-level egress restrictions
when exposing the worker to untrusted users. The browser allowlist applies to
browser requests, including subresources; it does not restrict the separate web
search provider. Include `duckduckgo.com` for browser search when using an allowlist.

Search logs record completion or failure without queries or results. The search
timeout bounds the tool's wait; it does not forcibly stop a provider thread already
running. Search/browser content is untrusted input, as described in Ariana's prompt.

## Tests and CI

```sh
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
```

Tests cover browser lifecycle, navigation errors, URL restrictions, search errors
and timeouts, and credential validation. They use mocked backends plus a real,
headless WebKit smoke test; no model API keys are required.

Repository-root `.github/workflows/checks.yml` runs these checks on pull requests
and pushes to `main`. Dependencies come from the committed `uv.lock`.

Full conversation scenarios are in `scenarios.yaml`. Run them with:

```sh
lk agent simulate text --scenarios scenarios.yaml
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

The image installs WebKit and its native libraries and runs as a non-root user.
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
preserved. Ariana can also search note titles (`notes_list`), read a selected note
(`notes_read`), and append or replace its contents (`notes_edit`). It uses stable IDs
so duplicate titles can be disambiguated. There is no delete tool.

Creating or editing always previews the proposed change and waits for a **new user
reply saying yes**. The code blocks writes in the preview turn and consumes each
confirmation once. Corrections, refusal, or changed arguments require a fresh preview.
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
