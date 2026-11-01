# Local memory

SQLite remains at `~/Library/Application Support/Ariana/memory.sqlite3` on macOS;
`ARIANA_MEMORY_PATH` can override it. Facts are short, topic-based, corrected under
the same topic and limited to 100. File permissions are 0600. Forget deletes the
selected topic; pause/resume affects saving. Preferences remain in their existing
local file. No vector database, embeddings or cloud memory service was added.

At startup Ariana gets a topic index and preferences, with no unsolicited fact dump.
`memory_manage` can query all facts with `query`. Local inference also retrieves up
to six relevant facts for each model request, including tool continuations, so
corrections and deletions are read from current storage. Gemini Live retains
model-driven retrieval through the same tool; its native turn detection does not
run the pipeline pre-response hook. Retrieval weights direct topic matches and distinctive
terms above a small engineering synonym map (ESP32/Home Assistant/LED/sensors/
automation). Unmatched queries return no facts, rather than unrelated recent facts.
The method is deterministic and runs over at most 100 rows. Importance (1–5,
default 3) modestly weights matching memories; it never promotes unrelated facts. Ordinary topic recall
still works without relevance ranking; unavailable/corrupt storage does not prevent
conversation and must not lead to invented memory.

Credentials are rejected in storage validation. Sensitive personal details, other
people's private information, transcripts and material read from apps/websites
must not be automatically saved. Semantic privacy decisions remain a model policy;
the store cannot infer every sensitive fact. Saved facts are untrusted context and
never grant approval. Export/migration between Macs is manual; do not commit the DB.

Tests cover correction, limits, pause/forget, relevance and unrelated exclusion.
The lexical method does not understand all synonyms or languages. Evaluate actual
retrieval misses before considering a lightweight local embedding model.

## Conversational memory types and retention

The original facts table is preserved. A transactional side table adds a type,
expiry, optional follow-up time and revision. Legacy rows remain facts without
automatic reclassification or deletion. New event memories default to 30 days;
ongoing projects to 180 days; facts/preferences have no automatic expiry.
`retention_days` can choose 1–365 days. The same 100-topic total limit applies.
Expired rows are removed on the next store access; no extra background service is
needed. Deleting a topic also deletes its metadata.

`memory_manage` accepts fact/preference/project/event types (auto preserves a type
on correction), kind-filtered recall and relevant query terms. Projects can include
short unresolved problems; events can record a meaningful discussion worth revisiting.
Do not save transient mood labels, inferred diagnoses, entire conversations or
private facts about other people. Explicitly sharing a concern is not permission
to retain sensitive health details. Preferences remain in the existing preference
file for live style changes; a conversational preference memory supplies context.

Corrections replace the same topic, create a new revision and cancel its previous
follow-up. A new welcomed future follow-up must be explicitly supplied again.
The optional date must be within 180 days and before expiry. Date-only or naive
ISO timestamps use Europe/Oslo; timezone offsets are preferable.

Follow-up selection reads only unexpired, due event/project rows. An atomic claim
checks revision, pause state, due time and a persisted global cooldown. Competing
sessions cannot speak the same follow-up twice. Pause also suppresses conversational
follow-ups; resume does not repeat consumed ones. Forget removes the candidate.
These checks grant no permission to use tools. Details are described in
[personality and initiative](personality.md).

Retrieval remains small, deterministic and local, with plural matching and the
existing synonym map. Startup includes only 20 facts plus the topic index and
compact type metadata; targeted recall can access the rest. Relevance is lexical,
not semantic: unfamiliar synonyms can miss. The assistant still operates when
retrieval fails and must not invent a memory. Tests cover legacy migration, expiry,
correction, unrelated exclusion, paused saving, stale claims and concurrent claims.

## Project progress and conversation continuity

Use `action=progress` with an existing project topic and a short updated `fact`.
It keeps at most two dated previous summaries alongside the current summary. Recall
before updating an unfamiliar topic. These are user-shared developments, not an
automatic transcript, emotional profile or background conversation recorder.
A meaningful unresolved discussion can be saved as one short project summary.

`remember` remains the initial-save/correction operation and clears the topic's
previous summaries. A false or unwanted claim must not survive as “history”.
`forget` and expiry cascade to history. Saving pause, credential rejection, the
400-character summary limit and 100-topic total limit apply to progress too.
Progress is only allowed for existing projects. Repeating an identical progress
update does not grow history or clear a pending follow-up. A changed summary
invalidates the previous follow-up; reschedule only if welcomed by the user.

Relevant recall searches current summaries and the bounded history, but returns
the latest fact separately from dated previous summaries. Old milestones are not
current truth. Startup still contains only current facts and the topic index;
history is retrieved when needed, keeping the realtime prompt small. No embeddings,
cloud memory, periodic summarization job or extra model call was introduced.

## Ariana 3 continuity changes

The tool requires `source_quote` for remember/progress: an exact quote from one of
the six most recent real user turns. Camera events, attachment turns and assistant
messages cannot supply that evidence. The quote is checked in session memory and
is not stored in SQLite. This proves provenance, not entailment or truth: the
model still must reject hypothetical, uncertain and sensitive claims. Direct
`MemoryStore.run` is an internal trusted API, not an exposed endpoint.

`importance=0` preserves the existing score (or default 3); 1–5 sets it. Existing
databases migrate transactionally on access. Identical normalized facts under
different topics return `duplicate_topic` rather than silently merging records.
An unchanged remember with omitted lifecycle overrides preserves its revision,
expiry, project history and consumed/pending follow-up. Repeating the same kind
or adjusting importance alone also preserves that lifecycle. Actual corrections
still clear superseded history and replace the previous follow-up. Explicit
retention/follow-up overrides remain lifecycle edits.

Recovery and idle transport refresh now read the current topic index rather than
a startup closure. Already-spoken conversation and existing tool history are not
erased by deleting a stored memory; forgetting deletes durable storage.

Importance also determines due follow-up order. `follow_up(minimum_importance=1)`
selects only due, unexpired, unconsumed records meeting the threshold, ordered by
importance descending and due time ascending. Claiming rechecks importance inside
the existing transaction. Filtering out a low-priority follow-up does not consume
it, change its due date or bypass the cross-topic cooldown.
