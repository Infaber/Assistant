# Development and validation

From `ariana/`:

```sh
uv sync --locked --dev
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
uv run python scripts/audit_repository.py
```

From `frontend/`:

```sh
npm ci
npm run typecheck
npm test
npm run build
npx playwright install webkit
npm run test:browser
```

From the repository root on macOS:

```sh
bash -n desktop/install.sh
swiftc -parse-as-library desktop/Ariana.swift desktop/CompanionState.swift desktop/ManagedService.swift -o /tmp/Ariana-check -framework Cocoa -framework WebKit -framework Network -framework ServiceManagement -framework AVFoundation
swiftc -parse-as-library desktop/CompanionState.swift desktop/CompanionStateTests.swift -o /tmp/Ariana-state-tests
/tmp/Ariana-state-tests
swiftc -parse-as-library desktop/CompanionState.swift desktop/ManagedService.swift desktop/ManagedServiceTests.swift -o /tmp/Ariana-service-tests
/tmp/Ariana-service-tests "$PWD/ariana/.venv/bin/python" "$PWD/ariana/src/service_runner.py"
```

Optional wake tests use fake frames/devices; they need no key, microphone or optional
SDK installation. Mac service tests create isolated subprocesses, never personal
apps. Python tests cover model config, missing keys, permissions, timeout/uncertain
writes, partial success, single-use approvals, stale Notes, memory and existing
Accessibility guards. Frontend tests cover connection policy, recovery gates,
attachments, activity states and WebKit presentation.

## LiveKit simulations

These use real inference/credentials and isolated tool fixtures. From `ariana/`:

```sh
lk agent simulate text --scenarios scenarios.yaml
lk agent simulate text --scenarios scenarios-integrations.yaml
lk agent simulate text --scenarios scenarios-mac.yaml
lk agent simulate text --scenarios scenarios-memory.yaml
lk agent simulate text --scenarios scenarios-reliability.yaml
lk agent simulate text --scenarios scenarios-sharing.yaml
lk agent simulate text --scenarios scenarios-home-assistant.yaml
```

Personal integrations are blocked or faked in simulations, including private reads.
CI must not access actual Notes, Mail, Calendar, Spotify or Home Assistant data.
Model startup should also be checked with `lk agent debugger start`, `say`, then
`stop`; restart after edits. Do not share private debugger/provider logs.

Real-device acceptance still needs login/reboot, app installation, microphone/TCC
prompts, custom Ariana wake detections, speaker echo, physical sleep/wake, Wi-Fi loss
and active LiveKit recovery. A compile or simulated notification does not prove those
flows work on the user's configured Mac. Test actual integrations only with explicit
user requests and reversible test data.


## Validation of this upgrade (7 October 2026)

- 201 Python tests passed; Ruff lint/format passed. One upstream Google typing
  deprecation warning remains.
- Frontend type checking, production build, 19 unit tests and 12 WebKit tests passed.
- Native Swift compile, state/output-tail tests and real isolated Mac process
  crash/duplicate-start/shutdown tests passed. Python also checked descendant cleanup.
- All 31 conversation scenarios were exercised across six suites. Core 8, integrations
  6, Mac 7, memory 3 and sharing 3 passed in their final suite runs. Reliability's
  three other cases passed; its uncertain-click case hit a provider generation
  timeout and passed a targeted rerun. Two earlier inference runs had transient
  `generation_created` timeouts. The failed-lookup next-step behavior was tightened
  and then passed the final core run. CI now runs inference with concurrency 1.
- Reachable-history credential scan found no real candidates; configured frontend
  server secrets did not occur in production browser JavaScript.

These results do not verify custom wake recognition, login/reboot, TCC microphone
prompts, speaker echo or physical sleep/Wi-Fi recovery. Those require installation
and real Mac acceptance tests; the currently running old companion was left intact.
