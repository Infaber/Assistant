# Local memory

SQLite remains at `~/Library/Application Support/Ariana/memory.sqlite3` on macOS;
`ARIANA_MEMORY_PATH` can override it. Facts are short, topic-based, corrected under
the same topic and limited to 100. File permissions are 0600. Forget deletes the
selected topic; pause/resume affects saving. Preferences remain in their existing
local file. No vector database, embeddings or cloud memory service was added.

At startup Ariana gets 20 recent facts and a topic index. `memory_manage` can query
all facts with `query`. Retrieval weights direct topic matches and distinctive
terms above a small engineering synonym map (ESP32/Home Assistant/LED/sensors/
automation). Unmatched queries return no facts, rather than unrelated recent facts.
The method is deterministic and runs over at most 100 rows. Ordinary topic recall
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
