# Response timing and reliability

Ariana keeps numerical timings per session without transcripts, app arguments,
result text, provider IDs or credentials. No external telemetry service or idle
polling was added. Existing application/provider logging is separate; do not share
private logs.

`ariana.performance` log entries report milliseconds. The read-only `task_status`
tool includes recent timing averages/maxima alongside action receipts. The buffer
retains the latest 100 samples, not 100 conversations. Pending SDK tool measurements
are capped at 64 and cleared on session close. Missing metrics are omitted.

- `local_router`: local selection of relevant app tools.
- `tool_execution`: SDK dispatch to completion, including failure/cancellation.
- `tool.<name>`: additional integration-wrapper timing. This overlaps SDK timing;
  do not add both together.
- `llm_node_ttft` / `llm_node_ttfs`: first model token / first sentence for speech.
- `tts_node_ttfb`: first generated speech chunk.
- `transcription_delay`, `end_of_turn_delay`, `e2e_latency`: SDK speech/turn metrics
  where available. Text-only input does not provide microphone latency.

Server audio timing excludes network delivery and physical speaker latency.
A finished call or elapsed time never proves an app write succeeded. Existing
verified receipts establish outcomes.

## Repeatable everyday benchmark

From the repository root, after configuring/installing Local mode:

```sh
uv run --project ariana --extra local-voice --extra wake-word python \
  ariana/scripts/benchmark_everyday.py --output /tmp/ariana-everyday.json
```

This opt-in real-model test uses configured local Ollama and local speech, fixed
public prompts, temporary empty SQLite memory/preferences, fake lights/Spotify,
and a fictional calendar. Other app tools are blocked, including nested Safari
tools. It never opens a microphone or changes a real app. Assertions require one
light command, one pause, one calendar read, a stored fictional ESP32 memory and
correct conversational recall. The model chooses tools; an extra dispatch or
wrong answer fails the check. Recall within this conversation does not establish
cross-session memory quality.

The private JSON (0600) contains generated replies; keep it outside Git. Run when
other inference jobs are stopped. Turn timing excludes startup. Measure cold/warm
starts separately before claiming percentile improvements.

## M4 Mac mini, 16 GB: 31 October 2026

Two sequential six-request runs used `ariana-local:4b`. The second included router
warmup before readiness. These individual observations are not a controlled speed
guarantee: cache and generated wording affect results.

| Request | First run: first audio | Router warmed: first audio |
| --- | ---: | ---: |
| Two plus two | 8.52 s | 4.96 s |
| Fictional desk lights on | 8.94 s | 9.00 s |
| Fictional Spotify pause | 6.66 s | 6.59 s |
| Fictional calendar | 8.90 s | 9.09 s |
| Store fictional ESP32 memory | 5.39 s | 5.62 s |
| Recall that controller | 9.59 s | 9.75 s |

The second run's router averaged 266 ms (maximum 777 ms). Fake app calls averaged
4 ms; first model tokens averaged 2.46 s and first speech chunks 0.91 s. These
metrics overlap and cannot be added to calculate full response latency. Local
replies are still slow, and the 4B model sometimes repeats closing phrases despite
its instructions. This pass does not claim otherwise.

## Recovery and verification

Retryable Local errors now publish `recovering` without marking the selected
engine permanently failed, switching to Google or re-submitting a turn. The SDK
owns provider retries. Terminal errors still require explicit user recovery.
Failed/cancelled startup cancels sibling warmup tasks. Router warmup discards its
classification and never executes app tools.

Regression tests cover verified Safari work followed by a Notes timeout or
cancellation: the Safari receipt stays verified, the write becomes uncertain, and
a second dispatch is blocked. Existing approval, revision and snapshot guards stay
active.

Validation: 485 Python tests, Ruff lint/format, frontend type checking, 24 frontend
unit tests, 13 WebKit tests and the production frontend build passed. Native Mac state tests and isolated process
tests passed: two crashes recovered, duplicate start prevented and shutdown stopped
retries. The real Local debugger completed a greeting and fictional memory
save/recall, then stopped. The Normal debugger also answered a greeting and correctly explained
that a timed-out Notes write must be inspected before retrying, without executing
any tools. Cloud simulations were blocked by exhausted simulation
quota and are not counted as passed.

Physical microphone/speaker latency, echo, actual sleep/wake and Wi-Fi loss still
need human acceptance testing. State simulations do not prove these physical flows.
No new dependencies, permissions or environment settings are required.
