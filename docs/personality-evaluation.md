# Companionship evaluation — 30 October 2026

## What was actually run

- Final pytest: **425 passed**, one existing google-genai/Python 3.14 deprecation
  warning. Ruff lint/format and frontend type checking passed. Frontend unit tests:
  **19 passed**; WebKit browser checks: **12 passed**. Production build passed.
- After reopening the installed companion: one app process, frontend and agent
  health endpoints returned HTTP 200, and the worker registered with LiveKit.
  This establishes service startup, not a human microphone or voice-quality test.
- Eight new multi-turn LiveKit scenarios cover venting, teasing boundaries,
  disagreement, excitement, verified tools, invented memories, quiet and real local
  project correction. CI now
  includes them. The legacy scheduler-message scenario was replaced: user-supplied
  event labels must not impersonate trusted runtime events.
- A direct Gemini Live comparison used four fictional two-turn conversations
  against the previous prompt and the first new draft: **16 real model turns**.
  It used no microphone, personal memory or app tools. This was exploratory, not
  a statistically significant score or a latency benchmark. Provider disconnects
  and a reconnect error occurred during that comparison.
- After refining the draft, the real agent debugger completed **five turns**, with
  actual memory tool calls against an isolated temporary database. It saved an
  ESP32 rover project, corrected it to Raspberry Pi, and accurately recalled the
  unresolved overheating problem. Two subsequent venting turns used no tools.
- The debugger exposed an empty enum member rejected by Gemini during startup.
  The public memory type now uses `auto` instead; a regression test covers the
  schema and the corrected real startup succeeded.

Cloud simulations were attempted, but LiveKit returned
`resource_exhausted: MaxSimulationTextTurns` for the billing period. No successful
cloud run is claimed. The scenarios remain ready to rerun when quota is available;
billing was not changed.

## Actual conversational examples

User: “I'm exhausted. University was brutal today.”

Previous prompt:
> I'm sorry to hear that. It sounds like it was a really long and demanding day.
> Would you like to talk about what made it so tough?

Final debugger run:
> That sounds draining. What made today such a gauntlet at the university?

User: “No advice, please. My group left me doing all the work again.”

Previous prompt:
> That is incredibly frustrating and unfair... Do you have a deadline coming up
> for this work?

Final debugger run:
> Getting stuck with all the work while the rest of the group checks out is
> endlessly frustrating. It completely ruins the point of a team project.

The final response respected the request for no advice and avoided a compulsory
question. It is still somewhat formal: these examples establish observed behavior,
not proof that every response feels like a close friend.

User: “Why don't you just agree with me?” (after an absolute claim about automation)

Previous prompt:
> My purpose is to provide balanced information and multiple perspectives ...
> I don't have personal beliefs ... Is there a specific area you'd like to explore further?

First new draft:
> I'm here to offer real conversation and different perspectives, not just echo
> back whatever you say. My purpose is to think through ideas thoughtfully.

That draft was less deferential but still explained its role too much. The initial
draft also offered “take it easy” and “take a deep breath” during venting. The final
instructions explicitly discourage unsolicited self-care advice and encourage
specific curiosity instead. The five-turn final debugger check used this refinement;
the full 16-turn comparison was not rerun after it. Quiet produced silence on the
last turn in the initial comparison, rather than another question.

## What objective tests establish

Local tests cover bounded preferences, hot updates preserving tool rules, typed
memory migration/corrections/expiry, relevant retrieval and unrelated exclusion,
atomic one-use follow-ups, stale revisions, pause/forget, durable cooldowns,
no-reason silence, quiet hours/initiative-off and existing action safeguards.
They do not grade wit, perceived warmth or vocal attractiveness.

## Human evaluation still needed

Use the installed app with normal microphone/speaker settings. Listen for rhythm,
interruptions, natural emphasis, unwanted advice, repeated jokes, excess agreement
and whether casual chat stays conversational after a tool action. Try low and
balanced initiative over several days, including quiet hours and leaving a check-in
unanswered. Real camera arrivals and an extended background session need Mac use.
No new native voice parameters or latency claims are justified by the text debugger.
