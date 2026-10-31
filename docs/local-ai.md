# Normal and Unrestricted Local modes

Normal remains the default Gemini Live pipeline. **Unrestricted** selects a real
independent Ollama model, local Whisper recognition, local Kokoro speech and local
Silero voice activity detection. Both use Ariana's existing personality, SQLite
memory, style settings, receipts and guarded integration implementations.

“Unrestricted” describes the selected community model's reduced conversational
filtering; it does not promise every answer, accuracy, or unrestricted Mac access.
No Gemini or hosted OpenAI inference is used as a fallback from Local mode.

## Selected model and alternatives

The default **`ariana-local:8b`** is a local alias of
**`huihui_ai/qwen3-abliterated:8b-v2`**, Q4_K_M. The alias fixes the context at
16,384 tokens and bounds output. This matters: warming a model with a larger native
context does not change the OpenAI-compatible endpoint's default. An actual 4K
allocation was observed before using the alias. Thinking is disabled through
Ollama's supported `reasoning_effort=none` compatibility parameter for responsiveness.

| Candidate | Weight download | Conversation/reasoning observed | Tools and resources | Decision |
| --- | --- | --- | --- | --- |
| Huihui Qwen3 4B Q4 | 2.5 GB | Answered discussion prompts, but confidently claimed 25 minutes was more than 30 in the public arithmetic check | Native tools; about 36 tokens/s in public checks | Faster alternative, not chosen for reliability |
| Huihui Qwen3.5 4B Q4 | 3.3 GB | No refusal on discussion prompts, but arithmetic contradictions, rambling and confused fictional roles | Native tools; about 31 tokens/s | Not selected despite newer architecture |
| **Huihui Qwen3 8B v2 Q4** | **5.0 GB** | Correct arithmetic and appropriate uncertainty in the small public set; better grounded fictional dialogue | Native tools; about **20 tokens/s**, observed 16K model allocation **5.59 GB** | **Selected** |
| Dolphin 3 Llama 3.1 8B Q4 | 4.9 GB | Author describes a general-purpose minimally filtered tune; not benchmarked here | Native Ollama tool compatibility not verified; custom template work would add risk | Researched, not installed |

These are small controlled observations, not a comprehensive model leaderboard.
Neither local model's humour was consistently good. The 8B model can still sound
more generic, use unwanted formatting, or hallucinate; shared personality guidance
does not guarantee Gemini-level conversational quality. No model guarantees that
it will answer absolutely everything.

Primary sources:
[4B model](https://ollama.com/huihui_ai/qwen3-abliterated:4b),
[8B v2 model](https://ollama.com/huihui_ai/qwen3-abliterated:8b-v2),
[Qwen3.5 4B](https://ollama.com/huihui_ai/qwen3.5-abliterated:4B),
[Dolphin 3](https://ollama.com/library/dolphin3:8b),
[LiveKit Ollama adapter](https://docs.livekit.io/agents/models/llm/ollama/),
[Ollama compatibility/context controls](https://docs.ollama.com/api/openai-compatibility).
Ollama was preferred over a custom MLX/llama.cpp server for its maintained LiveKit
adapter, native structured/tool support, model distribution and straightforward
service management. This is not a claim that MLX could not be faster.

## Setup on another Mac

The implementation was exercised on the user's M4 Mac mini with 16 GB memory.
This Mac already has Ollama, the selected model alias and speech weights installed.
For a clean installation, from the repository root:

```sh
brew install ollama
brew services start ollama
uv sync --project ariana --extra local-voice --extra wake-word
ariana/.venv/bin/python ariana/scripts/setup_local_voice.py
ariana/.venv/bin/python ariana/scripts/setup_local_model.py
(cd frontend && npm ci && npm run build)
open "$HOME/Applications/Ariana.app"
```

Omit `--extra wake-word` if not using that feature. Local mode does not enable the
wake word. `desktop/install.sh --local-voice` can install/update the companion and
preserves an existing wake-word/local-voice installation. Speech/model setup is
explicit: an ordinary conversation or API request never downloads models.

The speech downloader uses official sherpa-onnx release assets, SHA-256 checks and
safe archive extraction. Weights live outside Git under
`~/Library/Application Support/Ariana/local-voice`; Ollama uses its normal local
model store. Keep the downloaded license notices. Qwen/Huihui and Kokoro use Apache
2.0; Whisper uses MIT; sherpa-onnx and Silero have their upstream open-source licenses.
The Kokoro preset is **af_heart**, speaker ID 3: an American feminine voice, not an
imitation of a particular person and not the identical Gemini voice.

Optional server-only settings in **both** `ariana/.env.local` and
`frontend/.env.local`:

```dotenv
ARIANA_OLLAMA_URL=http://127.0.0.1:11434
ARIANA_LOCAL_MODEL=ariana-local:8b
# ARIANA_LOCAL_VOICE_PATH=/absolute/path/to/local-voice
```

Never use `NEXT_PUBLIC_` for credentials or these runtime settings. Custom models
must be downloaded locally, support tools, and have a configured context of at
least 8192 tokens. Hosted endpoints, cloud-backed tags and redirects are rejected.
Do not expose Ollama to your LAN or the internet. The installed service listens on
loopback and starts at login; stop it with `brew services stop ollama` if unwanted.
The model's default five-minute keep-alive releases idle model allocations later;
the lightweight service can stay running without continuous inference.

## Switching and permissions

Use the bottom-left segmented selector. Selection, loading and confirmed active
engine are separate. The orb becomes purple only after the backend acknowledges
Local; Normal uses blue. The confirmed choice persists in browser/WKWebView local
storage. Startup preflight failures show an error instead of creating a cloud token.

During a switch the microphone is muted, active speech is interrupted safely, and
new actions are gated. Running actions/image analysis/transfers block the switch;
completed receipts remain. Pending approvals, camera consent and Mac snapshots are
cleared. Staged attachments are discarded on success. No previous request is replayed.
If the result is uncertain, the microphone stays off until the user checks state.

Each engine starts **fresh model conversation context**. The local transcript is not
copied into Gemini. **Saved memories/preferences are shared** and can be loaded into
Gemini when the user explicitly selects Normal. Do not save a local discussion as
memory if you do not want that shared-memory behavior. Pause/forget still apply.

Voice mode switching is deliberately not exposed as a model tool. Use the trusted
UI; page text, saved memories and model-generated claims cannot change the engine.
`ai_engine_status` reports the active engine in both modes without switching it.

Small-model tool selection is a bounded, structured local Ollama classification of
the latest conversation context. It chooses up to three app groups; it never
executes anything or grants permission. The main model then receives the matching
existing tools. Core memory/preferences/status tools remain available. Normal's
catalog is unchanged. A classifier failure stays local and reports failure.

Existing Notes/Calendar/Mail confirmations, physical-device restrictions, one-use
Accessibility snapshots, password protections, verification and uncertain-action
receipts remain. The model's conversational freedom changes none of these guards.

## Privacy, offline limits and feature limits

- Speech recognition, language generation and synthesis run on the Mac in Local.
  The OpenAI-named SDK adapter speaks only to loopback Ollama; no OpenAI key is needed.
- **This app is not fully offline.** Existing LiveKit Cloud transports room audio,
  text and control data, even when inference is local. Home Assistant/Frigate use
  their configured servers; web/weather/other integrations may need networking.
- No new cloud database, periodic transcript uploader or analytics service was added.
  ONNX Runtime telemetry is disabled. Local endpoint clients ignore environment
  proxies and reject redirects; cloud-model metadata is checked before warmup.
- Local speech recognition is currently English-focused. Recognition of Norwegian
  and names may be weaker than Gemini. No microphone quality score is claimed.
- Local image analysis and screen sharing are disabled in this implementation.
  Camera status/recognition metadata and consented arrival announcements remain,
  but `camera_snapshot` cannot capture/upload in Local. Pictures are rejected,
  not silently sent to Gemini. Qwen3.5 vision was not added as an unsafe fallback.
- Local document excerpts are capped at 12,000 characters per message. The model
  sees a bounded 24-item recent context plus saved memory; it cannot remember an
  unlimited unsaved conversation. Tool receipts remain outside this context bound.
- Close memory-heavy apps on a 16 GB Mac. The 5.59 GB allocation is model/GPU memory,
  not total system usage: speech engines, Python, the UI and macOS need additional
  RAM. Cold starts and tool selection add latency; this is slower than Gemini Live.

## Validation and listening

See [local mode evaluation](local-ai-evaluation.md) for actual tests, model answers,
synthetic audio and room/RPC checks. A human microphone/speaker test and a sustained
20-minute conversation remain necessary. No actual personal Apple-app data or real
home devices are required by CI. Local models/assets are not downloaded in CI.
