"use client";
import { useEffect, useState } from "react";
import type { LocalParticipant } from "livekit-client";
import {
  voiceDraft,
  voicePatch,
  type VoiceSnapshot,
} from "../lib/voice-settings";

type Snapshot = VoiceSnapshot;
export default function VoiceControls({
  participant,
  destination,
  ready,
  busy,
  onStandby,
  wakeState,
  localTimings,
}: {
  participant: LocalParticipant;
  destination?: string;
  ready: boolean;
  busy: boolean;
  onStandby: () => void;
  wakeState: string;
  localTimings: () => unknown;
}) {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState("Connect to change voice settings.");
  const [slots, setSlots] = useState<Record<string, Record<string, string>>>(
    {},
  );
  const [diagnostics, setDiagnostics] = useState("");
  const [cues, setCues] = useState("subtle");
  useEffect(() => {
    try {
      setSlots(
        JSON.parse(localStorage.getItem("ariana.voice.comparisons") || "{}"),
      );
      const saved = localStorage.getItem("ariana.listening-cues");
      if (["off", "subtle", "expressive"].includes(saved || ""))
        setCues(saved!);
    } catch {}
  }, []);
  async function rpc(action: string, values?: Record<string, string>) {
    if (!ready || !destination) throw new Error("Connect first.");
    const result = JSON.parse(
      await participant.performRpc({
        destinationIdentity: destination,
        method: "ariana.voice-settings",
        payload: JSON.stringify({ action, values }),
        responseTimeout: 10000,
      }),
    );
    if (result.error) throw new Error(result.error);
    return result;
  }
  useEffect(() => {
    let canceled = false;
    if (!ready || !destination) {
      setSnapshot(null);
      return;
    }
    void rpc("status")
      .then((result) => {
        if (canceled) return;
        setSnapshot(result);
        setDraft(voiceDraft(result));
        setMessage("Voice and style changes apply on your next connection.");
      })
      .catch(() => {
        if (!canceled)
          setMessage("Voice controls unavailable in this session.");
      });
    return () => {
      canceled = true;
    };
  }, [ready, destination, participant]);
  async function run(action: "save" | "sample" | "standby") {
    setPending(true);
    if (action === "standby") onStandby();
    try {
      const result = await rpc(
        action,
        action === "save" ? voicePatch(draft) : undefined,
      );
      if (action === "standby") {
        setMessage("Returning to microphone-muted standby.");
      }
      if (action === "save")
        setMessage(
          "Saved. End and reconnect when ready to apply; the current conversation was not interrupted.",
        );
      if (action === "sample")
        setMessage(
          `Sample requested with active voice ${result.voice}. Content is fixed; Live generation can vary.`,
        );
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "Voice control failed.",
      );
    } finally {
      setPending(false);
    }
  }
  function slot(name: string, save: boolean) {
    if (save) {
      const next = { ...slots, [name]: draft };
      setSlots(next);
      try {
        localStorage.setItem("ariana.voice.comparisons", JSON.stringify(next));
      } catch {}
      setMessage(`Configuration ${name} saved locally; no audio recorded.`);
    } else if (slots[name]) setDraft(slots[name]);
  }
  return (
    <section className="voice-settings" aria-label="Voice and conversation">
      <h3>Voice and conversation</h3>
      <p role="status">{message}</p>
      <p>Active voice: {snapshot?.active_voice || "Not connected"}</p>
      <label>
        Gemini voice
        <select
          aria-label="Gemini voice"
          disabled={!snapshot || pending}
          value={draft.google_voice || ""}
          onChange={(e) => setDraft({ ...draft, google_voice: e.target.value })}
        >
          <option value="">Keep configured default</option>
          {(snapshot?.voices || ["Sulafat"]).map((voice) => (
            <option key={voice}>{voice}</option>
          ))}
        </select>
      </label>
      <label>
        Turn-end silence
        <select
          aria-label="Gemini turn-end silence"
          value={draft.turn_end_pause || "provider"}
          onChange={(e) =>
            setDraft({ ...draft, turn_end_pause: e.target.value })
          }
        >
          <option value="provider">Provider default</option>
          <option value="500">500 ms</option>
          <option value="800">800 ms</option>
          <option value="1200">1200 ms</option>
        </select>
      </label>
      <small>
        Gemini only. Longer silence can allow thinking pauses and also delay
        replies. This does not classify interruptions; test with your
        microphone.
      </small>
      <small>
        Normal uses Gemini native audio. Local keeps its own Kokoro voice; a
        saved Gemini preset applies when you next connect to Normal.
      </small>
      <small>
        Conversation preferences guide model delivery. They do not directly
        control pitch, laughter or emotion intensity.
      </small>
      {snapshot &&
        Object.entries(snapshot.styles).map(([key, values]) => (
          <label key={key}>
            {key}
            <select
              aria-label={`Conversation ${key}`}
              value={draft[key] || ""}
              onChange={(e) => setDraft({ ...draft, [key]: e.target.value })}
            >
              <option value="" disabled>
                Current default
              </option>
              {values.map((value) => (
                <option key={value}>{value}</option>
              ))}
            </select>
          </label>
        ))}
      <button disabled={!snapshot || pending} onClick={() => void run("save")}>
        Save for next connection
      </button>
      <details>
        <summary>Compare configurations</summary>
        <p>
          Save A and B, load one, save for next connection, then end and
          reconnect explicitly. Play the same sample in each fresh session.
          Opening this panel never plays audio or reconnects.
        </p>
        {["A", "B"].map((name) => (
          <span key={name}>
            <button disabled={!snapshot} onClick={() => slot(name, true)}>
              Save {name}
            </button>
            <button disabled={!slots[name]} onClick={() => slot(name, false)}>
              Load {name}
            </button>
          </span>
        ))}
        <p>{snapshot?.sample_text}</p>
        <button
          disabled={!ready || busy || pending}
          onClick={() => void run("sample")}
        >
          Play current voice sample
        </button>
        <small>
          The sample is a real model reply in this session and may appear in
          chat history. No tools are provided.
        </small>
      </details>
      <label>
        Listening cues (visual)
        <select
          aria-label="Listening cue level"
          value={cues}
          onChange={(e) => {
            setCues(e.target.value);
            try {
              localStorage.setItem("ariana.listening-cues", e.target.value);
            } catch {}
            window.dispatchEvent(
              new CustomEvent("ariana:listening-cues", {
                detail: e.target.value,
              }),
            );
          }}
        >
          <option value="off">Off</option>
          <option value="subtle">Subtle</option>
          <option value="expressive">Expressive</option>
        </select>
      </label>
      <small>
        Mid-speech audio backchannels are unavailable in this pipeline. Visual
        cues play no sound, create no model turns and trigger no tools.
      </small>
      <p>
        Wake conversation: {wakeState}. Automatic standby follows 90 seconds
        without detected activity.
      </p>
      <button disabled={!ready || pending} onClick={() => void run("standby")}>
        Stop speaking and return to standby
      </button>
      <details>
        <summary>Numerical diagnostics</summary>
        <button
          disabled={!ready}
          onClick={() =>
            void rpc("status")
              .then((result) =>
                setDiagnostics(
                  JSON.stringify(
                    { backend: result.diagnostics, browser: localTimings() },
                    null,
                    2,
                  ),
                ),
              )
              .catch(() => setDiagnostics("Diagnostics unavailable."))
          }
        >
          Refresh timings
        </button>
        <small>
          Local event timings, not provider compute time or sound reaching your
          ears. No transcripts or audio are stored here.
        </small>
        <pre>{diagnostics}</pre>
      </details>
    </section>
  );
}
