"""Local Whisper/Kokoro adapters for LiveKit's cancellable pipeline."""

import asyncio
import threading
from functools import lru_cache
from uuid import uuid4

from livekit import rtc
from livekit.agents import stt, tts
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS

from local_config import voice_files


@lru_cache(maxsize=1)
def engines():
    import onnxruntime
    import sherpa_onnx

    onnxruntime.disable_telemetry_events()
    whisper, kokoro = voice_files()
    recognizer = sherpa_onnx.OfflineRecognizer.from_whisper(
        encoder=str(whisper / "base.en-encoder.int8.onnx"),
        decoder=str(whisper / "base.en-decoder.int8.onnx"),
        tokens=str(whisper / "base.en-tokens.txt"),
        num_threads=2,
    )
    voice = sherpa_onnx.OfflineTts(
        sherpa_onnx.OfflineTtsConfig(
            model=sherpa_onnx.OfflineTtsModelConfig(
                kokoro=sherpa_onnx.OfflineTtsKokoroModelConfig(
                    model=str(kokoro / "model.onnx"),
                    voices=str(kokoro / "voices.bin"),
                    tokens=str(kokoro / "tokens.txt"),
                    data_dir=str(kokoro / "espeak-ng-data"),
                    lexicon=str(kokoro / "lexicon-us-en.txt"),
                    lang="en-us",
                ),
                num_threads=4,
            )
        )
    )
    return recognizer, voice, threading.Lock(), threading.Lock()


class LocalSTT(stt.STT):
    def __init__(self):
        super().__init__(
            capabilities=stt.STTCapabilities(streaming=False, interim_results=False)
        )

    async def _recognize_impl(self, buffer, *, language, conn_options):
        import numpy as np

        frame = rtc.combine_audio_frames(buffer)
        if frame.duration > 65:
            raise ValueError("Speak in turns shorter than a minute.")
        resampler = rtc.AudioResampler(
            frame.sample_rate, 16000, num_channels=frame.num_channels
        )
        chunks = resampler.push(frame) + resampler.flush()
        pcm = b"".join(bytes(chunk.data) for chunk in chunks)
        samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
        if frame.num_channels > 1:
            samples = samples.reshape(-1, frame.num_channels).mean(axis=1)
        samples /= 32768.0

        def decode():
            recognizer, _, lock, _ = engines()
            with lock:
                stream = recognizer.create_stream()
                stream.accept_waveform(16000, samples)
                recognizer.decode_stream(stream)
                return stream.result.text.strip()

        text = await asyncio.to_thread(decode)
        return stt.SpeechEvent(
            type=stt.SpeechEventType.FINAL_TRANSCRIPT,
            alternatives=[stt.SpeechData(language="en", text=text)],
        )


class LocalTTS(tts.TTS):
    def __init__(self, speed=None):
        from preferences_tools import read_preferences

        value = (
            speed if speed is not None else read_preferences().get("local_speed", "1.0")
        )
        if str(value) not in {"0.8", "1.0", "1.2"}:
            raise ValueError("Choose a supported Local speaking rate.")
        self.speed = float(value)
        super().__init__(
            capabilities=tts.TTSCapabilities(streaming=False),
            sample_rate=24000,
            num_channels=1,
        )

    def synthesize(self, text, *, conn_options=DEFAULT_API_CONNECT_OPTIONS):
        return LocalSpeech(tts=self, input_text=text, conn_options=conn_options)


class LocalSpeech(tts.ChunkedStream):
    async def _run(self, output_emitter):
        import numpy as np

        if len(self._input_text) > 4000:
            raise ValueError("Local speech segment is too long.")
        cancelled = threading.Event()

        loop = asyncio.get_running_loop()
        chunks = asyncio.Queue()
        output_emitter.initialize(
            request_id=uuid4().hex,
            sample_rate=24000,
            num_channels=1,
            mime_type="audio/pcm",
            stream=False,
        )

        def callback(samples, progress):
            if cancelled.is_set():
                return 0
            pcm = (np.clip(samples, -1, 1) * 32767).astype(np.int16).tobytes()
            loop.call_soon_threadsafe(chunks.put_nowait, pcm)
            return 1

        def generate():
            try:
                _, voice, _, lock = engines()
                with lock:
                    if not cancelled.is_set():
                        voice.generate(
                            self._input_text,
                            sid=3,
                            speed=self._tts.speed,
                            callback=callback,
                        )
            finally:
                loop.call_soon_threadsafe(chunks.put_nowait, None)

        task = asyncio.create_task(asyncio.to_thread(generate))
        try:
            while (pcm := await chunks.get()) is not None:
                output_emitter.push(pcm)
            await task  # Propagate synthesis errors instead of claiming success.
            output_emitter.flush()
        finally:
            cancelled.set()  # Native synthesis stops at its next sentence callback.
            # The worker owns the native voice lock until synthesis has stopped.
            # Retrieve late errors on cancellation without holding up interruption.
            if not task.done():
                task.add_done_callback(
                    lambda done: done.exception() if not done.cancelled() else None
                )
