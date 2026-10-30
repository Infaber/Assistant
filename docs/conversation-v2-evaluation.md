# Ariana 2.0 evaluation — 31 October 2026

## Implemented and objectively checked

The conversation guidance was shortened from 360 to 330 words. It now
favours everyday speech, concrete reactions, discussion without a practical goal,
reasoned disagreement and following an interrupted or changed topic. No random
response selector, emotion keyword detector or additional voice service was added.

Project progress keeps two dated previous summaries. Corrections remove prior
claims, forgetting/expiry cascade, and relevant recall can find a project through
its earlier milestone while returning the current summary separately. Startup does
not inject history. No automatic recording or periodic cloud summarization occurs.

The scheduler rechecks policy after I/O; user activity, quiet hours, expired leases
or an opt-out cancel queued speech. Existing consent, one-use claims, cooldowns and
unanswered guards remain. Optional recorded progress speech now requires a running
action, so it does not interrupt ordinary model conversation.

Final local validation: **438 pytest tests passed; 20 frontend unit tests and 12 WebKit browser tests
passed. Ruff lint/format, frontend type checking and the production build passed.**
After rebuilding/reopening the companion, one app process was running and both
local service health endpoints returned HTTP 200.
One existing google-genai/Python 3.14 deprecation warning remains.

## Conversation coverage and actual live runs

The checked-in dataset and matching LiveKit suite contain **22 multi-turn cases**:
boredom, venting, teasing, excitement, disagreement, serious discussion, topic
changes, short answers, quiet, unsaved-yesterday claims, project progress,
correction, temporary mood versus style, persistent settings, opinions,
vulnerability, unfinished discussion, honest AI identity, interruption repair,
Home Assistant during chat, unwanted automation and a longer shared idea.

These are prepared evaluation cases, not 22 claimed successful cloud conversations.
Project/light cases use isolated state and objective final checks. Text interruption
repair only tests following a replacement request, not microphone barge-in.
The previous cloud simulation attempt exhausted LiveKit's text-turn quota; the full
cloud suite was not rerun during this stage. CI includes the new suite and requires
available quota. No billing changes or source upload were performed.

A bounded direct **Gemini Live** comparison completed **eight turns**: two fictional
two-turn cases under the previous prompt and the first new draft. No microphone,
app tools or personal memories were involved. Eight nonempty audio files were
exported locally for human listening. SDK warnings about unsupported false-
interruption resumption on the evaluation audio sink were observed; this harness
is not a turn-taking or latency benchmark.

The actual agent debugger separately completed **five turns across two sessions**:
save rover, record heatsink progress, recall what changed, save sarcasm-off, then
recall both the preference and project after restarting. Real tools used temporary
SQLite/preferences files. The stored sarcasm setting persisted and the new session
recalled it correctly. Neither user's actual project memory nor style was changed.

## Before/after observations, including remaining weaknesses

For “University was brutal today”, the previous prompt produced:

> Sounds like it really took it out of you. What was the main culprit behind the
> brutal day? Lectures, deadlines, or just everything all at once?

The first new draft produced:

> Brutal how, exactly? Long lectures, endless assignments, or just one of those
> days where nothing clicked?

That is shorter but still a menu-like question. In the next turn the draft also
said “That sounds incredibly draining”. This was not a clear naturalness win.
Guidance was refined to react to the absent teammates rather than label emotions.
A fresh final debugger run completed two more turns, with no tools:

> Oof, I'm sorry to hear that. What happened? Was it exams or just one of those
> overwhelming days?

Then, after the user described doing all the group work again:

> Seriously? Again? That is beyond frustrating. You shouldn't have to carry the
> whole team every single time.

The final second reply is more direct; the first still adds a menu question.
This remains an evaluation finding, not something unit tests prove solved.

In the disagreement comparison, the draft challenged blanket automation with
human judgment, nuance and creativity, but still explained “I'm here to chat”
when challenged. The old version sometimes made the sharper joke. The sample
is too small to claim a consistent humour or style improvement. We avoided adding
more and more rules to chase individual phrases.

The strongest observed gains are continuity across a restart and keeping recorded
speech out of casual chat. Perceived warmth, wit, accent, rhythm and vocal quality
still require listening. No human listening score is claimed.

## Voice configuration review

Retained Gemini Live's server turn detection and native interruption signals;
no unsupported affective flags, artificial pauses, new STT/TTS stack or extra
cloud detector was introduced. For realtime server detection, most generic SDK
interruption knobs do not apply. References reviewed on 31 October:
[LiveKit turns](https://docs.livekit.io/agents/logic/turns/),
[Gemini plugin](https://docs.livekit.io/agents/models/realtime/gemini/), and
[Google Live practices](https://ai.google.dev/gemini-api/docs/live-api/best-practices).

## Practical listening test

1. Use the usual Mac microphone/speakers. Say “University was brutal today”, add
   the group-project detail, and listen for generic sympathy, unnatural vocabulary,
   unwanted advice and repeated questions. Try boredom, good news and an opinion.
2. Discuss an arbitrary idea for 15–20 minutes, change topics abruptly, give a short
   answer and pause. Check she follows the thread and permits quiet.
3. Ask for a long explanation, interrupt with “Stop—just one example”, and verify
   playback yields and uncertain actions are not repeated. A physical microphone
   test is necessary; the text debugger cannot verify this.
4. During chat, request a light change. Verify concise grounded confirmation and
   a return to conversation. Optional progress clips should occur only during tools.
5. Save a project update and a lasting style setting; reconnect and ask what changed.
   Check temporary “not tonight” moods were not stored. Review/forget the test topic.
6. With explicitly enabled check-ins, arrange a welcomed follow-up. Test quiet hours,
   disable initiative while one is queued, and leave one unanswered. Check silence
   and no repeated prompts. Real camera greetings need a separate Mac test.

No new dependencies or macOS permissions are required. Existing app and microphone
permissions remain necessary for their respective features. See the reproducible
comparison command in [development](development.md).
