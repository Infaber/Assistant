# Ariana 3.0 — conversation and companion upgrade

Review date: 1 November 2026. No installation, deployment, microphone permission grant, production configuration change, merge, or remote push was performed.

## Baseline and scope

Fetched `Infaber/Assistant` and inspected draft PR #12 before editing. The remote default branch is `main`, at `1e6c0350fc3c336da4905426fbd53587f09ca6a3`. The PR and `codex/ariana-3-conversation-voice` still point to `b396813300529156a5d40b823051667e7788d906`. Work is based on that PR head, in an isolated local clone on `codex/ariana-3-polish`; the previous checkout is unchanged.

PR #12 already includes read-only Home Assistant room-context aggregation and its privacy/sensor safeguards. This upgrade preserves that cumulative work. No Home Assistant, Frigate, camera, native companion, action-execution, or approval implementation is changed by this diff. Dependency updates are reviewed separately below.

## User-visible changes

- The orb remains central. Conversation state and microphone publication are visible, recent messages appear on the main screen, and the full conversation/activity view is directly reachable once there are messages.
- Activating explicitly asks the user to wait for Listening. Activation can be canceled. Standby explains that an enabled local wake detector may still listen.
- Microphone controls remain discoverable. Settings gain clearer spacing, contrast, responsive layout and keyboard focus restoration. Existing reduced-motion support is retained and tested.
- Voice settings show an active snapshot separately from saved changes awaiting a new connection. Effective style defaults are populated. Late responses from an old connection cannot overwrite disconnected settings.
- Selecting the configured default explicitly clears the saved Gemini override. Reset is validated and committed atomically with other preference changes; omission alone never deletes an override.
- Five fixed samples cover neutral explanation, casual conversation, seriousness, amusement and self-correction. Selection and playback are explicit. Samples have no tools, allow interruption and share a 15-second backend cooldown. They may appear in model/session history; generation is not guaranteed verbatim or acoustically identical.
- Local Kokoro speaking rate offers 0.8×, 1.0× and 1.2×. These bounded values reach the actual synthesis call. The existing speaker ID 3 is retained; no unverified voice catalog was exposed.
- A/B slots remain local configuration data. Loading does not save, reconnect or play audio. Malformed stored slots are discarded safely.
- Diagnostics add count, median and nearest-rank p95 to the existing bounded numerical measurements. Raw timing data remains behind a second disclosure. SDK state timing is not acoustic latency.

## Runtime findings and implementation

### Wake and capture ownership

The detector (`wake_word.py`) owns a local sounddevice stream. It sends newline-delimited control events to the native companion. The Swift companion forwards a wake event into the web view. The frontend waits for agent readiness and then publishes a separate LiveKit microphone track. The detector event carries no PCM, timestamped audio segments, or transfer acknowledgment.

A reliable continuous wake-phrase-to-command handoff therefore needs an explicit audio transport, resampling/time-boundary protocol, deduplication, capture-owner transfer and cancellation acknowledgments. Adding a ring buffer alone would collect audio without a route into either intended pipeline. No buffer was added. **Say the wake phrase, wait for Listening, then speak. Immediate commands can still lose leading words.**

The publication helper now retains exclusive wake ownership until asynchronous publication and cleanup finish. A canceled attempt cannot start another wake publication while its late cleanup could mute the replacement. Manual microphone controls are disabled during publication cleanup. A delayed rejection after cancellation is treated as cancellation if cleanup succeeds; cleanup failures remain visible. Sleep, offline, pause, standby, permission revocation and native wake-disable during pending activation cancel capture intent. These are application-state protections, not proof of OS/hardware mute.

The existing 90-second idle window extends during input activity, model thinking and output. Raw input level or repeated speaking detection can still keep it open under sustained noise. No hard duration cap was added: it could cut off quiet speech, a long explanation or thinking. Explicit mute remains available. Real-device noise and echo evaluation is required.

### Interruption and continuity

Normal mode still uses Gemini native audio through LiveKit, with provider turn detection. Local still uses Whisper, Silero VAD, Ollama and Kokoro. No new provider, cloud fallback or short-word whitelist was added. “Yeah” can still be a correction and can still interrupt.

Local false-interruption auto-resume is explicitly disabled using the installed SDK's `TurnHandlingOptions`. Cancellation yields instead of automatically restarting old speech. A synthesis regression drives the real adapter with a controlled native synthesis fixture: a canceled old callback returns 0, then a newer turn can produce output. This proves adapter mechanics, not stop-to-silence latency on speakers.

Local context keeps the SDK's tool-safe 24-item tail. For replies up to three words, retrieval now includes up to six preceding conversational messages, each capped at 160 characters, with a 1,000-character total query cap. This preserves assistant-provided alternatives and survives consecutive short replies. Generated text after the current user turn is excluded from that query.

Matched older user excerpts can bring their immediately adjacent assistant explanation, capped at 700 characters with its interruption flag. The adjacency check uses the original message sequence, so removing external/media turns cannot create false adjacency. Historical material remains explicitly untrusted evidence, not fresh user turns, tool instructions, approvals or requests to execute. No action is replayed. Existing task receipts and approval protections remain unchanged.

Retrieval remains lexical and bounded; it is not comprehensive long-term conversational understanding. “Continue” cannot recover unheard text that was never retained. The two added conversation scenarios require real-model evaluation before claiming language-quality improvements.

### Voice settings and expressive speech

Gemini startup uses one explicit preferences snapshot for voice and turn-end timing, avoiding a save between reads changing what the UI reports as active. Active style display reads the agent's actual style block, including successful spoken preference updates, rather than confusing a stale companion preference snapshot with current instructions.

Style settings remain model guidance. They are not exact pitch, emotion, laughter or timing controls. The serious and amused scripts are comparison material, not instructions to force theatrical delivery throughout conversation.

**No independent audio backchannel subsystem was implemented.** The current SDK exposes interruption and speech-generation controls, but that alone does not demonstrate a safe simultaneous acknowledgment path preserving the user's input turn, preventing self-transcription/feedback and excluding tools. Visual cues remain optional and silent. Input acknowledgment classification is also unresolved: a short acknowledgment can still interrupt Gemini. No canned acknowledgment clips were substituted.

References consulted: [LiveKit turns](https://docs.livekit.io/agents/logic/turns/), [speech and audio](https://docs.livekit.io/agents/multimodality/audio/), installed LiveKit 1.8.5 source and local Kokoro adapter, and installed Next.js client-component documentation. The installed SDK supports the arguments used; the CLI reported a docs-server version newer than its own, so installed signatures were checked directly.

## Validation

All runtime checks below used existing installed dependencies, including Next.js 16.3.8 and LiveKit Agents 1.8.5. No new dependencies were installed. The prepared security lockfile changes have **not** been runtime-tested with their new packages.

| Check | Result |
|---|---|
| Backend `uv run --no-sync pytest ariana/tests -q` | 541 passed; one upstream Google `_UnionGenericAlias` deprecation warning |
| Ruff lint and format | Passed, 137 Python files formatted/checked |
| Frontend unit tests | 41 passed |
| WebKit browser tests | 23 passed, including four isolated voice-component RPC-fixture tests |
| Frontend typecheck | Passed |
| Production build | Passed on existing Next.js 16.3.8 |
| Native Swift app compilation | Passed; executable only compiled, never launched/installed |
| Native state tests | Passed: backoff, disabled/repeated wake, output suppression, sleep, listening |
| Isolated native service tests | Passed: two crashes recovered, duplicate start prevented, shutdown stopped retries |
| Installer shell syntax | Passed; installer was not executed |
| Repository credential-candidate scan | 0 candidates; values never printed |
| `uv lock --check --offline` | Passed |
| Git whitespace/diff check | Passed |
| Real-model debugger/simulations | Not run: no Google/LiveKit credentials or environment files available in this checkout |
| Physical microphone/speaker, wake accuracy, echo, physical sleep/reconnect | Not run; no permission grant or live audio session |

Browser tests initially exposed the status heading's incorrect accessibility role and Safari focus restoration behavior. Both were fixed, then the full suite passed. Screenshots were captured in WebKit after canvas rendering: desktop, mobile and settings. They show the real disconnected interface, not a claimed live-model session.

## Dependency advisories

Audit date: 1 November 2026. Registry/OSV responses describe known package advisories, not an exploitability assessment of this app.

- npm reported Next.js 16.3.8 affected by `GHSA-2464-fhr4-w9xw`, `GHSA-p3m5-59mp-jv5r`, and `GHSA-673q-mjm6-r5xr`. Manifest/lockfile updated to compatible 16.4.3; npm reports zero advisories for the resulting lockfile. Installed Next remains 16.3.8 because installation was out of scope.
- Python lockfile updates: aiohttp 3.14.3 → 3.14.5, certifi 2026.7.22 → 2026.10.23, pyasn1 0.6.4 → 0.6.5, pypdf 6.19.0 → 6.21.4, yarl 1.23.0 → 1.25.1. Removed the obsolete yarl packaging workaround after verifying 1.25.1 has an sdist and Python 3.14 wheels.
- Final OSV check covers 113 locked registry packages. Remaining findings: opentelemetry-api 1.44.0 (`GHSA-xcq7-p3pf-p88h`) and Pillow 12.3.0 (59 advisory identifiers, including aliases). The complete list is supplied as `dependency-audit.json` in the review package.
- Pillow's reported fixes require version 13. OpenTelemetry's attempted resolution updated LiveKit/Google SDKs and moved OpenAI from 2.x to 3.x; that broad change was discarded. These upgrades require a separate compatibility review. No forced major upgrade remains in this diff.
- esbuild 0.28.2 was already installed transitively through the test tooling. It is now an explicit development dependency for repeatable isolated browser component tests; no new package was installed.

Before merging, install the prepared lockfiles in an isolated development environment and repeat backend/frontend/browser checks. This review does not claim the new dependency set is validated.

## Review package

The incremental patch applies to `b396813`. It preserves existing PR #12 functionality. The package includes source, regression tests, screenshots, this report, dependency findings and the Mac listening checklist. No remote branch or PR content was changed.
