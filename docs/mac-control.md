# Mac control and vision boundaries

Prefer direct Notes, Calendar, Reminders, Mail, Spotify, Home Assistant and Safari
integrations. Use Accessibility only when a direct tool cannot perform the task.

Existing protections remain: fresh inspection, stable target verification, opaque
snapshot IDs, one-use consumption, 60-second expiry, stale UI protection, secure-field
blocking and post-action observation. Dispatch alone is not proof of success.
Permission errors stop retries; timeouts remain uncertain until actual state is
read. Accessibility limitations must be explained rather than using guessed clicks.
See the [integration reference](agent-reference.md) for supported actions.

`vision_fallback.py` prepares bounded, advisory screenshot requests and semantic
label hints. It has no capture wiring, coordinate output or action executor. It
requires a secure-content exclusion check; that check must come from trusted
capture code, not the model. No screenshot grants consent or overrides instructions.

Next implementation step: trusted on-device capture with secure-window/field
exclusion, then map suggested labels to a fresh verified Accessibility target. If
no usable target can be verified, ask the user to act. Reliable visual clicking
needs an additional target-validation and approval design before it can ship.
This release adds no Screen Recording permission requirement.

Safari permission denial opens a session-local circuit breaker: subsequent calls
return the error without more navigation. Grant Automation, then reconnect for a
fresh session. Repeated same-URL requests in one user turn re-read the page rather
than opening duplicate windows; uncertain navigation is never automatically replayed.
