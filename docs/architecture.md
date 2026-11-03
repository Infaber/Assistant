# Architecture and model support

The native Swift companion supervises a local Next.js server and a Python LiveKit
worker. The frontend joins a fresh, scoped LiveKit room through a server-only token
endpoint. The Python agent owns integrations, local memory and action guards.

## Gemini Live verification (7 October 2026)

Google documents stable `gemini-3.8-live` as its recommended low-latency Live model.
[Google model documentation](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-live),
[LiveKit Gemini plugin](https://docs.livekit.io/agents/models/realtime/plugins/gemini/),
[LiveKit Python reference](https://docs.livekit.io/reference/python/livekit/plugins/google/realtime/index.html).
The locked Google plugin is 1.8.5. `src/model_config.py` is the common startup and
recovery constructor. `ARIANA_GOOGLE_MODEL` overrides the default. The default voice is warm Sulafat with American English delivery.
`ARIANA_GOOGLE_VOICE` overrides the voice across startup and recovery. Secrets are read from the environment.

3.8 defaults to asynchronous tools; Ariana explicitly selects Google's supported
BLOCKING mode to preserve its guarded tool flow. Removed affective/proactivity
flags and unsupported thinking settings are not sent. Audio output and input/output
transcripts are handled by LiveKit. An optional `ARIANA_FALLBACK_GOOGLE_MODEL` is
attempted once after a terminal model failure, carrying context without resubmitting
the last user turn. A backup shares project quotas and needs account testing.

## Deeper reasoning: prepared, intentionally gated

Google also documents stable
[3.8 Live extended thinking](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-live-extended-thinking).
It requires NON_BLOCKING tool behavior and uses `interaction_status=IDLE` to signal
actual completion; `turnComplete` alone is insufficient. The inspected LiveKit
Google 1.8.5 adapter does not handle that status. Selecting the extended model
therefore fails clearly rather than risking incorrect tool/turn sequencing.

`reasoning.py` defines bounded advisory requests and responses. A future router may
request a plan for genuinely complex tasks after the realtime agent gathers facts.
It receives no executable tool handles or approval authority. Simple commands stay
on the fast model. No second model is instantiated or billed by this release.
Before enabling extended reasoning, add adapter idle-state support and simulations
for pending tools, cancellation, interruption and approval boundaries.

## Effects and partial completion

`action_events.py` publishes redacted states; `task_ledger.py` keeps bounded receipts
in session memory. Returned is not verified. Approval is not dispatch. Interrupted
or timed-out writes are uncertain. Matching already-dispatched Apple writes are
blocked in that session; Accessibility dispatch uses its independent one-use
snapshot protection, allowing legitimate navigation with new observations.

Receipts contain labels, status and hashed argument fingerprints, never note/email
contents. They are not a durable transaction database or an executable task queue.
After restart the agent must inspect actual app state before any consequential
retry; recovery itself never resends a user request. A repeated intentional identical
Apple write requires a fresh session and a state check. No model is permitted to
reset receipts or manufacture verified results.

`instructions.py` holds conversational guidance. Exact approval payload/turn checks,
Notes revisions, URL validation and Accessibility constraints remain in tool code.
Understanding natural consent and recognizing untrusted prose still require model
judgment; a boolean from the model alone cannot satisfy the Apple write guard.

## Two inference pipelines

Normal uses the existing Gemini realtime model. Local uses the optional
`local-voice` extra: Whisper/Kokoro adapters, Silero VAD and a loopback-only Ollama
LLM. `ai_modes.py` owns authenticated room RPC handoffs/readiness and action gates;
`local_routing.py` selects bounded tool visibility without executing anything.
Each target Agent configures its own turn handling. Receipts/userdata remain shared,
while model chat context resets by default. A one-switch UI opt-in can transfer
a bounded text conversation; no media, tools, instructions or approvals transfer. Local failure never constructs a cloud fallback.
See [local AI](local-ai.md) for privacy/transport distinctions and setup.

## Ariana 3 voice lifecycle audit (1 November 2026)

Installed in this checkout: LiveKit Agents 1.8.5, Google plugin 1.8.5 and
Google GenAI 2.28.0; frontend LiveKit client is locked at 2.22.3. Sherpa-ONNX
1.13.8 was initially absent; the locked wake extra was then installed for validation
with sherpa-onnx-core 1.13.8, sounddevice 0.5.6 and sentencepiece 0.2.2. The pinned
keyword model was checksum-verified in an isolated workspace directory, Hey Ariana
was tokenized, and model loading plus 20 silence blocks were checked without
opening the microphone. This does not establish wake accuracy.

Normal audio flows WebKit/browser microphone → LiveKit room → AI-coustics input
enhancement → Gemini realtime input, with Gemini-native audio returned through
LiveKit playback. Gemini owns VAD/turn completion and interruption signals under
`turn_detection="realtime_llm"`. The installed Google adapter advertises
`can_disable_turn_detection=False`; generic pipeline interruption filters cannot
be applied to this path. Local mode retains its independent Whisper/Silero/
Ollama/Kokoro pipeline. No speech adapter was replaced.

Available session observations include user/agent state changes, input
transcriptions, completed conversation items and tool events. Provider state events
are not raw acoustic boundaries. New diagnostics measure local SDK user-end to
speaking-state and overlap to speaking-state-stop, alongside existing model/tool
metrics. Browser wake-event to microphone readiness excludes keyword-decoder
latency and does not prove acoustic readiness or physical output-stop time.

`voice_controls.py` serves authenticated UI settings, fixed samples and explicit
standby via a room RPC. `conversation_tools.py` can request standby through an
agent-only data event when the model interprets a genuine conversational ending.
Approvals are cleared; receipts remain and no action is replayed. The frontend
owns wake activation tokens, mic publication and inactivity timeout. Swift owns
local detector/permission lifetime, output suppression and phrase setup.

See [voice evaluation and limitations](ariana-3-voice-evaluation.md) before treating
the build as a validated natural-voice release.
