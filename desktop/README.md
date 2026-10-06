# Ariana Mac companion

A native Swift menu bar app with a persistent WebKit workspace. Closing the window
hides it; the session, audio output and check-in heartbeat keep running. The app
starts a private production frontend and a dedicated LiveKit worker. Quit stops
those services. Microphone input starts off; wake-word detection is a future feature.

Configure `ariana/.env.local` and `frontend/.env.local` first, then from the root:

```sh
bash desktop/install.sh
open "$HOME/Applications/Ariana.app"
```

Requires macOS 12+, Apple Command Line Tools (`swiftc`), Node 22+ and `uv`.
The installer creates an ad-hoc signed local app in `~/Applications`; it does not
install a login agent or enable microphone permissions. Add the app to Login Items
if desired. Reinstall after pulling frontend/native changes or moving the checkout.
The app uses loopback port 3030, generates a fresh private access code per launch,
and dispatches `ariana-desktop`. Logs: `~/Library/Application Support/Ariana/desktop.log`.

Check-ins default to every 15 minutes with quiet hours 22:00–08:00. Change these in
the workspace; the app remembers them. Choose equal quiet hours to disable that
window. Only one unanswered check-in is sent. Check-ins are conversational and
cannot run tools. They require the Mac to stay awake, online and connected.

Use the menu bar sparkle for Show Ariana, Pause conversation and Quit Ariana.
Voice can be enabled with the microphone button; background wake-word listening
is not present. Apple app control permissions may need to be granted for Ariana
instead of the terminal app you previously used.

The production frontend is built during installation. Build-only check:

```sh
swiftc -parse-as-library desktop/Ariana.swift -o /tmp/Ariana-check -framework Cocoa -framework WebKit
```
