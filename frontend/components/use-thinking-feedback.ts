"use client";
import { useEffect, useRef, useState } from "react";
import { ThinkingFeedback } from "../lib/thinking-feedback";
export function useThinkingFeedback(
  thinking: boolean,
  enabled: boolean,
  inputLevel: number,
) {
  const controller = useRef<ThinkingFeedback | null>(null);
  const [level, setLevel] = useState(0);
  useEffect(() => {
    const context = new AudioContext();
    const analyser = context.createAnalyser();
    analyser.fftSize = 256;
    analyser.connect(context.destination);
    const buffers = new Map<string, Promise<AudioBuffer>>();
    let source: AudioBufferSourceNode | undefined,
      frame = 0;
    const unlock = () => {
      void context.resume().catch(() => {});
    };
    // Resume in the original gesture, before a delayed cue needs playback.
    window.addEventListener("pointerdown", unlock);
    window.addEventListener("keydown", unlock);
    const stop = () => {
      source?.stop();
      source?.disconnect();
      source = undefined;
      setLevel(0);
      cancelAnimationFrame(frame);
    };
    const play = async (name: string, active: () => boolean) => {
      if (!buffers.has(name))
        buffers.set(
          name,
          fetch(`/audio/${name}.wav`)
            .then((response) => {
              if (!response.ok) throw new Error("Audio cue unavailable");
              return response.arrayBuffer();
            })
            .then((data) => context.decodeAudioData(data)),
        );
      const buffer = await buffers.get(name)!;
      await context.resume();
      if (!active()) return;
      source = context.createBufferSource();
      source.buffer = buffer;
      source.connect(analyser);
      source.start();
      const playing = source;
      playing.onended = () => {
        if (source === playing) {
          source = undefined;
          setLevel(0);
          cancelAnimationFrame(frame);
        }
        playing.disconnect();
      };
      const bytes = new Uint8Array(analyser.fftSize);
      const tick = () => {
        if (source !== playing || !active()) return;
        analyser.getByteTimeDomainData(bytes);
        setLevel(
          Math.sqrt(
            bytes.reduce((sum, b) => sum + ((b - 128) / 128) ** 2, 0) /
              bytes.length,
          ),
        );
        frame = requestAnimationFrame(tick);
      };
      tick();
    };
    controller.current = new ThinkingFeedback(play, stop);
    return () => {
      controller.current?.cancel();
      window.removeEventListener("pointerdown", unlock);
      window.removeEventListener("keydown", unlock);
      void context.close();
    };
  }, []);
  const active = thinking && enabled && inputLevel <= 0.12;
  useEffect(() => {
    controller.current?.update(active);
    return () => controller.current?.cancel();
  }, [active]);
  return level;
}
