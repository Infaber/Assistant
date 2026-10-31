# Local engine evaluation — 31 October 2026

## Model choice on the M4 Mac mini

The Mac has 16 GB unified memory. Three Ollama quantizations were downloaded and
actually queried. A matching six-prompt public baseline covered religious ethics,
political analysis, mildly profane humour, fictional political dialogue, calendar
arithmetic and unknowable information. No personal memories or private app data
were included in this public comparison. Dolphin 3 was researched but not run.

| Model | Observation | Measured generation speed |
| --- | --- | --- |
| Huihui Qwen3 4B | Discussed challenging subjects without unnecessary refusal, but incorrectly said 25 available minutes exceeded a 30-minute walk | About 36 tokens/s |
| Huihui Qwen3.5 4B | Discussed the subjects, but made time-arithmetic contradictions and confused fictional roles | About 31 tokens/s |
| **Huihui Qwen3 8B v2** | Correctly rejected the walk, acknowledged it could not know a secretly chosen number, and gave more grounded fictional dialogue | **20.2–20.7 tokens/s** |

The selected model's six completions took approximately 1.48–6.72 seconds each.
These are generation measurements, not microphone-to-first-audio latency. Its
observed model allocation at 16K context was 5,588,008,303 bytes; this excludes
speech engines, Python, macOS and other applications. Cold loads and the local tool
router add latency. Smaller models remain available through explicit configuration.

None of the three showed unnecessary refusals in this small legitimate test set.
That does not establish universal freedom, factual accuracy or safety. Humour was
weak, requested profanity was inconsistent, and the selected model sometimes used
generic helpful-assistant wording, formatting or emojis despite personality rules.
It shares Ariana's personality configuration, but it does not match Gemini's
naturalness reliably. Two public Gemini baseline checks also answered the arithmetic
and uncertainty questions correctly; this was not a full paired voice comparison.

The reproducible runner is `ariana/scripts/evaluate_local_model.py`. It uses only
literal public prompts and loopback inference. Raw local runs remain outside Git.
No private memory export or personal conversation corpus is committed.

## Integration checks actually performed

- An actual LiveKit Cloud room started with the local pipeline. Its connected guest
  invoked the authenticated mode RPC to switch to Gemini, then back to Local.
  Both handoffs returned backend-confirmed `ready` and the expected model IDs.
  This exercised real room transport and pipeline handoffs, not a mocked UI toggle.
- An SDK-level handoff test additionally used a fake Home Assistant endpoint.
  A light request produced exactly one service call; completed work was not
  replayed. Returning to Gemini received fresh context without the local test word.
  No real light or personal Apple app was changed by that test.
- Synthetic audio passed through local VAD, Whisper, local generation and Kokoro.
  The initial complete synthetic question/answer round trip used the 4B candidate;
  the final selected 8B was tested separately for generation, tools and handoffs.
- A separate two-sentence Kokoro/Whisper check generated 3.02 seconds of audio in
  about 1.94 seconds and transcribed it in about 0.34 seconds. This confirmed the
  whole utterance survived the native callback. It is not a live microphone test.

These tests exposed and fixed three real issues: speech truncation from the native
TTS callback return convention; a 4K context allocation despite native warmup; and
readiness published before room connection. Regression tests cover those boundaries.

## Automated checks

Pytest covers mode validation/authentication, duplicate switches, pending actions,
failed preparation, local-only recovery, missing credentials, tool visibility,
loopback enforcement, unavailable/cloud-backed models, speech cancellation and
existing integrations. Frontend checks cover signed dispatch metadata, unavailable
local startup, persistence boundaries, selector states and existing workflows.

Final checks passed: **468 pytest tests**, Ruff lint and formatting, frontend type
checking, **24 frontend unit tests**, **13 WebKit browser tests**, and the production
frontend build. One upstream google-genai Python 3.14 deprecation warning remains. Cloud simulation scenarios for
voice-switch claims and hidden fallback are included in the existing CI workflow.
They were **not run successfully locally**: the available simulation quota was
exhausted. Real model checks, SDK tests and the real room RPC test described above
were performed separately; none is described as a passed cloud simulation.

## Still requiring human testing

Physical microphone recognition, speaker quality, echo/self-interruption, real
barge-in, a sustained 20-minute conversation, wake/sleep with Local active, and
personal Apple app workflows need testing in the installed companion. No measured
score for those is claimed. Start with a normal conversation, interrupt a long
answer, then try a read-only tool before a confirmed write.

Local image analysis is deliberately unavailable. Local speech is English-focused.
The rolling context is bounded, so long unsaved conversations can lose details.
Saved SQLite memory and action receipts use the existing shared implementations.
LiveKit Cloud still transports room data; this is local inference, not fully offline
operation. See [setup, privacy and limitations](local-ai.md).
