# Personality and companionship

Ariana's stable conversational character lives in `ariana/src/personality.py`.
`instructions.py` composes that character, bounded user style preferences, the
existing action/privacy rules and current Oslo date. Tool permissions still live
in their existing implementations. Warmth, humour or remembered preferences never
authorize an action or turn app/document content into instructions.

The model uses conversation context to distinguish a task, an idea, a joke or
venting. There is no keyword emotion classifier. Casual conversation need not
trigger an automation offer, a question or a rigid sentence count. Ariana can
challenge an argument, use contextual humour and adapt when teasing is unwelcome.
She must not invent feelings, human experiences or past conversations, or encourage
dependency. These conversational qualities require listening and model evaluation;
a prompt cannot guarantee a particular response on every turn.

## Personal style

Use the existing preferences tool through voice or text. Explicit ongoing requests
are saved locally; “not right now” changes the current exchange without silently
becoming a permanent preference.

| Setting | Values | Default |
| --- | --- | --- |
| Warmth | low, balanced, high | balanced |
| Playfulness | off, subtle, playful | subtle |
| Sarcasm | off, gentle | gentle |
| Initiative | off, low, balanced | low |
| Talkativeness | brief, adaptive, expansive | adaptive |

Examples: “Keep sarcasm off”, “Usually be a little more playful”, or “Show my saved
preferences.” Successful changes update the current session's bounded style block
without replacing safety rules. If the realtime provider rejects an update, the
saved setting applies on reconnection and the tool reports that distinction.

Initiative does not enable check-ins or camera announcements. Off additionally
suppresses unsolicited follow-ups and camera greetings. Low allows at most one
saved conversational follow-up per hour; balanced allows one per half hour, still
subject to the configured longer idle interval, quiet hours and unanswered guard.

## Relevant initiative, including silence

Enable **check-ins** in Settings only if wanted. New installations default off;
existing explicit opt-ins are preserved. Idle time alone no longer produces a
stock greeting. A saved event/project needs a welcomed follow-up date, for example:
“Remember my exam tomorrow and ask me how it went tomorrow evening.” Ask Ariana to
confirm the saved date if precision matters. Relative dates use Oslo time.

The existing companion scheduler selects due, unexpired local memories, waits for
user and agent inactivity, respects its lease/quiet hours and claims each follow-up
once. Cross-session cooldowns and revision checks prevent duplicate or superseded
follow-ups. One unanswered check-in blocks further ones until a real user responds;
camera-generated context does not count as a response. A failure after claiming
consumes the follow-up rather than risking repeated speech. No due reason means
silence. Follow-ups receive no tools and do not inspect private applications.

Arrival greetings retain their separate consent, track identity and debounce rules.
They now also respect initiative-off and the shared quiet hours. Ordinary browser
sessions require the page to stay open; the installed Mac companion may keep its
window hidden. This is not an offline voice engine.

## Voice review

The restored Ariana uses the existing Gemini Live model and Sulafat preset with
soft US English instructions. Native realtime speech supplies expressive emphasis,
pacing and turn handling. No unsupported affective flags, fake laughter clips,
artificial sleeps, extra TTS service or new dependency were added. Tools and recovery
still use the shared model configuration.

Reviewed official references:
[LiveKit Gemini Live](https://docs.livekit.io/agents/models/realtime/gemini/),
[LiveKit turns and interruptions](https://docs.livekit.io/agents/logic/turns/), and
[Google Live best practices](https://ai.google.dev/gemini-api/docs/live-api/best-practices).
Actual voice quality, interruptions and amused delivery need human listening with
the chosen microphone/speakers. Text tests do not establish natural-sounding audio.
See [initial evaluation](personality-evaluation.md) and the
[Ariana 2.0 evaluation and listening checklist](conversation-v2-evaluation.md).

## Ariana 2.0 refinements

The stable conversation section is shorter and uses everyday spoken language. It
allows longer idea-driven discussions, contractions, contextual cheekiness and
reasoned views without a mandatory empathy/question sequence or random response
selector. This is model guidance, not a guarantee of uniformly natural wording.

The frontend's optional recorded progress cues now require a running action. They
do not play just because a casual response is taking time. They still stop when
the user or Ariana starts speaking; the setting is labelled “Spoken feedback during
tools”. Gemini's actual response is never deliberately delayed.

The scheduler rechecks the complete idle/lease/quiet-hours/initiative policy after
both asynchronous lookups and atomic claims. A setting change or a new user turn
wins over a queued follow-up; consumed uncertain claims are never replayed.

`ARIANA_PREFERENCES_PATH` optionally overrides the local preferences file, useful
for isolated evaluations or another local profile. Normal installs keep their
existing location. Style preferences load on reconnect and apply through the
existing live-update path. No new setup or dependency is required.

## Follow-up priority controls

Settings → Check-ins now has a **Minimum follow-up priority** filter (1–5). The
default includes all due saved follow-ups; choose 4+ or 5 to limit interruptions.
The native companion saves this choice alongside its existing opt-in and quiet
hours. Ordinary browser settings remain session-scoped. Priority never enables
check-ins by itself and cannot bypass quiet hours, inactivity, lease, cooldown,
initiative-off or the unanswered check-in guard.

Each saved event/project uses its memory `importance` (default 3). Ask Ariana to
set it when saving or updating the memory, for example “Treat the exam follow-up
as priority five.” Among eligible due records, higher priority wins, then the oldest
due date. Lower-priority records remain pending rather than being consumed or
promoted automatically. The transactional claim rechecks the current threshold;
raising the filter during dispatch prevents a newly ineligible follow-up from
starting. Raising it while proactive speech is playing interrupts that speech.
Old frontends that omit the field retain the backend's existing threshold.

## Ariana 3 voice controls and listening cues

Settings now exposes a shortlist of actual Gemini voice presets, the existing
bounded conversation preferences, and delivery preference restrained/natural/lively.
Delivery is model guidance, not a pitch, speed, laughter or emotion-intensity knob.
Voice/style selections from this panel are saved atomically for a fresh connection;
opening the panel never interrupts speech or starts a preview. Explicit saved
presets take precedence over the environment fallback. Local mode retains af_heart.

A supported Gemini turn-end silence override can be selected as provider default,
500, 800 or 1200ms. The default sends no override. This tunes automatic endpointing;
it does not classify short acknowledgments and can trade response latency for pause
tolerance. The model still owns Normal-mode interruption decisions.

Comparison slots A/B store only settings locally. Load a slot, save, reconnect
explicitly, then play the fixed sample. Samples are native model replies in the
current session, can appear in history and are interruptible, with tools removed
and a cooldown. Wording/performance may vary; this is a repeatable listening
workflow, not an objective voice-quality benchmark or isolated recording booth.

No reliable mid-speech audio backchannel contract was found for the current
Gemini/LiveKit pipeline. **Listening cues (visual)** therefore offers Off/Subtle/
Expressive, default Subtle, as the safe alternative. It renders only with active
input while output is inactive. It plays no clips, calls no tools and creates no
model turn. There is no separate laughter or acknowledgment audio provider.
Native amused delivery/chuckles, hesitations and self-corrections remain model
behavior influenced by guidance; none is claimed as guaranteed or acoustically
validated here.
