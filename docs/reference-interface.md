# Reference interface refresh

Ariana now follows the supplied November 3 reference: a charcoal workspace, translucent cyan/lavender ribbons, a slim icon rail, last response, rounded composer and right-hand Session panel. Unrestricted uses red throughout. The primary and glass orb presets use the new ribbon renderer; the remaining four styles retain their existing animations. The renderer caps motion at 30 fps, stops while hidden and respects reduced motion.

Session diagnostics show only actual LiveKit `e2e_latency` measurements: speech end to agent response start. The chart shows up to 20 recent samples; median and nearest-rank p95 use all response samples retained in the backend's bounded 100-event window. No values are invented for an empty or unavailable session. The read-only status RPC refreshes serially every eight seconds and late responses cannot restore a disconnected session. No transcripts or audio are included in the diagnostic payload. This is an agent-side timing, not measurement of sound reaching the listener.

Connection, microphone and active engine remain distinct. Full conversation/activity, voice preferences, attachments, mode-transfer opt-in and approval flows remain available. Mobile stacks diagnostics below the main interaction.

Validation: frontend typecheck and production build; frontend unit tests; WebKit browser regressions, including responsive geometry, silent preferences, diagnostic reset and stale RPC handling; targeted backend voice-control and performance tests. No live microphone or camera was enabled for validation. This change does not claim an inference-speed improvement.
