# Repeatable Mac listening acceptance

Status: **not executed in this coding session**. Run only after explicitly choosing to install/test the candidate and granting microphone permission yourself. Use an isolated test setup; avoid personal integrations and production actions. Do not enable transcript/audio persistence by default.

## Record the setup

Record commit, dependency lock versions actually installed, macOS version, engine/model, microphone/output device, headphones versus speakers, room noise, distance, configured voice, Local speed, Gemini endpoint silence and network. Record numerical outcomes and case IDs. If recording audio for acoustic measurements, obtain consent, keep it local and delete it after evaluation.

First repeat all automated checks with the updated lockfiles. Browser component fixtures do not prove LiveKit transport or acoustic behavior.

## Wake and lifecycle

| Trial | Repetitions | Record / acceptance condition |
|---|---:|---|
| “Hey Ariana”, pause until Listening, then “What is seven plus five?” | 20 quiet + 20 normal room noise | Detection count / attempts; activation-to-Listening median/p95; lost leading words / completed commands. Goal: zero lost words in supported two-step flow. Set a wake detection target before testing, e.g. at least 19/20 quiet trials. |
| Wake phrase immediately followed by command | 10 | Count lost initial words. This is a known unsupported flow, not a release-pass criterion or proof of pre-roll. |
| Non-wake speech / TV-like noise | 15 minutes | False wake count per hour (rate is exploratory over this short interval). Record conditions; no arbitrary claim of perfect speaker authentication. |
| Cancel while Activating; then activate again | 10 warm + 5 cold | Zero late microphone publications, duplicate commands or new session muting from the canceled attempt. |
| Revoke mic permission during activation; disable wake during pending activation | 5 each | Activation stays canceled, no automatic re-grant, clear recovery guidance. Explicitly re-enable only when ready. |
| Sleep, wake, network loss and reconnect while activating/listening | 5 each | No unexpected capture restart; bounded recovery; explicit unmute/wake required as appropriate. Verify both UI and actual OS capture indicator. |
| Two minutes of speech; long thinking/output; then quiet | 3 each | No 90-second cutoff while busy. Standby around 90 seconds after the last detected activity. |
| Quiet speech and 30-/60-second thinking pauses | 5 each | No premature standby or systematic dropped quiet speech. Separate endpointing from standby failures. |
| Sustained fan/TV noise | 10 minutes | Record whether capture remains active. Noise can currently extend the activity window indefinitely; manual mute must remain effective. |

Standby means the room microphone is muted. Separately check whether local wake detection is enabled; do not infer that all capture stopped.

## Interruptions and latency

Use neutral explanations without tools. Interrupt with “stop”, “wait”, “no”, “yeah, but use the other example”, and a replacement question. Also test an acknowledgment-only “yeah”; count false interruptions separately rather than treating every short word as ignorable.

- At least 30 trials per engine, including five rapid successive corrections.
- Measure **stop-to-silence** from the first audible interruption syllable to the last assistant sound. Record median, nearest-rank p95 and maximum; agree a target before the test, e.g. median ≤300 ms and p95 ≤700 ms. These are proposed acceptance targets, not measured results.
- Count outdated responses continuing, canceled speech resuming without request, duplicate responses and ignored replacement turns. Goal: zero action replay and zero unsolicited restart of canceled Local speech.
- Then explicitly ask “continue”. Check contextual continuation without claiming unheard text was already spoken.
- For **first audio**, use at least 30 comparable short questions. Measure from the final audible user phoneme to the first audible assistant phoneme. Report median/p95 separately for warm Normal, warm Local and cold Local. Agree engine-specific targets before measuring; do not mix cold starts with warm latency.
- Compare SDK diagnostics with acoustic measurements; never substitute `sdk_user_end_to_speaking_state` for sound at the listener's ear. Small samples and different questions are not a rigorous performance comparison.

## Continuity and action safety

Run at least a 20-minute / 40-turn conversation per engine:

1. Ask for two rover sensor options; follow with “the second one”, “why?” and several short replies.
2. Leave an unfinished thought, pause and clarify it. Check that the clarification supersedes the earlier assumption.
3. Discuss two unrelated topics, then return to the rover. Check options and corrections against your private notes.
4. Interrupt an explanation; ask a new question; request continuation later. Count correct referents / total referential probes.
5. Switch engines with transfer off, then with a fresh explicit opt-in. Check that text continuity is bounded and media, tool instructions and pending approvals do not become fresh authority.
6. Use the repository's isolated action fixtures to create an uncertain receipt. Interrupt/recover and ask to discuss it. Require unchanged receipt and **zero replay**; never use a real device action just to test continuity.

Suggested continuity criterion: all ten planned referential probes resolved correctly or clarified honestly, no invented memory, no historical approval accepted. A text simulation can help assess this, but it does not prove audio quality.

## Voice comparison and expression

Save explicit A/B configurations. Load A, save, end and reconnect deliberately; verify the active snapshot. Play each of the five samples once, waiting at least 15 seconds between samples. Repeat for B using the same hardware/volume and listening conditions. Native output can vary and can enter session history.

Score clarity, naturalness and contextual appropriateness from 1–5. Record interruption success and synthesis glitches separately. For Local, repeat at 0.8×, 1.0× and 1.2×; verify the rate actually changes and remains intelligible. Test configured-default reset after saving an override, and verify the active voice only changes after reconnecting.

Serious speech should not acquire forced amusement. Hesitation/laughter are not exact controls. Independent mid-input spoken backchannels are **not implemented**; visual listening cues do not count as passing that requirement. Do not mark acknowledgment handling as solved because one sample sounded natural.

## Results sheet

| Engine/config | Wake correct/attempts | Lost-word trials | False interrupts/trials | Stop median/p95 ms | First audio median/p95 ms | Continuity correct/probes | Action replays |
|---|---|---|---|---|---|---|---|
| Normal A | Not run | Not run | Not run | Not run | Not run | Not run | Not run |
| Normal B | Not run | Not run | Not run | Not run | Not run | Not run | Not run |
| Local A | Not run | Not run | Not run | Not run | Not run | Not run | Not run |
| Local B | Not run | Not run | Not run | Not run | Not run | Not run | Not run |

Record failures as failures, including conditions and reproducible steps. Do not count scripted providers, fixture replies or text-only simulations as acoustic evidence.
