# Ariana 3: room context and proactive priorities

This stage builds on the continuity/memory changes already implemented against
baseline `1e6c035`. Changes remain local; no deployment or GitHub push was made.

## Implemented

**Priority-aware follow-ups.** Check-ins now have a user-selectable minimum
priority from 1 to 5. The native companion persists the setting alongside the
existing opt-in, interval and quiet hours; ordinary browser settings remain
session-scoped. Each event/project uses the existing memory importance value,
defaulting to 3. Due follow-ups are ordered by priority, then due time. Filtered
records remain pending. No automatic promotion, generic idle greeting, extra
private-app access or autonomous device action was introduced.

The SQLite claim rechecks current importance transactionally. The companion also
checks the current threshold after an awaited claim, so changing the setting during
dispatch cannot start a newly ineligible follow-up. Raising the threshold interrupts
ongoing proactive speech. Existing quiet hours, cooldowns, lease, initiative-off,
expiry, pause, deduplication and unanswered guards still apply. Older frontend
heartbeats that omit the new field preserve the current backend threshold.

**Read-only room overview.** `home_assistant_room_context` combines evidence from
one explicitly selected Home Assistant area. It is available to both engines and
the local Home Assistant routing group. It resolves exact names, native aliases or
saved area aliases using fresh registry metadata, then supplies bounded current
state evidence. It includes environment, illumination, motion, occupancy, lights,
switches, fans, climate, covers and area-assigned automation trigger times.

Each category gets a first observation before extra sensors fill the budget.
At most 18 observations and three per category are returned, with omitted counts.
Missing/stale/future timestamps, unknown/unavailable values and assumed/restored
states never become verified current facts. Motion/occupancy evidence has a
90-second window; other observations use 10 minutes. These are conservative
application policies, not universal Home Assistant guarantees. The report distinguishes
sequential collection from an atomic snapshot. Automation trigger times within
24 hours are historical evidence, not proof that the action succeeded.

Frigate sources are excluded by default. Explicit camera inclusion reuses existing
camera enablement, area/source identity and freshness checks, and requires a unique
discovered source. It returns detection evidence only: no images, recognized names,
track identifiers or assumption that a person is the user. The tool never controls
devices or enables proactive behavior. Actual camera interpretation remains in the
existing integration rather than a second detector.

**Simulation isolation.** The new tool is blocked in unrelated LiveKit simulations.
The new `ha_room_context` fixture executes the real snapshot implementation using
fictional data. End-state grading requires a Bedroom snapshot containing actual
fixture observations and rejects any device-service write. The extended real-model
scenario is wired into the existing Home Assistant CI simulation set.

## How to use

- “Give me a quick Bedroom overview: temperature, lights and occupancy sensors.
  Don't use cameras or change anything.”
- “Include the configured camera's current detection count in that room overview.”
- “Treat my exam follow-up as priority five.”
- Settings → Check-ins → Minimum follow-up priority → Important only (4+).

If a sensor reports infrequently, its state can be marked unverified even while the
device is working. If the area's name or source is ambiguous, Ariana must ask rather
than choose a different room. Unassigned automations are excluded; room membership
is never inferred from their friendly names.

## Validation

The tests cover priority order/filtering, nonconsumption of lower priorities,
transactional rechecks after a priority change, strict configuration bounds,
backward compatibility and a setting change during dispatch. Room tests cover
scoping, missing/ambiguous areas, fresh-registry reassignment, bounded results,
category coverage, stale/future/assumed/unavailable data, read-only effects, camera
opt-in/disable gates and simulation end-state checks. A WebKit test verifies native
priority-setting persistence while disconnected.

Final validation: **510 backend tests**, **24 frontend unit tests** and **15 WebKit
browser tests** passed. Ruff lint/formatting, TypeScript checks and production
build also passed.
The real-model scenario, physical microphone/speaker behavior, live Ollama and
HA/Frigate services remain untested here because the fresh checkout lacks their
configuration/credentials. Fictional fixtures and browser tests are not represented
as real-world integration or voice successes.

## Remaining work

Real conversation/listening evaluation, tuning speech endpointing on actual hardware,
a visual memory/style editor, optional semantic retrieval and permission-controlled
screen assistance remain later work. This stage supplies on-demand room evidence;
it does not invent a background room-suggestion policy or act on a presumed arrival.
The pre-existing critical npm dependency advisory remains separate from this change
and should be reviewed before deployment.

Implementation details and source-field semantics are documented in
[Home Assistant room context](home-assistant.md#room-context-overview),
[priority controls](personality.md#follow-up-priority-controls) and
[memory lifecycle](memory.md). Official timestamp semantics were checked against
[Home Assistant's state-object documentation](https://www.home-assistant.io/docs/configuration/state_object/).
