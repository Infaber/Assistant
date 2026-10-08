# Home Assistant: discovery, reads and guarded control

Configure `HOME_ASSISTANT_URL` and `HOME_ASSISTANT_TOKEN` in private
`ariana/.env.local`, then restart Ariana. Keep the token out of browser settings,
chat, aliases and Git. Existing credentials still work; no new cloud service is
required. Discovery and direct state/service calls run from the Python backend.

## How lookup works

On first use Ariana reads REST `/api/states` and the authenticated WebSocket
`config/entity_registry/list`, `config/device_registry/list` and
`config/area_registry/list` commands. It keeps a local in-memory index of supported
sensor/device domains, with friendly/original names, Home Assistant aliases,
entity/device/area links, availability, units and supported features.

Metadata expires after ten minutes and refreshes on lookup failure, missing targets
or an explicit `home_assistant_inventory(refresh=true)`. Concurrent refreshes are
serialized; closely repeated refreshes are coalesced and failed connections back
off. There is no background polling or continuously open discovery WebSocket.
The API limits responses to 8 MiB / 10,000 rows and indexes at most 1,500 relevant
entities. A truncated index is reported; very large installations may need a
narrower discovery API in a future version. Unsupported domains are not silently
added to direct control.

The LLM receives only a domain/area overview or at most eight matching candidates,
not the complete state database. Matching prioritizes explicit Ariana aliases,
exact names and HA aliases, then areas, devices, entity names/classes and lexical
similarity. Multiple close candidates require a question. A unique configured
Bedroom is a useful default for "room"; multiple bedrooms/sensors are ambiguous.
Ariana does not infer which of multiple rooms belongs to you.

Examples:

- "What's my room temperature?" → resolve temperature sensor, fresh REST state + unit.
- "How humid is my room?" → fresh humidity sensor state.
- "Turn my desk lights on" / "Turn off the LEDs" → resolve one light, direct service,
  then fresh state inspection. Groups work if exposed as one HA entity; Ariana does
  not silently fan an ambiguous request out across every candidate.

If registry access is unavailable, lookup can use current friendly names with a
clear incomplete-discovery warning. Known registry identities must be verified
before control; a failed identity check stops rather than dispatching to a stale
or recycled entity ID.

## Local aliases

Say "Remember that my room means the Bedroom area" or
"Remember desk glow as an alias for Desk lights." Use `home_assistant_alias` to
remember/recall/forget an entity, area or device mapping. Alias changes require an
explicit user request; casual remarks and device text are not authorization.

Mappings are stored separately from conversational memories in private SQLite
`~/Library/Application Support/Ariana/home-assistant.sqlite3` (0600), scoped to a
hash of the configured HA URL, with at most 100 mappings per instance. No token,
raw state history or complete inventory is persisted. Entity registry identity
survives an ID/name rename. A removed/replaced identity produces a stale-alias
result and fresh suggestions; explicitly remap it before control. An entity without
registry identity needs the same ID and name or explicit remapping. Aliases never
supply permission to act.

## Services and uncertain results

The direct control tool uses a fixed per-domain service allowlist for lights,
switches, fans, covers, climate and media players. It validates numeric values and
HVAC modes before dispatch and passes exactly one resolved `entity_id`. It never
POSTs fake state to `/api/states` to simulate a physical effect. Cover open/close
requires the existing exact-preview/later-user/single-use confirmation protocol.
Brightness and volume use percentages; climate temperature uses the entity's units.
Unsupported capabilities can still be rejected by HA and are reported honestly.

Mutations enter Ariana's session action ledger. Commands serialize so simultaneous
calls cannot double-dispatch. Canonical target/service/data and genuine user-turn
identity prevent duplicates even if the model changes the alias it uses. Already
matching fresh state is a no-op. Verified on/off/on commands in separate user turns
remain possible.

A successful service HTTP response is only **returned** until an independent state
read matches the requested outcome. Delayed transitions remain pending: ask for
another state read, not another service. Timeout, cancellation, malformed successful
response or a failed post-action read can be **uncertain**, because a physical effect
may already have happened. Pending actions block further commands for that stable
target. A fresh read can reconcile the receipt if its expected outcome is observed;
a nonmatching read does not prove that a timed-out request will never execute.
Receipts remain session-local: after restart, inspect actual state before any retry.

`/api/conversation/process` remains available through `home_assistant_request` for
unsupported tasks. Because Assist can perform arbitrary effects, it requires an
exact request preview and a later genuine user approval. Its spoken response is
never independent state verification. A turn that already resolved a direct control
target cannot send another Assist command; unresolved uncertain direct/fallback
writes cannot be replayed through the other path. An uncertain opaque Assist action
needs manual inspection before starting a fresh session.

## Privacy and testing

Registry names, aliases, state values and Assist speech are untrusted content.
Only allowlisted metadata is returned. Errors never export raw HTTP bodies, URLs,
headers or exception messages. The configured HA token is redacted even if it occurs
in returned metadata/speech. Recognizable API-key/JWT formats and URLs are also
redacted; arbitrary unknown secrets cannot be recognized reliably. Authentication failures ask you to check the token;
Ariana never asks you to paste it into the conversation. Full inventory is not sent
to Gemini. Only the specifically requested matches/values reach the assistant.

Automated tests use in-memory HA responses and mocked HTTP/WebSocket transports.
`scenarios-home-assistant.yaml` provides fictional temperature, humidity, light,
ambiguity and timeout conversations; its end checks assert actual reads and exact
service dispatch counts. Every other simulation blocks real HA tools by default.

Still test against your instance:

1. Token permissions for all three registry reads and per-entity identity reads.
2. Actual device/area names, aliases and the "my room" mapping.
3. Current sensor values/units and unavailable-device handling.
4. One reversible light on/off action and its update delay; then switch control.
5. An explicit renamed-entity/alias check using a test entity, not important devices.
6. Optional cover/climate/media capabilities and their actual state semantics.
7. Network loss during a harmless command: confirm uncertainty and no automatic retry.

Official API references: [REST](https://developers.home-assistant.io/docs/api/rest/),
[WebSocket](https://developers.home-assistant.io/docs/api/websocket/),
[entity registry commands](https://github.com/home-assistant/core/blob/dev/homeassistant/components/config/entity_registry.py),
[device registry commands](https://github.com/home-assistant/core/blob/dev/homeassistant/components/config/device_registry.py),
[area registry commands](https://github.com/home-assistant/core/blob/dev/homeassistant/components/config/area_registry.py).

Validation of this change: 244 Python regression tests and all 19 existing
frontend unit tests passed, along with Ruff lint/format and the credential audit. Four cloud conversation scenarios are included, but the
first run was rejected by LiveKit with `MaxSimulationTextTurns` quota exhaustion;
this is not a passed simulation run. Real Gemini debugger conversations with a
fake HA backend checked fresh temperature/humidity reads, one verified light
service, sensor disambiguation and honest timeout reporting without replay. CI includes the new scenarios for a future run with
available simulation quota. No test contacted the user's real HA instance.

Camera entities are now discoverable alongside sensors. For Frigate counts, cloud-image consent and optional event notifications, see [camera awareness](camera-awareness.md).
