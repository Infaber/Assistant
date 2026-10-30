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
