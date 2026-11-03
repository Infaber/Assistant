# Ariana 3: first implementation stage

Inspected baseline: `1e6c035` (31 October 2026 checkout). This is a tested continuity
upgrade, not completion of all ten requested phases.

## Architecture and existing functionality

The repository has a Python LiveKit worker (`ariana/src/agent.py`), a Next.js orb UI
(`frontend/components/ariana.tsx`) and a Swift Mac launcher (`desktop`). Normal uses
Gemini Live, configured centrally in `model_config.py`; local mode uses loopback
Ollama with Whisper STT, Kokoro TTS and Silero VAD. Local routing selects bounded
tool groups. Speech streams incrementally, with warmup, latency metrics, recovery
and interruption handling already implemented in recent commits.

SQLite memory already has topic retrieval, typed facts/preferences/projects/events,
expiry, correction/deletion/pause, two previous project summaries and due follow-ups.
Personality already has persistent warmth/playfulness/sarcasm/initiative/verbosity
controls through the preferences tool, plus shared character and action policy.
There is no existing visual editor for these style values; voice/text adjustment
works. This stage preserves that interface.

Home Assistant already discovers actual entity/area/device metadata, reads fresh
states, resolves aliases and verifies service outcomes. Frigate awareness already
checks freshness, separates detections from identity, guards image delivery and
requires opt-in for announcements. Check-ins already have quiet hours, leases,
cooldowns, single-use claims and an unanswered guard. Screen sharing is already an
explicit frontend control, with local vision disabled. Generic Mac control is a
separate guarded capability. No additional screen capture or autonomous control
was added.

Recent history reviewed: personality/typed memory, conversation v2/evaluation,
independent local voice, incremental speech/latency and startup/recovery hardening.
Existing unit, integration, browser and real-model simulation suites were reviewed.

## Three weaknesses addressed

1. Startup/recovery supplied recent facts regardless of relevance, sometimes from a
   stale closure. Startup now supplies an index only; refresh/recovery reread it.
   Local inference retrieves current relevant facts automatically. Gemini continues
   to retrieve with its memory tool; changing its native turn detection just to add
   pipeline RAG would risk voice reliability.
2. Unchanged remember calls reset lifecycle state, while identical facts consumed
   multiple slots. Repeated saves now preserve lifecycle; exact normalized duplicate
   facts are rejected with their existing topic. Importance scores rank relevant
   results. A user-source quote is required at the exposed save tool boundary.
3. Engine switches discarded all conversation and local requests lost older topics.
   A one-switch consent checkbox enables bounded plain-text transfer. The local
   request builder retrieves matching older user excerpts beyond the recent tail.
   Tools, media and staged approvals never transfer, and no request is replayed.

## Verification and practical limits

Automated tests cover old-database migration, unrelated exclusion, importance,
deduplication, save provenance, repeated follow-ups, correction/deletion, long
conversations with topic changes, interruption metadata, engine-transfer guards,
current-memory injection through the real SDK context type, and personality settings
across recreated normal/local agents. Provider output in these tests is scripted;
it does not establish language understanding, humor quality or speech quality.

The existing CI real-model conversation set now includes hypothetical-memory and
repeated-project cases, with end-state checks. No LiveKit or Google credentials
are configured in this checkout, so simulations, debugger conversations and live
voice/integration tests could not be run. Run the extended simulation set in the
existing credentialed CI before deployment.

## Real-world acceptance checklist (not executed here)

- Start the microphone muted; explicitly enable it. Confirm speech/transcription,
  a short reply, a long pause mid-sentence and background speech not addressed to
  Ariana. Record accidental triggers rather than assuming wake gating works.
- Interrupt a long answer repeatedly; verify playback stops, the new turn wins,
  no duplicate reply plays, and interrupted actions are checked before retry.
- Talk for 20 minutes across three topics, return to the first and correct a fact.
  Check that relevant memory is current and unrelated details stay out of replies.
- Switch both directions with transfer off, then on. Inspect provider transcripts:
  off carries no chat; on carries bounded text only. Verify opt-in resets, pending
  approvals clear, the microphone remains off on uncertainty and no tools replay.
- Disable sarcasm, restart, switch engines and exercise a failing tool. Evaluate
  consistent character, concise practical frustration responses, disagreement,
  celebration, venting and humor by listening rather than exact wording.
- Use headphones and speakers separately. Record first-audio latency (median and
  p95), overlaps, false turn ends and interruption recovery on both engines.
- With authorized HA/Frigate fixtures, test stale/unavailable sensors, unknown
  people, quiet hours, opt-out, duplicate events and one unanswered follow-up.
- Explicitly start/stop screen sharing; confirm visible sharing state, no capture
  before activation, and local-mode rejection of image analysis.

## Remaining stages

- Evaluate real-model conversations and actual audio before tuning endpointing,
  emotional adaptation or personality behavior further.
- Consider local semantic embeddings after measuring lexical retrieval misses;
  evidence quoting is not a semantic verifier of truth or sensitive content.
- Add a visual memory/style editor if desired; inspection/correction/deletion remain
  available through existing voice/text tools. No full conversation archive exists.
- Develop room-context fusion and user-defined proactive priorities against real
  HA/Frigate configurations. Do not duplicate the current consent/cooldown engine.
- Scope a distinct permission-controlled read-only screen-help mode separately from
  the existing sharing and guarded Mac-control capabilities.

## Results from this checkout

- Backend: **498 passed**, including 13 new tests across memory/context and
  personality consistency. Ruff lint and formatting checks passed.
- Frontend: **24 unit tests passed**, TypeScript check passed, production build
  passed, and **14 WebKit browser tests passed** (desktop/mobile and consent reset).
- Existing Google SDK emits a Python deprecation warning. `npm ci` also reported
  one critical dependency advisory in the locked baseline; no forced dependency
  upgrade was mixed into this behavioral change. Review it before deployment.
- No real-model simulation, physical microphone/speaker, Ollama service, HA or
  Frigate test was represented as a live success. Credentials and configured
  services were absent from the fresh checkout.

Changes are local to the cloned repository; nothing was pushed or deployed.
Apply the accompanying patch from the root of a checkout at baseline `1e6c035`
with `git apply --check ariana-3-continuity.patch`, then `git apply` that file.
