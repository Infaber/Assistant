"use client";
import { useEffect, useState } from "react";
import { desktopConfig } from "../lib/desktop";
type WakeStatus = {
  enabled: boolean;
  ready: boolean;
  phrase: string;
  configuring: boolean;
  permission_pending?: boolean;
  can_configure?: boolean;
  error: string;
};
export default function WakeControls() {
  const [native, setNative] = useState(false);
  const [status, setStatus] = useState<WakeStatus | null>(null);
  const [phrase, setPhrase] = useState("Hey Ariana");
  useEffect(() => {
    const config = desktopConfig();
    if (!config) return;
    setNative(true);
    const receive = (event: Event) => {
      const value = (event as CustomEvent).detail;
      if (
        value &&
        typeof value.enabled === "boolean" &&
        typeof value.ready === "boolean" &&
        typeof value.phrase === "string" &&
        typeof value.configuring === "boolean" &&
        typeof value.error === "string"
      ) {
        setStatus(value);
        if (["Hey Ariana", "Ariana"].includes(value.phrase))
          setPhrase(value.phrase);
      }
    };
    window.addEventListener("ariana:wake-status", receive);
    config.postMessage?.({ type: "wake-status" });
    return () => window.removeEventListener("ariana:wake-status", receive);
  }, []);
  return (
    <section className="voice-settings" aria-label="Local wake word">
      <h3>Local wake word</h3>
      {!native ? (
        <p>Wake detection requires the Mac companion.</p>
      ) : (
        <>
          <p role="status">
            {status?.error ||
              (status?.permission_pending
                ? "Waiting for microphone permission"
                : status?.configuring
                  ? "Configuring local phrase"
                  : status?.ready
                    ? "Wake word ready"
                    : status?.enabled
                      ? "Wake detection paused or starting"
                      : "Wake detection off")}
          </p>
          <label>
            Local wake detection
            <input
              type="checkbox"
              aria-label="Local wake detection"
              checked={status?.enabled || false}
              disabled={
                !status || status.configuring || status.permission_pending
              }
              onChange={(e) =>
                desktopConfig()?.postMessage?.({
                  type: "wake-settings",
                  enabled: e.target.checked,
                })
              }
            />
          </label>
          <p>Configured: {status?.phrase || "Waiting for companion"}</p>
          <label>
            Wake phrase
            <select
              aria-label="Wake phrase"
              value={phrase}
              onChange={(e) => setPhrase(e.target.value)}
            >
              <option>Hey Ariana</option>
              <option>Ariana</option>
            </select>
          </label>
          <button
            disabled={
              !status ||
              status.configuring ||
              status.can_configure === false ||
              (status.enabled && !status.ready)
            }
            onClick={() =>
              desktopConfig()?.postMessage?.({
                type: "wake-settings",
                phrase: phrase as "Hey Ariana" | "Ariana",
              })
            }
          >
            Configure local phrase
          </button>
        </>
      )}
      <small>
        Phrase setup may download the existing small local keyword model if
        missing. No audio is recorded to disk. Wait for Listening before your
        command: continuous speech immediately after the phrase is not buffered
        or replayed. Standby mutes the room; an enabled local wake detector
        still listens. Turn this setting off to stop that detector. Wake
        detection is not speaker authentication.
      </small>
    </section>
  );
}
