# Ariana 3 voice and wake evaluation — 1 November 2026

This is a software implementation and evaluation candidate, not a claim of
human-equivalent speech or completed real-world audio validation. The earlier
memory/continuity and room/priority work is retained. Home Assistant and Frigate
runtime modules were frozen for this voice pass; no new integration features were
added in response to the voice-focused request.

## Initial technical assessment

Normal uses Gemini native audio through LiveKit Agents 1.8.5 / Google plugin 1.8.5 /
Google GenAI 2.28.0. The configured model remains `gemini-3.8-live`, with the existing
blocking tool flow. Native input owns endpointing and interruption: the Google
adapter cannot disable provider turn detection in this configuration. Local mode
retains Whisper STT, Silero VAD, loopback Ollama and Kokoro; parity is not promised.

The wake helper reads local 16kHz audio in 100ms blocks with one keyword inference
thread, then disarms and emits an event. Swift suppresses detection during active
capture, output, output tail, busy states and sleep. WebKit opens/publishes the
conversation microphone after activation. No audio transport connects the helper's
capture to WebRTC input. Sherpa was initially absent. The locked wake extra was
then installed (sherpa-onnx/core 1.13.8, sounddevice 0.5.6, sentencepiece 0.2.2).
The pinned model was downloaded and checksum-verified into an isolated workspace
directory. Real Hey Ariana tokenization and `wake_word.py --check` passed; 20
zero-valued 100ms blocks produced no detections. No microphone was opened. This
checks loading/processing, not spoken-keyword accuracy or echo behavior.

The installed SDK offers user/agent state events, transcriptions, speech handles,
conversation metrics and tool execution events. Some arrive after the audio fact
they describe. No supported safe mid-input acknowledgment API was found. Native
cancellation is preserved; no short-word whitelist delays stop/wait/no. A quiet
mhm can still be treated as an interruption by Gemini. No claim is made that the
application now semantically distinguishes all acknowledgments from interruptions.

Official references checked against installed source:
[LiveKit Gemini](https://docs.livekit.io/agents/models/realtime/gemini/),
[realtime interruption ownership](https://docs.livekit.io/agents/logic/turns/),
[Google Live capabilities](https://ai.google.dev/gemini-api/docs/live-api/capabilities),
[Google voice options](https://ai.google.dev/gemini-api/docs/speech-generation#voice-options).

## Actual changes and deterministic before/after differences

| Before | After | Evidence type |
| --- | --- | --- |
| 15-second wake deadline started at the wake event | 90-second window starts after microphone readiness | Clock-driven state tests |
| Deadline refreshed on React dependency changes | Current activity is checked every 500ms, including sustained levels and ongoing output/thinking | Long-duration synthetic state test |
| Cold activation could enable capture before agent readiness | Cold join stays muted until agent readiness; activation token cancels delayed work | State/async wait tests |
| Permission callback could re-enable after a later disable intent | Generation-checked native consent rejects stale callbacks | Compiled Swift state assertions |
| Phrase change required CLI setup | Trusted companion Settings sends bounded explicit phrase setup requests | Browser IPC fixture + native compile |
| New wake setup defaulted to Ariana | New setup prefers Hey Ariana; verified existing phrases are preserved | Setup/tokenizer fixtures; no physical detection claim |
| Voice preset required environment editing | Authenticated UI saves supported presets and style settings atomically | Store/RPC tests |
| No fixed in-session comparison workflow | Settings-only A/B slots and explicit fixed-sample requests, with idle/cooldown/tool guards | RPC and browser tests; audio not listened to |
| No explicit contextual standby tool | Model-interpreted ending can request mic-muted standby; explicit UI stop also interrupts output | Tool/RPC/event wiring and simulation grading tests |
| Mostly provider/tool timing | Additional local SDK state timing and wake-readiness timing | Numerical event wiring tests |

Personality guidance now permits context-earned native amusement, brief hesitation
and self-correction. Delivery preferences are bounded. Those are guidance changes;
they are not proof of better laughter, emotional realism or conversational quality.
No canned response bank or forced filler was introduced.

## Backchannels and immediate-command handoff: limitations, not simulated success

There is **no new audio backchannel subsystem**. Independent clips risk overlap,
echo, self-transcription and false turn boundaries, and would not be verified as the
same Gemini voice. The safe implemented alternative is an optional visual listening
cue, default Subtle, with Off/Subtle/Expressive levels. It appears only during active
input with no active output. It has no audio source, model calls or tool path.
Opening Settings creates no audio. Genuine mid-speech acknowledgments remain open.

There is **no pre-roll/replay buffer** and no claim that “Hey Ariana, remind me…”
works seamlessly. The current detector → Swift → WebKit path cannot transfer audio
into the current session without a separate transport/publication design. Keeping
unusable private audio would add risk without solving the handoff. Wait for Listening
before speaking the command. No extra speech model or TTS service was added.

## Controls and privacy

- Normal presets: Sulafat (default), Aoede, Kore, Leda and Zephyr. Explicit saved
  selection wins over the existing environment fallback on a fresh connection.
- Conversation preferences include delivery, warmth, playfulness, sarcasm,
  initiative and talkativeness. These are model preferences, not exact audio knobs.
- Optional Gemini automatic end-of-speech silence: provider default (unchanged),
  500, 800 or 1200ms. A supported SDK config is constructed only on explicit choice.
  This can delay replies; it is not an interruption-sensitivity or semantic control.
- Voice/style settings from the panel apply on the next fresh connection, including
  a provider recovery/refresh; the panel never restarts a session by merely opening.
  For a controlled comparison, end/reconnect explicitly after each saved slot.
- Samples use the current active voice and fixed requested content with no tools,
  remain interruptible and require idle state plus cooldown. Live generation may
  vary from the text. Samples can appear in session history; no audio is recorded.
- Explicit standby mutes locally first and asks the backend to stop output. A
  contextual ending can finish a short goodbye while muting capture. Standby keeps
  context and may leave the separately opted-in local detector listening.
- No screen capture, new personal memory database, raw audio persistence, new
  camera permissions, action authorization or replay behavior was introduced.

## Automated validation and reproducible commands

Commands are run from repository root unless indicated. Use a writable module cache
with the matching Xcode toolchain; plain swiftc initially failed against the default
protected cache/toolchain, then xcrun plus this cache built successfully.

```sh
ariana/.venv/bin/ruff check ariana
ariana/.venv/bin/ruff format --check ariana
ariana/.venv/bin/pytest -q ariana/tests
npm test --prefix frontend
npm run typecheck --prefix frontend
npm run build --prefix frontend
(cd frontend && npm run test:browser)
xcrun swiftc -module-cache-path /private/tmp/ariana-voice-swift-cache \
  -parse-as-library desktop/Ariana.swift desktop/CompanionState.swift \
  desktop/ManagedService.swift -o /private/tmp/Ariana-voice-check \
  -framework Cocoa -framework WebKit -framework Network \
  -framework ServiceManagement -framework AVFoundation
xcrun swiftc -module-cache-path /private/tmp/ariana-voice-swift-cache \
  -parse-as-library desktop/CompanionState.swift desktop/CompanionStateTests.swift \
  -o /private/tmp/Ariana-voice-state-tests
/private/tmp/Ariana-voice-state-tests
xcrun swiftc -module-cache-path /private/tmp/ariana-voice-swift-cache \
  -parse-as-library desktop/CompanionState.swift desktop/ManagedService.swift \
  desktop/ManagedServiceTests.swift -o /private/tmp/Ariana-voice-service-tests
/private/tmp/Ariana-voice-service-tests "$(command -v python3)" "$PWD/ariana/src/service_runner.py"
bash -n desktop/install.sh
```

Final results: **524 backend tests, 30 frontend unit tests and 17 WebKit browser
tests passed**. Ruff lint/format, TypeScript checks, production build, native
companion build, Swift state assertions, isolated service crash/retry tests and
installer shell syntax checks passed. One pre-existing Google SDK deprecation
warning remains. The earlier baseline npm critical advisory remains outside this
voice change and should be reviewed before deployment.

The real keyword-model check used a workspace-only `ARIANA_WAKE_WORD_MODEL_DIR`;
no app data directory, user recording or active microphone was used. The setup
command was `python ariana/scripts/setup_wake_word.py --phrase "Hey Ariana"`,
followed by `python ariana/src/wake_word.py --check` with that same override. A
separate direct KeywordEngine loop fed 20 NumPy zero arrays. These results are
separate from the unit-suite counts. Tests cover settings validation,
read-only opening, samples without tools, cooldown, unauthorized callers, standby
cancellation/receipts, supported endpointing configuration, real SDK numerical event
wiring, delayed wake/permission ownership, phrase metadata and native crash recovery.
Two initial new browser tests failed because the test left the comparison panel
collapsed and did not acknowledge its mocked native settings request; both harness
issues were corrected and rerun without weakening the assertions.

Conversation evaluation cases now include thanks-with-continuation, unfinished
thoughts and short interruption repair. Real-model simulation fixtures check
whether the actual standby tool was used once or not used, rather than grading only
a claim in the reply. The full real-model set was **not run** here: the fresh
checkout has no configured LiveKit/Google credentials or provider quota. Existing
historical evaluation results are not evidence for this implementation.

## Mac mini listening and wake checklist — not executed

1. Configure credentials and rebuild/install on the intended Mac mini. Confirm
   Wake detection is off until opted in. Verify denial, later grant, disable during
   delayed grant, quit and sleep leave the intended capture state.
2. Configure Hey Ariana and test ten quiet activations at different distances,
   accents/volumes, background music and ordinary conversation. Count misses/false
   activations. Test Ariana's own speakers and headphones separately. Do not infer
   accuracy from the phrase tokenizer or IPC fixture.
3. Say Hey Ariana, wait for Listening, then ask a question. Check one capture owner,
   no duplicate replies and continued follow-up speech without repeating the phrase.
   Test the immediate-command form too; record lost words as the known handoff gap.
4. Speak for several minutes including stable quiet speech, 5–10 second thinking
   pauses, laughter and interruptions. Test a full 15–30 minute conversation with
   topic returns, corrections and short yes/no/why responses. Confirm standby only
   after inactivity, not in the middle of continuous speech.
5. Interrupt with stop, wait, no and a replacement question; repeat rapidly. Verify
   old output does not unexpectedly resume and no uncertain action is replayed.
   Also say mhm during output; log any unwanted cancellation as a provider limitation.
6. Use explicit standby, contextual goodnight, and thanks-with-a-continuation.
   Confirm the last one continues. Observe microphone mute and local detector state
   separately. Disconnect/reconnect and sleep/wake during activation and speech.
7. Compare two fresh connections with A/B slots and the same requested sample,
   device, volume and room. Rate intelligibility, pacing, seriousness/amusement and
   whether filler sounds forced. Do not report preferences as objective quality.
8. Inspect diagnostics. SDK timings measure local observed state changes; browser
   readiness begins at the wake event. Neither is acoustic output-stop latency or
   provider-only processing time. For acoustic timing, use an explicitly consented
   external recording/test harness and report its method separately.
9. Exercise existing Notes/Calendar/Reminders/Mail approvals, Spotify/Safari and
   model switching. Check memory pause/correction/forget, staged-approval clearing,
   receipt persistence and no new HA/Frigate behavior.

Next work should be driven by these observations: measured turn-cutting failures,
provider acknowledgment support, and a separately designed consented audio handoff.
Do not enable independent backchannel audio or claim continuous wake-command capture
until acoustic/echo and ownership tests support it.

## Delivery and integration freeze

The 16 existing Home Assistant, camera and Frigate runtime module files were
compared byte-for-byte against the end of stage two and were unchanged. Generic
simulation isolation now also blocks the standby tool except in its explicit
fictional fixture. This is compatibility protection, not integration development.

All changes are local; no app was installed, no permissions were exercised, and
nothing was pushed or deployed. The voice-only patch applies after the earlier
stage-two cumulative patch. The new complete patch applies directly to the
original `1e6c035` baseline and includes the earlier accepted stages as well.
Use `git apply --check` on the appropriate patch before applying; do not apply
both variants to the same checkout.
