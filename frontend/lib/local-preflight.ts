import { existsSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';

export async function preflightLocal(env: Record<string,string|undefined>) {
  const base = new URL(env.ARIANA_OLLAMA_URL || 'http://127.0.0.1:11434');
  if (base.protocol!=='http:' || !['127.0.0.1','localhost','[::1]'].includes(base.hostname) || base.username || base.password || !['','/'].includes(base.pathname) || base.search || base.hash) throw new Error('Local AI requires a loopback Ollama server.');
  const model = env.ARIANA_LOCAL_MODEL || 'ariana-local:8b';
  if (/cloud/i.test(model)) throw new Error('Cloud-backed Ollama models are not allowed in Local mode.');
  const root=env.ARIANA_LOCAL_VOICE_PATH || join(homedir(),'Library/Application Support/Ariana/local-voice');
  for (const file of ['sherpa-onnx-whisper-base.en/base.en-encoder.int8.onnx','sherpa-onnx-whisper-base.en/base.en-decoder.int8.onnx','kokoro-multi-lang-v1_0/model.onnx','kokoro-multi-lang-v1_0/voices.bin'])
    if (!existsSync(/* turbopackIgnore: true */ join(/* turbopackIgnore: true */ root,file))) throw new Error('Local speech assets are missing. Run the local voice setup script first.');
  try {
    const response=await fetch(new URL('/api/show',base),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({model}),redirect:'error',signal:AbortSignal.timeout(5000)});
    if (!response.ok) throw new Error('missing');
    const data=await response.json();
    if (data.remote_host || data.remote_model || !data.capabilities?.includes('tools')) throw new Error('unsupported');
  } catch {throw new Error('Local model unavailable. Start Ollama and download the configured tool-capable model; no cloud fallback was used.');}
}
