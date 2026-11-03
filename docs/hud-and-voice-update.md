# HUD and voice update — 2 November 2026

The workspace now uses an angular cyan HUD, dark grid, orb reticles, compact system
navigation and a separate conversation panel. Unrestricted uses red throughout
panels, controls, labels and settings. The existing sculpted orb is retained.
Reticles fit short windows; keyboard controls, reduced motion and mobile layouts remain supported.

Gemini's Ariana persona receives explicit warm, soothing delivery guidance: softer
projection, relaxed cadence and gentle sentence endings, without theatrical
whispers or added filler. The selected voice and Local Kokoro voice are unchanged.
Jarvis persona does not receive the feminine Ariana delivery instruction.
Four real Gemini voice samples (two before/two after) were generated with fictional
conversation and no app tools or microphone. Prosody still needs human listening.

## Performance investigation

No speed experiment is enabled in this release. A smaller 1.7B model and shorter
tool descriptions produced faster speech but skipped requested fixture actions.
Other warmup, context-cache, routing, prompt-length and batching experiments did
not establish a consistent gain. They were reverted; the installed 4B profile,
original tools, full personality, memory policy and all effect guards remain intact.

The benchmark now waits for the backend-ready callback before starting its timer.
The earlier harness included startup warmup in its first reply measurement. With
readiness respected, a simple warm answer measured approximately 0.7 seconds to
first server audio. App requests remained roughly 8–11 seconds in the tested
baseline. These exclude microphone, STT, network and speaker latency, and are
individual observations, not percentile guarantees.

A later baseline run also failed the persisted-memory assertion despite a spoken
acknowledgment. Thus it is not a fully passing benchmark. Reports now explicitly
include checks_passed, and assertion failures still exit nonzero. Faster replies
without the requested effects are failures, not performance improvements.

## Validation

- Backend unit suite: 543 tests; Ruff lint and formatting.
- Frontend: 41 unit tests, typecheck and production build.
- Browser: 34 checks; four layout checks repeated after the short-window ring fix.
- Real Gemini comparison samples and a text-debugger response completed.
- Cloud companionship simulation was attempted but hit Gemini quota errors.
- Local debugger retry encountered a CLI/SDK --connect-addr incompatibility;
  local inference and effects were exercised through the SDK benchmark instead.
- Physical microphone, perceived voice warmth and echo/barge-in remain untested.
