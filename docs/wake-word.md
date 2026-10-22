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

## Free local wake-word setup

The optional detector uses [Sherpa-ONNX](https://github.com/k2-fsa/sherpa-onnx),
with native macOS Apple Silicon and Intel support. The engine and selected English
[GigaSpeech 3.3M keyword model](https://k2-fsa.github.io/sherpa/onnx/kws/pretrained_models/index.html#sherpa-onnx-kws-zipformer-gigaspeech-3-3m-2024-01-01-english)
are Apache-2.0 licensed (the downloaded model README retains its license metadata).
There is no account, subscription, API key or custom-model training step. The old
Picovoice helper and its paid credentials are no longer used.

1. Quit Ariana from its menu-bar menu.
2. From the repository root, install and reopen:

   ```sh
   bash desktop/install.sh --wake-word
   open "$HOME/Applications/Ariana.app"
   ```

3. Click Ariana's menu-bar icon and enable **Wake word**. Allow Microphone access
   when asked. Say **“Ariana”**, pause briefly for activation, then speak.
4. After about 15 seconds without speech/output, voice capture returns to muted
   waiting. Disable **Wake word** to stop local microphone recording completely.

The installer downloads a pinned, checksum-verified ~17 MB archive once from the
upstream release. It retains only the quantized models, tokenizer, keyword file and
model/license metadata in `~/Library/Application Support/Ariana/wake-word` (~5.3 MB).
Normal reinstalls verify existing model files and do not download them again.
The installer preserves an existing wake installation, including migration from
Picovoice. Old `PORCUPINE_ACCESS_KEY` and `.ppn` settings can be removed from private
env files; Ariana ignores them. No real credentials belong in Git.

Optional Python dependencies are `sherpa-onnx` / its native `sherpa-onnx-core` runtime
(1.13.8), `sounddevice` (0.5.6) for local microphone input and `sentencepiece` (0.2.2)
for configuring phrases. The native core is explicit because upstream sdist metadata
can omit it during lockfile resolution. No separate ONNX Runtime Python package,
cloud speech recognizer or vector service is needed. Inference uses one CPU thread
and blocking 100 ms microphone reads; while disabled the helper waits for commands
without opening the microphone or running inference.

### Change the phrase or model location

The default phrase is **Ariana**. To use **Hey Ariana**, quit the companion and run:

```sh
cd ariana
.venv/bin/python scripts/setup_wake_word.py --phrase "Hey Ariana"
```

Reopen the app. Phrase changes are tokenized locally, with no retraining. Subsequent
installs preserve your configured phrase. English is the supported language for this
model; names, accents and noise affect accuracy. A longer phrase may reduce false
activations. Arbitrary phrases are supported by the model architecture, but each
needs real microphone testing.

To store the models elsewhere, set `ARIANA_WAKE_WORD_MODEL_DIR` in private
`ariana/.env.local`. The installer and helper both read that file. The default needs
no environment configuration.

### Privacy, guards and limitations

Detection runs locally; the helper makes no network requests during operation and
writes no audio files. Only wake/status events go to the native app. Initial package
and model downloads need internet. A muted connected LiveKit room may remain for
check-ins, so wake mode is not a fully offline assistant. Once awakened, ordinary
voice conversation uses the existing LiveKit/Gemini connection.

The detector stops recording during active cloud voice capture, Ariana's output and
a one-second output tail, thinking/connecting and Mac sleep. Each re-arm starts a
fresh decoder stream and microphone buffer so old partial phrases cannot complete
after a mute. Detection disarms immediately, with a three-second cooldown and a
second native gate preventing duplicate sessions. Detection never grants permission
for tools or consequential actions.

Device or setup failures produce a redacted error and stop instead of retrying
permission prompts. Enable **System Settings → Privacy & Security → Microphone →
Ariana**; macOS may additionally attribute input to the Python helper/launcher.
Automation and Accessibility permissions remain relevant for app control, but
Screen Recording is unnecessary for wake detection.

The helper has no rolling speech buffer: words immediately following the wake phrase
may be missed. Pause briefly before your command. The menu shows whether wake mode
is armed locally, paused during conversation, or needs setup/microphone access.
Accuracy and echo suppression still need testing with the user's microphone and
voice; synthetic audio tests are not a substitute. Headphones help isolate echo
when evaluating this. Wake mode does not identify or authenticate speakers.
