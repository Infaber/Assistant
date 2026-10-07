"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  RoomAudioRenderer,
  SessionProvider,
  StartAudio,
  useAgent,
  useLocalParticipant,
  useSession,
  useSessionMessages,
  useTrackVolume,
  type UseSessionReturn,
} from "@livekit/components-react";
import {
  LocalAudioTrack,
  Track,
  ConnectionState,
  DisconnectReason,
  ParticipantKind,
  RoomEvent,
  TokenSource,
  type RemoteParticipant,
  type DataPacket_Kind,
} from "livekit-client";
import {
  Check,
  Copy,
  Mic,
  MicOff,
  Monitor,
  PhoneOff,
  Settings2,
  X,
} from "lucide-react";
import ArianaOrb, { orbStyles } from "./ariana-orb";
import { useThinkingFeedback } from "./use-thinking-feedback";

import { desktopConfig } from "../lib/desktop";
import SharingComposer, { type SharedMessage } from "./sharing-composer";
import CheckInControls from "./check-in-controls";
import {
  parseActivity,
  updateActivity,
  finishActivity,
  type Activity,
} from "../lib/activity";

function friendlyError(error: unknown) {
  if (error instanceof Error) {
    if (error.name === "NotAllowedError")
      return "Microphone access was denied. Allow it in your browser, or choose text mode.";
    if (error.name === "NotFoundError")
      return "No microphone was found. Connect one, or choose text mode.";
    return error.message || "Something went wrong. Please try again.";
  }
  return "Could not connect. Please try again.";
}

export default function Ariana() {
  const accessCode = useRef(desktopConfig()?.accessCode || "");
  const credentials = useRef({ serverUrl: "", participantToken: "" });
  const [ready] = useState(() => {
    let resolve!: () => void;
    const promise = new Promise<void>((done) => {
      resolve = done;
    });
    return { promise, resolve };
  });
  // Fetch only on an explicit start. The SDK also reads this source while
  // preparing/ending a session; those reads must not create rooms or requests.
  const tokenSource = useMemo(
    () =>
      TokenSource.literal(async () => {
        await ready.promise;
        return credentials.current;
      }),
    [ready],
  );
  async function prepare(signal: AbortSignal) {
    const response = await fetch("/api/connection", {
      method: "POST",
      headers: { Authorization: `Bearer ${accessCode.current}` },
      signal: AbortSignal.any([signal, AbortSignal.timeout(15_000)]),
    });
    const data = await response.json();
    if (!response.ok)
      throw new Error(data.error || "Could not create a session.");
    signal.throwIfAborted();
    credentials.current = {
      serverUrl: data.server_url,
      participantToken: data.participant_token,
    };
    ready.resolve();
  }
  const session = useSession(tokenSource, {
    agentConnectTimeoutMilliseconds: 30_000,
  });
  return (
    <SessionProvider session={session}>
      <Workspace
        session={session}
        prepare={prepare}
        onCodeChange={(code) => {
          accessCode.current = code.trim();
        }}
      />
      <RoomAudioRenderer />
    </SessionProvider>
  );
}

function Workspace({
  session,
  prepare,
  onCodeChange,
}: {
  session: UseSessionReturn;
  prepare: (signal: AbortSignal) => Promise<void>;
  onCodeChange: (value: string) => void;
}) {
  const agent = useAgent(session);
  const { messages, send, isSending } = useSessionMessages(session);
  const { localParticipant, isMicrophoneEnabled, isScreenShareEnabled } =
    useLocalParticipant();
  const [inputOpen, setInputOpen] = useState(false);
  const [orbStyle, setOrbStyle] = useState(0);
  const [captions, setCaptions] = useState(false);
  const [feedback, setFeedback] = useState(true);
  const [chrome, setChrome] = useState(true);
  const [captionVisible, setCaptionVisible] = useState(false);
  const [incomingFiles, setIncomingFiles] = useState<File[]>([]);
  const history = useRef<HTMLDialogElement>(null);
  const fadeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const outputLevel = useTrackVolume(agent.microphoneTrack);
  const microphoneTrack = localParticipant.getTrackPublication(
    Track.Source.Microphone,
  )?.track;
  const inputLevel = useTrackVolume(
    microphoneTrack instanceof LocalAudioTrack ? microphoneTrack : undefined,
  );
  const feedbackLevel = useThinkingFeedback(
    session.isConnected && agent.state === "thinking",
    feedback,
    inputLevel,
  );
  const [activity, setActivity] = useState<Activity[]>([]);
  const [providerError, setProviderError] = useState("");
  const [busy, setBusy] = useState(false);
  const [mediaBusy, setMediaBusy] = useState(false);
  const [error, setError] = useState("");
  const [draft, setDraft] = useState("");
  const [copied, setCopied] = useState(false);
  const [code, setCode] = useState("");
  const [sharedMessages, setSharedMessages] = useState<SharedMessage[]>([]);
  const [hiddenMessages, setHiddenMessages] = useState<Set<string>>(new Set());
  const dialog = useRef<HTMLDialogElement>(null);
  const transcript = useRef<HTMLDivElement>(null);
  const composer = useRef<HTMLInputElement>(null);
  const abort = useRef<AbortController | null>(null);
  const connected = session.isConnected;
  const connecting =
    busy || session.connectionState === ConnectionState.Connecting;
  const reconnecting = [
    ConnectionState.Reconnecting,
    ConnectionState.SignalReconnecting,
  ].includes(session.connectionState);
  const visibleMessages = messages.filter(
    (message) => !hiddenMessages.has(message.id),
  );
  const conversation = [
    ...visibleMessages.map((message) => ({
      ...message,
      files: [] as SharedMessage["files"],
      isAgent:
        message.type === "agentTranscript" ||
        !!(message.from && !message.from.isLocal),
    })),
    ...sharedMessages.map((message) => ({ ...message, isAgent: false })),
  ].sort((a, b) => a.timestamp - b.timestamp);
  const status = providerError
    ? "Connection needs attention"
    : reconnecting
      ? "Reconnecting"
      : !connected
        ? connecting
          ? "Connecting"
          : "Ready when you are"
        : agent.state === "failed"
          ? "Agent unavailable"
          : agent.state === "speaking"
            ? "Ariana is speaking"
            : agent.state === "thinking"
              ? "Thinking it through"
              : !agent.isConnected
                ? "Finding Ariana"
                : isMicrophoneEnabled
                  ? "Listening to you"
                  : "Ready for your message";

  function revealInput() {
    setInputOpen(true);
    requestAnimationFrame(() => composer.current?.focus());
  }
  function revealChrome() {
    setChrome(true);
    if (fadeTimer.current) clearTimeout(fadeTimer.current);
    fadeTimer.current = setTimeout(() => setChrome(false), 3000);
  }
  useEffect(() => {
    try {
      const saved = JSON.parse(
        localStorage.getItem("ariana.orb.preferences") || "{}",
      );
      if (Number.isInteger(saved.style) && saved.style >= 0 && saved.style < 6)
        setOrbStyle(saved.style);
      setCaptions(saved.captions === true);
      setFeedback(saved.feedback !== false);
    } catch {}
    const shortcut = (event: KeyboardEvent) => {
      if (
        event.target instanceof HTMLElement &&
        event.target.closest("button,a,summary") &&
        (event.key === "Enter" || event.key === " ")
      )
        return;
      if (event.key === "Escape") {
        setInputOpen(false);
        return;
      }
      if (
        dialog.current?.open ||
        history.current?.open ||
        (event.target instanceof HTMLElement &&
          /INPUT|TEXTAREA|SELECT/.test(event.target.tagName))
      )
        return;
      if (
        ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") ||
        event.key === "Enter" ||
        (!event.metaKey &&
          !event.ctrlKey &&
          !event.altKey &&
          event.key.length === 1)
      ) {
        event.preventDefault();
        if (event.key.length === 1 && !event.metaKey && !event.ctrlKey)
          setDraft((current) => current + event.key);
        revealInput();
      }
    };
    const paste = (event: ClipboardEvent) => {
      if (
        event.clipboardData?.files.length &&
        !(
          event.target instanceof HTMLElement &&
          event.target.closest(".sharing-composer")
        )
      ) {
        event.preventDefault();
        setIncomingFiles(Array.from(event.clipboardData.files));
        revealInput();
      }
    };
    window.addEventListener("keydown", shortcut);
    window.addEventListener("paste", paste);
    revealChrome();
    return () => {
      window.removeEventListener("keydown", shortcut);
      window.removeEventListener("paste", paste);
      if (fadeTimer.current) clearTimeout(fadeTimer.current);
    };
  }, []);
  function preferences(
    style = orbStyle,
    showCaptions = captions,
    speak = feedback,
  ) {
    setOrbStyle(style);
    setCaptions(showCaptions);
    setFeedback(speak);
    try {
      localStorage.setItem(
        "ariana.orb.preferences",
        JSON.stringify({ style, captions: showCaptions, feedback: speak }),
      );
    } catch {}
  }
  const lastCaption =
    conversation.filter((message) => message.isAgent).at(-1)?.message || "";
  useEffect(() => {
    setCaptionVisible(!!lastCaption);
    const timer = setTimeout(() => setCaptionVisible(false), 6000);
    return () => clearTimeout(timer);
  }, [lastCaption]);

  useEffect(() => {
    const receive = (
      payload: Uint8Array,
      participant?: RemoteParticipant,
      _kind?: DataPacket_Kind,
      topic?: string,
    ) => {
      if (
        topic !== "ariana.activity" ||
        participant?.kind !== ParticipantKind.AGENT
      )
        return;
      const event = parseActivity(payload);
      if (!event) return;
      setActivity((rows) => updateActivity(rows, event));
      if (event.kind === "system" && event.status === "failed")
        setProviderError(event.detail);
    };
    const disconnected = (reason?: DisconnectReason) => {
      setActivity(finishActivity);
      if (reason !== DisconnectReason.CLIENT_INITIATED)
        setProviderError(
          (current) =>
            current ||
            "The connection ended unexpectedly. Reconnect to start a fresh session; check any unfinished action before repeating it.",
        );
    };
    session.room.on(RoomEvent.DataReceived, receive);
    session.room.on(RoomEvent.Disconnected, disconnected);
    return () => {
      session.room.off(RoomEvent.DataReceived, receive);
      session.room.off(RoomEvent.Disconnected, disconnected);
    };
  }, [session.room]);

  useEffect(() => {
    const onError = (err: Error) => setError(friendlyError(err));
    session.room.on(RoomEvent.MediaDevicesError, onError);
    return () => {
      session.room.off(RoomEvent.MediaDevicesError, onError);
    };
  }, [session.room]);

  useEffect(() => {
    const element = transcript.current;
    if (element) element.scrollTop = element.scrollHeight;
  }, [messages, sharedMessages]);

  useEffect(
    () => () => {
      abort.current?.abort();
      void session.room.disconnect();
    },
    [session.room],
  );

  async function start(asText = false) {
    if (connecting || connected) return;
    setBusy(true);
    setError("");
    setProviderError("");
    setActivity([]);
    setSharedMessages([]);
    setHiddenMessages(new Set(messages.map((message) => message.id)));
    const controller = new AbortController();
    abort.current = controller;
    try {
      await prepare(controller.signal);
      controller.signal.throwIfAborted();
      await session.start({
        signal: controller.signal,
        tracks: { microphone: { enabled: !asText } },
      });
      controller.signal.throwIfAborted();
      // StartAudio offers a user gesture if the browser blocks autoplay.
      await session.room.startAudio().catch(() => {});
    } catch (err) {
      if (!controller.signal.aborted) setError(friendlyError(err));
      await session.end();
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (!desktopConfig()) return;
    const automaticStart = window.setTimeout(() => {
      void start(true);
    }, 400);
    const pause = () => {
      abort.current?.abort();
      void session.end();
    };
    window.addEventListener("ariana:pause", pause);
    return () => {
      window.clearTimeout(automaticStart);
      window.removeEventListener("ariana:pause", pause);
    };
  }, [session.room]);

  async function end() {
    abort.current?.abort();
    await session.end();
  }

  async function media(action: () => Promise<unknown>) {
    if (mediaBusy) return;
    setMediaBusy(true);
    setError("");
    try {
      await action();
    } catch (err) {
      setError(friendlyError(err));
    } finally {
      setMediaBusy(false);
    }
  }

  async function copyTranscript() {
    try {
      await navigator.clipboard.writeText(
        conversation
          .map(
            (message) =>
              `${message.isAgent ? "Ariana" : "You"}: ${message.message}${message.files.length ? "\nAttachments: " + message.files.map((file) => file.name).join(", ") : ""}`,
          )
          .join("\n\n"),
      );
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setError(
        "Could not copy the conversation. Try selecting the text instead.",
      );
    }
  }

  const orbState =
    connecting || reconnecting || (connected && !agent.isConnected)
      ? "thinking"
      : !connected
        ? "idle"
        : agent.state === "thinking"
          ? "thinking"
          : agent.state === "speaking"
            ? "speaking"
            : isMicrophoneEnabled
              ? "listening"
              : "idle";
  const issue =
    error ||
    providerError ||
    (connected && agent.state === "failed"
      ? "Ariana has not joined. Check the agent, then reconnect."
      : "");
  return (
    <main
      className={`orb-stage ${chrome ? "chrome-visible" : ""}`}
      onPointerMove={revealChrome}
      onPointerDown={revealChrome}
      onFocus={revealChrome}
      onDragOver={(event) => {
        if (event.dataTransfer.types.includes("Files")) event.preventDefault();
      }}
      onDrop={(event) => {
        if (
          !event.target ||
          !(event.target as HTMLElement).closest(".sharing-composer")
        ) {
          event.preventDefault();
          setIncomingFiles(Array.from(event.dataTransfer.files));
          revealInput();
        }
      }}
    >
      <h1 className="sr-only">Ariana</h1>
      <div className="orb-center">
        <button
          className="orb-touch"
          aria-label={
            connected
              ? "Message Ariana"
              : connecting
                ? "Connecting to Ariana"
                : "Start conversation"
          }
          onClick={() => {
            if (!connected && !connecting) void start();
            else revealInput();
          }}
          disabled={connecting}
        >
          <ArianaOrb
            style={orbStyle}
            state={orbState}
            level={
              orbState === "speaking"
                ? outputLevel
                : orbState === "thinking"
                  ? feedbackLevel
                  : inputLevel
            }
          />
        </button>
        <p
          className={`orb-caption ${captions && captionVisible ? "caption-visible" : ""}`}
          aria-hidden={!captions || !captionVisible}
        >
          {lastCaption}
        </p>
      </div>
      <p className="sr-only" role="status">
        {status}
      </p>
      <div className="quiet-controls">
        <button
          className="icon-button"
          disabled={mediaBusy || connecting}
          aria-label={
            connected
              ? isMicrophoneEnabled
                ? "Mute microphone"
                : "Unmute microphone"
              : "Start conversation"
          }
          aria-pressed={connected && isMicrophoneEnabled}
          onClick={() => {
            if (!connected) void start();
            else
              void media(() =>
                localParticipant.setMicrophoneEnabled(!isMicrophoneEnabled),
              );
          }}
        >
          {connected && isMicrophoneEnabled ? (
            <Mic size={19} />
          ) : (
            <MicOff size={19} />
          )}
        </button>
        <button
          className="icon-button"
          aria-label="Settings"
          onClick={() => dialog.current?.showModal()}
        >
          <Settings2 size={19} />
        </button>
      </div>
      <StartAudio label="Enable Ariana’s audio" className="enable-audio" />
      {issue && (
        <div className="error-banner" role="alert">
          <p>{issue}</p>
          <button
            onClick={() => {
              setError("");
              setProviderError("");
              if (connected || connecting) void end();
              else void start();
            }}
          >
            {connected || connecting ? "End session" : "Retry"}
          </button>
          <button
            aria-label="Dismiss error"
            onClick={() => {
              setError("");
              setProviderError("");
            }}
          >
            <X size={16} />
          </button>
        </div>
      )}
      <div
        className={`input-overlay ${inputOpen ? "input-open" : ""}`}
        inert={!inputOpen}
        aria-hidden={!inputOpen}
      >
        <SharingComposer
          participant={localParticipant}
          destination={agent.isConnected ? agent.identity : undefined}
          ready={agent.isConnected && !isSending && !providerError}
          draft={draft}
          setDraft={setDraft}
          inputRef={composer}
          onText={async (text) => {
            await send(text);
          }}
          onShared={(message) =>
            setSharedMessages((current) => [...current, message])
          }
          onError={setError}
          sessionKey={connected}
          incomingFiles={incomingFiles}
          onSent={() => setInputOpen(false)}
        />
        {!connected && !connecting && (
          <button
            className="text-connect"
            onClick={() => {
              void start(true);
            }}
          >
            Connect with text
          </button>
        )}
        <button
          className="close-input icon-button"
          aria-label="Hide message input"
          onClick={() => setInputOpen(false)}
        >
          <X size={16} />
        </button>
      </div>
      <dialog
        ref={dialog}
        className="glass-dialog settings-dialog"
        aria-labelledby="settings-title"
        onClick={(event) => {
          if (event.target === dialog.current) dialog.current?.close();
        }}
      >
        <header>
          <h2 id="settings-title">Ariana</h2>
          <button
            className="icon-button"
            aria-label="Close settings"
            onClick={() => dialog.current?.close()}
          >
            <X size={19} />
          </button>
        </header>
        <fieldset className="appearance">
          <legend>Appearance</legend>
          <div className="style-picker">
            {orbStyles.map((name, index) => (
              <button
                key={name}
                aria-pressed={orbStyle === index}
                onClick={() => preferences(index)}
              >
                <span
                  className={`style-swatch swatch-${index}`}
                  aria-hidden="true"
                />
                <span>{name}</span>
              </button>
            ))}
          </div>
        </fieldset>
        <label className="setting-toggle">
          Captions
          <input
            type="checkbox"
            checked={captions}
            onChange={(event) => preferences(orbStyle, event.target.checked)}
          />
        </label>
        <label className="setting-toggle">
          Spoken thinking feedback
          <input
            type="checkbox"
            checked={feedback}
            onChange={(event) =>
              preferences(orbStyle, captions, event.target.checked)
            }
          />
        </label>
        <p className="settings-help">
          Tap Ariana to begin. Tap again, type, or press ⌘K to write. Paste or
          drop pictures and files.
        </p>
        <div className="session-settings">
          <span>{status}</span>
          {connected || connecting ? (
            <button
              onClick={() => {
                void end();
              }}
            >
              <PhoneOff size={16} />
              {connecting ? "Cancel connection" : "End session"}
            </button>
          ) : (
            <>
              <button
                onClick={() => {
                  void start();
                  dialog.current?.close();
                }}
              >
                Start conversation
              </button>
              <button
                onClick={() => {
                  void start(true);
                  dialog.current?.close();
                }}
              >
                Connect with text
              </button>
            </>
          )}
          <button
            disabled={!connected || mediaBusy}
            onClick={() => {
              void media(() =>
                localParticipant.setScreenShareEnabled(!isScreenShareEnabled, {
                  audio: false,
                }),
              );
            }}
          >
            <Monitor size={16} />
            {isScreenShareEnabled ? "Stop sharing screen" : "Share screen"}
          </button>
          <button
            onClick={() => {
              dialog.current?.close();
              history.current?.showModal();
            }}
          >
            Conversation & activity
          </button>
        </div>
        <CheckInControls
          participant={localParticipant}
          destination={agent.isConnected ? agent.identity : undefined}
          ready={agent.isConnected && !providerError}
        />
        <form
          className="access-form"
          onSubmit={(event) => {
            event.preventDefault();
            onCodeChange(code);
            dialog.current?.close();
          }}
        >
          <label htmlFor="access-code">Access code</label>
          <input
            id="access-code"
            type="password"
            autoComplete="current-password"
            value={code}
            onChange={(event) => setCode(event.target.value)}
          />
          <button type="submit">Save settings</button>
        </form>
      </dialog>
      <dialog
        ref={history}
        className="glass-dialog history-dialog"
        aria-labelledby="history-title"
        onClick={(event) => {
          if (event.target === history.current) history.current?.close();
        }}
      >
        <header>
          <h2 id="history-title">Conversation</h2>
          <div>
            <button
              className="icon-button"
              aria-label={copied ? "Transcript copied" : "Copy transcript"}
              disabled={!conversation.length}
              onClick={copyTranscript}
            >
              {copied ? <Check size={18} /> : <Copy size={18} />}
            </button>
            <button
              className="icon-button"
              aria-label="Close conversation"
              onClick={() => history.current?.close()}
            >
              <X size={19} />
            </button>
          </div>
        </header>
        <div ref={transcript} className="transcript" role="log">
          {!conversation.length && (
            <p className="settings-help">Your conversation will appear here.</p>
          )}
          {conversation.map((message) => (
            <article className="message" key={message.id}>
              <small>{message.isAgent ? "Ariana" : "You"}</small>
              <p>{message.message}</p>
              {message.files.map((file, index) => (
                <div className="shared-file" key={index}>
                  {file.preview && <img src={file.preview} alt={file.name} />}
                  <span>{file.name}</span>
                </div>
              ))}
            </article>
          ))}
        </div>
        {activity.length > 0 && (
          <details>
            <summary>Activity</summary>
            {activity.map((item) => (
              <article className="message" key={item.id}>
                <small>
                  {item.label} · {item.status}
                </small>
                <p>{item.detail}</p>
              </article>
            ))}
          </details>
        )}
      </dialog>
    </main>
  );
}
