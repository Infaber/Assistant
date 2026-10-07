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
recovery constructor. `ARIANA_GOOGLE_MODEL` overrides the default. Voice remains
Achernar and language en-GB. Secrets are read from the environment.

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
