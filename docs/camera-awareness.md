# Camera awareness (Frigate + Home Assistant)

Ariana reuses Frigate's detection and existing Home Assistant discovery. It does
not run a second detector, alter recording, enroll faces, or stream camera video
to Gemini. Every camera feature is disabled initially.

## Configure privately

Add these settings to `ariana/.env.local`, which must stay untracked:

```dotenv
ARIANA_CAMERA_ENABLED=true
FRIGATE_URL=http://frigate.local:8971
FRIGATE_CAMERA=bedroom
FRIGATE_USERNAME=your_read_only_viewer
FRIGATE_PASSWORD=your_private_password
```

Replace the hostname with your local authenticated Frigate address. Port 5000,
embedded URL credentials, redirects, and raw configuration reads are refused.
Use a Frigate viewer or camera-scoped read-only role, not an administrator. A
`FRIGATE_TOKEN` bearer token can replace username/password; tokens expire. With
username/password the next request can reauthenticate after an expired session.
Login is the only POST; Ariana exposes no camera mutation API.

Frigate commonly serves HTTPS on 8971; use the scheme your instance actually
supports. HTTPS is preferred because HTTP exposes credentials/images to the LAN.
For self-signed HTTPS, configure a trusted certificate (for example a private CA
with `SSL_CERT_FILE`); Ariana does not disable certificate verification. Do not
publish either API port to the internet. No direct camera/RTSP credentials are
needed by Ariana.

Restart the backend after changing environment settings. Existing
`HOME_ASSISTANT_URL` and `HOME_ASSISTANT_TOKEN` settings remain necessary for
current counts and subscriptions. The Frigate HA integration uses MQTT; Frigate
and HA must share the broker. This upgrade does not install or modify the broker.

## Voice commands

- “How many people are in my room?” — fresh discovered **total** Frigate person count.
- “What objects is the bedroom camera detecting?” — available fresh HA object counts.
- “Is my bedroom camera working?” — bounded Frigate stats with fresh timestamps.
- “Was someone detected in my room in the last hour?” — historical detection events.
- “Are there any recent camera alerts?” — review API; unsupported versions fail clearly.
- “What can you see on my desk?” — asks separate permission to send one image to Gemini.
- “Stop camera announcements.” — disables speech immediately for the session.

Zero means Frigate reports zero detections, not proof that nobody is physically
present. Detected people have **unknown identity**. Historical events never prove
current occupancy. Total counts include stationary tracked objects; active-only
counts omit stationary people and are refused as occupancy evidence.

Discovery uses actual registry/platform/name/area/alias metadata. Temperature,
humidity and desk-light commands continue through existing Home Assistant tools.
If a person-count match is ambiguous, choose the discovered total-count entity.
Fresh registry identity is checked again before trusting a person count; a recycled
entity ID is refused. Known false-positive historical events are excluded.
No entity ID is fabricated. Object-count sensors also require the native
`objects` unit to exclude unrelated counters. Object counts are a partial inventory of configured
HA sensors, not a claim that every object in the room has been detected.

Current data requires a reporting timestamp no older than 90 seconds. HA's
`last_reported` is preferred, with `last_updated` as a conservative fallback.
Unchanged sensors can therefore be reported as stale even while the room is
unchanged: configure reliable MQTT/HA reporting rather than accepting old values
as current. Missing registry provenance, unavailable sensors or stale stats mean
**unknown**. No history-based occupancy fallback is used.

## Snapshot permission and retention

A request to look at the room starts a preview. Ariana explains that **one camera
image will be sent to Google Gemini**, then waits for a new affirmative user
reply. Natural approval is sufficient. Approval is bound to camera, question and
optional event ID, expires after five minutes, and is consumed once. The guard
also checks that the cloud recipient was actually named in the conversation,
not merely in a hidden tool result. Changes,
retries after failures, or additional images need a new approval.

Current snapshots require recent healthy camera stats. Historical event images
are labeled historical and checked against the approved camera. Retrieval uses
Frigate's documented latest-frame/event-snapshot routes. Responses are bounded to
5 MB; decoding rejects excessive dimensions and unsupported data. Images are
normalized to JPEG, at most 1280 pixels on the longer side, quality 75, with EXIF
removed. No snapshots are written to files or SQLite. Tool results contain no
image bytes/base64. Gemini uses blocking tool calls: the current tool turn must
finish before a new image input is delivered. Ariana gives a brief “One moment”
cue, then a bounded session-scoped delivery task sends the approved picture through
the existing Gemini Live multimodal context and generates its description with
all action tools removed. There is no second model or continuous video pipeline.
A newer user turn, interruption before delivery or session closure cancels the
pending upload. Failures are exposed through camera subscription/status diagnostics.

The tool confirms image preparation, **not analysis or upload**. Ariana must
inspect it before describing content and acknowledge ambiguity. Failed delivery
never counts as seeing the room. There is a 45-second bound on waiting for the
preceding tool speech and another 45-second bound on analysis. Images are pruned
from local context and history afterward, never stored on disk. Camera-derived
memory writes are blocked during that turn. Normal SDK context serialization
excludes images from telemetry.

Important provider limitation: Gemini Live cannot delete individual messages from
an already established cloud session. Local pruning prevents future replay after delivery ends, but this cannot erase
what Gemini already received. Disconnect to end that
live session; Google's retention policies still apply. Do not approve an upload
if you need the image to remain completely local. This integration does not
promise cryptographic memory erasure or cloud deletion.

## Opt-in event announcements

Set up discovered Frigate entities in the private environment:

```dotenv
ARIANA_CAMERA_EVENTS_ENABLED=true
FRIGATE_HA_PERSON_ENTITY=sensor.replace_with_actual_total_person_count
FRIGATE_HA_CAMERA_ENTITY=camera.replace_with_actual_bedroom_camera
FRIGATE_HA_ALERT_ENTITY=sensor.replace_with_actual_review_status
```

Only provide entities that actually exist; leave unused sources blank. Sources
are validated against Home Assistant registry provenance and camera metadata.
Person sources must be total counts, never active-only. Announcements use the configured camera name; verify its metadata before enabling. Subscription setup alone does **not**
authorize speech: ask “Enable camera announcements,” listen to the preview, then
approve. Permission lasts only for the connected voice session and is lost on a
new session. The background Mac companion needs its voice session connected. While announcements
are permitted, the existing idle voice-transport refresh keeps that connection
available without generating speech or replaying actions.

A single HA WebSocket subscription consumes state changes, with heartbeats and
bounded reconnect backoff. It does not continuously poll Frigate or fetch images.
Initial/reconnect states are baselines, not arrivals; old/duplicate notifications
are ignored. Count transitions trigger neutral notifications, availability
transitions describe the HA camera entity (not a verified RTSP diagnosis), and
review-status transitions report a new alert. There is a 120-second global speech
cooldown. Events during active speech/recent conversation are dropped, never
queued as stale greetings. No identity, device action, memory write or tool use
is authorized by a notification. Alerts require the optional review-status entity;
this is not a separate full Frigate review-event archive.

To disable all camera access, set `ARIANA_CAMERA_ENABLED=false` and restart the
backend. This also stops the subscription. None of these settings change Frigate's
own recording, detection or face-recognition configuration.

## Face recognition preparation

“Check camera capabilities” reads `/api/version` and explains next steps. It does
not claim that recognition is installed/enabled based on a version number alone.
The Docker image tag `stable-standard-arm64` is not a reliable version/capability
check. The unauthenticated endpoint probe was rejected. A read-only Docker inspection
confirmed installed Frigate **0.18.0-77a66e7**, without inspecting credentials or
footage. Native recognition capability has not been verified on this ARM64 runtime.

Prefer native Frigate recognition if the installed version **and runtime hardware**
support it. Current official documentation lists AVX/AVX2 CPU requirements, which
must not be assumed compatible with an ARM64 Apple Silicon Docker image. Older
and current documentation have different requirements/defaults. Check your exact
release before enabling; no replacement recognition service was added.

`camera_recognition.py` defines a disabled-by-default confidence policy and a
future consent-bound native enrollment/removal interface. It is intentionally not
an executable enrollment tool. Person events ignore native `sub_label` identities.
If native recognition is supported, enrollment/removal remain explicit operations
in Frigate's local Face Library UI; review its own retention/training settings.
No automatic enrollment or biometric personal memory is permitted.

Next implementation step: verify local native recognition support, then implement
an explicit enrollment/removal adapter with single-use consent and native
confidence provenance. Do not infer a confidence score from a name-only sub-label.

## Real-system acceptance checklist

1. Ask for cameras and health; verify the actual Frigate version separately through
   authenticated capabilities. Check incorrect credentials/unreachable service
   produce clear errors without leaking their values.
2. Stand/move/sit in view; compare zero/one/two person counts with HA's total-count
   sensor. Confirm stale/unavailable readings are described as unknown.
3. Compare historical timestamps and alerts with Frigate. They must not become
   current-presence claims. Try an unsupported API feature safely.
4. Ask to inspect the desk; decline cloud permission first. No image should be
   fetched. Ask again, approve one upload, and verify visible details without
   identity claims. Confirm no snapshot files or camera memories are created.
5. Enable the subscription, then separately approve speech. Enter/leave, reconnect
   HA, repeat detections, and speak during an event. Verify neutral wording,
   baseline suppression, cooldown and no interruption. Test Mac sleep/wake and
   network loss with the companion; no new session should retain permission.
6. Disable camera access and restart; all camera tools/subscriptions must stop.

Automated tests use fake HTTP/HA services and synthetic solid-color images. They
cannot prove your camera, MQTT sensor reporting, physical stream freshness,
companion background audio, native recognition or production voice timing works.

## Official API references (checked 8 October 2026)

- [Authentication and viewer roles](https://docs.frigate.video/configuration/authentication/)
- [Stats](https://docs.frigate.video/integrations/api/stats-stats-get/)
- [Events](https://docs.frigate.video/integrations/api/events-events-get/)
- [Review alerts](https://docs.frigate.video/integrations/api/review-review-get/)
- [Latest frame](https://docs.frigate.video/integrations/api/latest-frame-camera-name-latest-extension-get/)
- [Event snapshots](https://docs.frigate.video/integrations/api/event-snapshot-events-event-id-snapshot-jpg-get/)
- [MQTT count semantics](https://docs.frigate.video/integrations/mqtt/)
- [Home Assistant integration](https://docs.frigate.video/integrations/home-assistant/)
- [Native face recognition](https://docs.frigate.video/configuration/face_recognition/)
- [LiveKit multimodal context](https://docs.livekit.io/agents/logic/chat-context/)
