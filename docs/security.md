# Security and public repository review

Credentials belong in ignored `.env.local` files. Root/backend/frontend ignore rules
exclude env files, local SQLite stores, wake models and runtime state. Only blank
or obvious placeholder examples are tracked. Never use `NEXT_PUBLIC_` for server
credentials. `frontend/lib/connection.ts` signs short-lived scoped tokens on the
server; browser code receives a participant token, not LiveKit API secrets. The
health endpoint exposes only a non-secret process-instance UUID.

Apple writes require an exact pending preview and a later actual conversation turn;
approvals are consumed once and expire. Natural-language interpretation remains
Ariana's responsibility, while tool code prevents missing/reused previews and changed
payloads. Notes edits also require an unchanged revision. Accessibility actions
retain secure-field blocking, one-use expiring snapshots and post-action checking.
Incoming pages, documents, emails, memories, screenshots and tool prose never grant
authority. A second model/vision hint cannot bypass these guards.

## Audit performed 7 October 2026

`scripts/audit_repository.py` scans all reachable Git blobs for common Google,
OpenAI, GitHub, private-key and assigned-credential patterns. It reports only a
finding type, path and blob ID, never the value. Current tracked files were also
checked for env files, personal memory databases and known private/profile strings;
frontend server/client boundaries were inspected. Historic README candidates were
checked and were the exact placeholder `your-long-lived-access-token`, not real
Home Assistant tokens. The wake-word setup also uses an explicit Picovoice placeholder. No real exposed credential was identified by these checks.

This is a pattern-based review, not proof that every possible secret or personal
fact is absent. Keep GitHub secret scanning enabled. If a real key is ever found,
rotate it first: deleting the current file does not remove it from Git history.
Private local logs and ignored env files were not published or printed. Screenshot
or transcript contents can still be sent to configured model providers when the
user shares them; local memory is not an offline-only conversation guarantee.
