# Mac companion and optional local wake word

## Install and login

Configure `ariana/.env.local` and `frontend/.env.local`, then from the repository root:

```sh
bash desktop/install.sh
open "$HOME/Applications/Ariana.app"
```

The installer builds the app in `~/Applications/Ariana.app` and embeds this checkout's
path. Reinstall after moving/updating it. Stop the old app before opening a rebuilt
one. The installer does not kill an active conversation. macOS 13+ supports the
menu's **Start at login** using SMAppService; approve in General → Login Items if
macOS requests it. Nothing is added to login items without selecting that option.

The companion owns production port 3030 and agent health port 8083, with worker name
`ariana-desktop`. Its private access code changes each launch. An instance-specific
health response avoids accidentally attaching to another server on that port.
A file lock prevents two updated companion instances in the same user account.

Services restart with bounded exponential delays (1–60 seconds, eight attempts).
Stable two-minute service runs reset the budget. Three failed health checks stop
and recover a hung owned frontend. Network recovery and sleep/wake notify the
frontend; LiveKit's own reconnect runs first, then bounded fresh joins. Authentication,
quota and microphone errors need user attention. **Reconnect** resets a stopped
retry budget; **Pause** survives automatic recovery. No actions/messages are replayed.
Quit closes ownership pipes and terminates the owned process groups gracefully,
with a bounded hard stop. Health checks slow to about every 30 seconds after startup.

The menu shows Connecting, Ready, Listening, Thinking, Speaking, Offline, Recovering
or Paused. Closing the window hides it. Logs stay in
`~/Library/Application Support/Ariana/desktop.log`; treat them as private because
provider logs can contain transcripts. Login, wake and network behavior require
real-device testing after installing this build.

## Optional Porcupine setup

[Picovoice Porcupine](https://picovoice.ai/docs/api/porcupine-python/) provides a
maintained native local detector for Apple Silicon/macOS. Optional dependencies
are `pvporcupine` 4.0.3 and `pvrecorder` 1.2.7. No speech-recognition model or vector
service was added. Picovoice requires an AccessKey and custom macOS `.ppn` wake-word
model; account licensing/initialization may require internet, but microphone audio
is processed locally and is not uploaded by this helper.

1. Create a custom English **Ariana** wake word for your Mac platform in the
   [Picovoice Console](https://console.picovoice.ai/). Store its `.ppn` outside Git.
2. Add to private `ariana/.env.local`:

```dotenv
PORCUPINE_ACCESS_KEY=your-picovoice-access-key
ARIANA_WAKE_WORD_MODEL=/absolute/path/to/ariana_mac.ppn
```

3. Quit Ariana, then install with `bash desktop/install.sh --wake-word`. Ordinary upgrades preserve installed wake dependencies. Quit the old app, open the
   updated app, then enable **Wake word** in its menu. It is off by default.
4. Allow microphone access. Say “Ariana”, pause briefly for activation, then speak.
   After about 15 seconds without speech/output, voice capture returns to muted
   waiting. Ordinary manual voice mode remains available.

The detector stops recording during active cloud voice capture, Ariana's output and a one-second output tail,
thinking/connecting and Mac sleep. It disarms immediately on detection, with a
three-second cooldown and a second native gate preventing duplicate sessions.
When waiting, no continuous room microphone track goes to Gemini. A muted connected
room may remain for check-ins, so wake mode is not a zero-network/offline assistant.
Disable the menu option to stop the helper and local microphone recording.

Setup/device/permission failures produce a redacted error and stop without repeated
permission prompts. Enable Microphone for Ariana and, if macOS attributes capture
to the Python helper/launcher, for that process too. Automation and Accessibility
remain required for app control. No Screen Recording is needed. Detection accuracy,
custom-model licensing, accents, background noise and output echo need live testing;
headphones are recommended during that evaluation. The helper is not a rolling
speech buffer: words immediately following the wake phrase may be missed.
