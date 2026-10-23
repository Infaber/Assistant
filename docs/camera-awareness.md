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
- “Stop camera announcements.” — disables speech now and revokes its saved permission.

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
Unchanged MQTT sensors may have an old timestamp even while the room is
unchanged. Ariana never relabels an old HA value as fresh. For stale/unavailable
native count data, it instead checks healthy recent Frigate capture stats,
requests one authenticated live tracker snapshot, then verifies capture again.
If that independent check fails, the answer remains unknown. Missing registry
provenance or invalid sensors are still refused. No historical count is reused.


### Independent live count fallback

On Frigate 0.18, Ariana uses its authenticated `/ws` UI transport only for a
read-only `onConnect` state query. The installed viewer authorization and handler
were inspected: the query publishes current activity and does not change
configuration. Only person/person-verified track IDs are retained, including
stationary people; no images, names or arbitrary command topics are requested.
Detection must be enabled. The connection lasts at most eight seconds after
authentication, accepts at most 32 bounded messages and closes immediately after
the activity reply. Redirects, duplicate/missing IDs, disabled detection, malformed
activity, login failures and unsupported versions leave the result unknown.
Capture is checked before and after. The observation time records the fresh
server-state retrieval, not the age of an individual video frame or guarantee
that the detector cannot lag. There is no continuous polling or video upload.

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
pending upload. While a delivery is pending, automatic greetings, check-ins and idle
transport refresh wait for it instead of superseding its generation. Camera
subscription/status diagnostics expose `image_analysis_state` (prepared, waiting
for the tool turn, submitting, analyzing, completed, cancelled or failed) and
redacted errors. Status never includes image bytes, private questions or credentials.

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
approve. Permission is saved locally, scoped to this camera and its discovered
event sources, and survives voice reconnects, app restarts and Mac restarts.
Changing camera/source configuration needs fresh approval. “Stop camera
announcements” revokes the saved permission; other sessions notice within five
seconds. The background companion must be running and connected to play audio;
closing its window is fine, quitting it, explicit Pause, sleep or a network outage
prevents live speech. No microphone input or first user message is required. While announcements
are permitted, the existing idle voice-transport refresh keeps that connection
available without generating speech or replaying actions.

A single HA WebSocket subscription consumes state changes, with heartbeats and
bounded reconnect backoff. It does not continuously poll Frigate or fetch images.
Initial/reconnect states are baselines, not arrivals; old/duplicate notifications
are ignored. Count transitions trigger neutral notifications, availability
transitions describe the HA camera entity (not a verified RTSP diagnosis), and
review-status transitions report a new alert. The default notification cooldown is 120 seconds. Friendly arrival greeting mode
uses a 15-second cooldown and a three-second minimum empty interval to
filter detection flicker. It also handles increases in an already occupied room,
such as one person becoming two. Additional arrivals wait for three seconds of
stable count; brief count dips and recoveries do not create another greeting. A genuine new arrival during cooldown stays pending
until it can speak, rather than being discarded. Set `ARIANA_CAMERA_GREETING_ENABLED=true` for a brief unnamed
“Hey, welcome back” on a fresh person-count increase. This greets newcomers,
including visitors joining someone already present, and does not speak on departure.
It still requires explicit announcement approval, which is then remembered; setup/reconnect
baselines never generate greetings. Set `ARIANA_CAMERA_NAMED_GREETING_ENABLED=true` after authorizing recognition
metadata to personalize greetings. Each arrival gets up to eight seconds of
bounded current-identity checks. Only current healthy tracks with the established
confidence threshold supply names; recent sightings never do. A private, session-local
baseline of live track IDs distinguishes newcomers from people already in the room.
Only names attached to the newly arriving tracks enter the greeting: a recognized
resident never supplies the name for an unknown visitor. Missing baselines, ambiguous
track changes and unknown names fall back to a friendly unnamed welcome. Rapid
successive arrivals awaiting speech are combined into one greeting. Startup and
reconnect capture occupants as a baseline without greeting them; there is no continuous
identity polling. The bounded track history stays in memory and is not saved as
personal memory or treated as authorization. Departure/reconnect cancels the lookup,
and names older than ten seconds are rechecked if conversation delayed playback.
No face images or biometric templates are retrieved. A new greeting may wait for up to 60 seconds while Ariana is busy, then
plays after three seconds of conversation quiet. Leaving, a disconnect, disabling
speech or expiry cancels it. Reconnect baselines never create a greeting.
The subscription diagnostic includes `last_greeting_decision` (for example
`waiting_for_cooldown`, `conversation_busy`, `brief_detection_gap` or
`waiting_for_identity`, `waiting_for_stable_arrival`, `arrival_count_changed` or
`arrival_not_present`) so missed greetings have a concrete explanation.
Failed/uncertain audio is recorded in subscription diagnostics and never blindly
replayed. No identity, device action, memory write or tool use
is authorized by a notification. Permission is stored in a private local
`camera-permission.json` beside Ariana’s preferences, with no names/images/tokens.
A missing, corrupt or camera/source-mismatched record defaults to off. Alerts require the optional review-status entity;
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

### Let Ariana read recognition results

After configuring and testing Frigate locally, explicitly opt in in private
`ariana/.env.local`:

```dotenv
ARIANA_CAMERA_RECOGNITION_ENABLED=true
```

Restart Ariana and ask “Has Frigate recognized me?” or “Who did the bedroom
camera recognize?” `camera_status(action="recognition")` reads only person-event
metadata from the authenticated API, excluding thumbnails. No face image,
embedding or enrollment data is retrieved. Reported names and confidence become
conversation data sent to Ariana's existing Gemini model. Explicitly authorize
this transfer before enabling it; this is not fully local conversation processing.
Camera-derived memory writes are blocked for that turn.

Matches require a finite **sub-label** confidence of at least 0.95. Object-detection
confidence is never substituted. Missing, low-confidence or invalid results remain
unknown. Current identity uses a fresh discovered HA total person count (or the
independent live Frigate fallback), healthy recent camera stats and ongoing person events (`in_progress=1`, excluding
thumbnails). Track count must match the observed count; live fallback IDs must match the
ongoing event IDs exactly. Ended, false-positive,
duplicate or inconsistent tracks never establish current identity. Long-running
ongoing tracks are eligible regardless of when they started, so staying seated
for more than ten minutes does not hide a recognized person. Unknown people
remain separate when only some people are recognized.

`current_recognized_people` supports natural answers such as “Looks like Youssef
is in the room.” This is a probabilistic tracked-object report, not guaranteed
physical occupancy or speaker authentication. Camera/count/track disagreement
returns current identity unavailable instead of guessing. Labels can lag changes
in view until Frigate updates/ends the corresponding track.

Separately, `recent_matches` reads at most 20 events started in the last ten
minutes. These are historical only: “Looks like Youssef was here recently.” Event
start is not recognition time. Past matches never fill in an unnamed current
track or establish that someone is still present.

Frigate sub-labels can also be set by administrators or classification models.
An API score does not prove native face-recognition provenance. Names remain
untrusted data and never authenticate a user, approve a write, unlock anything or
change existing confirmation requirements. No automatic identity enrollment or
biometric memory storage is added. Enrollment/removal stay manual in Frigate's
local Face Library UI, with its own retention settings.

Set the opt-in flag false and restart to stop Ariana reading recognition labels.
This does not turn off Frigate's own recognition. Hardware compatibility still
needs verification on the installed runtime, regardless of image tag or version.

Current identity is checked on demand, not continuously. Named arrival greetings perform bounded on-demand checks against those current
tracks, with departure cancellation and no historical-name substitution. Named
mode also takes one bounded baseline snapshot on reconnect or announcement enable.
A visitor leaving before playback cancels the queued greeting, even if somebody
else remains. The sensor/track system still has limits: one person entering at the
same instant another leaves (unchanged count) does not trigger an arrival; short
untracked departures or tracker churn may yield no name or an unnamed greeting.

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
   network loss with the companion; saved permission should survive a new session, while reconnect baselines must not
   announce a fictitious arrival. Disable speech, reconnect again, and confirm it stays off.
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
