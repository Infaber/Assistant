# Ariana on iPhone

Ariana can be added to the iPhone Home Screen as an app. It uses the same orb, chat and voice interface. Your Mac runs the assistant and its app integrations, so keep the Mac awake with Ariana running. Tailscale provides a private HTTPS connection both at home and away.

## One-time setup

1. Install [Tailscale for Mac](https://tailscale.com/download/mac) and [Tailscale for iPhone](https://tailscale.com/download/ios). Complete its sign-in and VPN configuration on both devices using the same account.
2. Open Ariana on the Mac → Settings → iPhone → **Enable private iPhone access**. If setup asks for HTTPS certificates, enable them in the Tailscale admin console’s DNS settings, then retry. See [Tailscale Serve setup](https://tailscale.com/docs/features/tailscale-serve).
3. Click **Show iPhone pairing**. On your iPhone, connect Tailscale and scan the QR code using Camera. Open the link in Safari and tap **Pair this iPhone**.
4. In Safari, choose Share → Add to Home Screen. Keep **Open as Web App** enabled and tap Add. See [Apple’s installation instructions](https://support.apple.com/guide/iphone/open-as-web-app-iphea86e5236/ios).
5. Open Ariana from the new Home Screen icon. Open Conversation for text, or choose voice and approve the iPhone’s microphone prompt.

The pairing link is private: it grants access to your assistant. The browser removes its fragment before pairing and sends the key only after your confirmation. A Secure, HttpOnly, SameSite=Strict host cookie keeps the pairing for 30 days. Safari copies login cookies into newly installed Home Screen apps; it does not copy localStorage ([WebKit](https://webkit.org/blog/14787/webkit-features-in-safari-17-2/)). Install after pairing so the new app receives the login cookie. If the app was installed first, remove its Home Screen icon and add it again after pairing.

## What to expect

- Both Normal/Gemini and Unrestricted/Local use the Mac’s existing configuration. Local inference stays on the Mac; LiveKit Cloud still carries the session’s audio/data.
- Phone conversations have their own session transcript. Saved memories remain shared with the Mac’s existing memory store. This does not synchronize live Mac and phone chat histories.
- Mac tools run on the Mac, with its existing permissions and approval rules.
- Keep the app open for voice. iOS can suspend background web apps; this does not add an always-listening iPhone wake word or Siri replacement.
- Tailscale must remain connected. The Mac must be awake and Ariana must be running.

## Turn access off

In Mac Ariana → Settings → iPhone, choose **Turn off iPhone access**. This stops the owned HTTPS listener, frontend and separate phone agent worker, ends its active sessions, and deletes the pairing key. Previous phone cookies and QR links can no longer start sessions. Re-enabling creates a new key. Removing the saved pairing in the phone app clears that app’s login cookie; it does not revoke other phones.

## Implementation and validation

Phone access is off by default. The frontend binds to `127.0.0.1:3031`; a foreground Tailscale Serve process provides HTTPS on tailnet port 8443. Ariana refuses to replace an existing configuration on that port, never enables Funnel, and verifies its own HTTPS proxy mapping before showing pairing. An agent worker with a key-derived name isolates each Mac’s phone sessions and their shutdown from the desktop worker. The companion owns all child processes through the existing service runner. Pairing keys and status files have owner-only permissions in `~/Library/Application Support/Ariana`.

Tests cover exact-origin authentication, cookie scope, QR confirmation and URL cleanup, copied-cookie session authentication, key rotation, existing Serve/Funnel conflicts, native compilation, and a complete owner startup/shutdown with fake Tailscale/frontend/agent processes. Browser tests cover Home Screen metadata and a simulated Safari keyboard viewport. These are not physical iPhone, live Tailscale-account or microphone tests. The user must complete Tailscale sign-in and VPN permissions on their own devices before a real phone connection can be verified.
