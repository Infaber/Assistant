'use client';

import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import {
  BarVisualizer, RoomAudioRenderer, SessionProvider, StartAudio,
  useAgent, useLocalParticipant, useSession, useSessionMessages,
  type UseSessionReturn,
} from '@livekit/components-react';
import { ConnectionState, RoomEvent, TokenSource } from 'livekit-client';
import { ArrowUp, AudioLines, Check, ChevronRight, Compass, Copy, Headphones,
  Keyboard, LoaderCircle, MessageSquare, Mic, MicOff, Monitor, PhoneOff,
  Settings2, ShieldCheck, Sparkles, X } from 'lucide-react';

const prompts = [
  { icon: Compass, label: 'Explore something new', text: 'Help me learn something interesting today.' },
  { icon: Sparkles, label: 'Think it through', text: 'Can you help me think through an idea?' },
  { icon: MessageSquare, label: 'Find an answer', text: 'I have a question I would like you to look up.' },
];

function friendlyError(error: unknown) {
  if (error instanceof Error) {
    if (error.name === 'NotAllowedError') return 'Microphone access was denied. Allow it in your browser, or choose text mode.';
    if (error.name === 'NotFoundError') return 'No microphone was found. Connect one, or choose text mode.';
    return error.message || 'Something went wrong. Please try again.';
  }
  return 'Could not connect. Please try again.';
}

export default function Ariana() {
  const accessCode = useRef('');
  const credentials = useRef({ serverUrl: '', participantToken: '' });
  const [ready] = useState(() => {
    let resolve!: () => void;
    const promise = new Promise<void>((done) => { resolve = done; });
    return { promise, resolve };
  });
  // Fetch only on an explicit start. The SDK also reads this source while
  // preparing/ending a session; those reads must not create rooms or requests.
  const tokenSource = useMemo(() => TokenSource.literal(async () => {
    await ready.promise;
    return credentials.current;
  }), [ready]);
  async function prepare(signal: AbortSignal) {
    const response = await fetch('/api/connection', {
      method: 'POST', headers: { Authorization: `Bearer ${accessCode.current}` },
      signal: AbortSignal.any([signal, AbortSignal.timeout(15_000)]),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Could not create a session.');
    signal.throwIfAborted();
    credentials.current = { serverUrl: data.server_url, participantToken: data.participant_token };
    ready.resolve();
  }
  const session = useSession(tokenSource, { agentConnectTimeoutMilliseconds: 30_000 });
  return <SessionProvider session={session}>
    <Workspace session={session} prepare={prepare} onCodeChange={(code) => { accessCode.current = code.trim(); }} />
    <RoomAudioRenderer />
  </SessionProvider>;
}

function Workspace({ session, prepare, onCodeChange }: { session: UseSessionReturn; prepare: (signal: AbortSignal) => Promise<void>; onCodeChange: (value: string) => void }) {
  const agent = useAgent(session);
  const { messages, send, isSending } = useSessionMessages(session);
  const { localParticipant, isMicrophoneEnabled, isScreenShareEnabled } = useLocalParticipant();
  const [mode, setMode] = useState<'voice' | 'text'>('voice');
  const [busy, setBusy] = useState(false);
  const [mediaBusy, setMediaBusy] = useState(false);
  const [error, setError] = useState('');
  const [draft, setDraft] = useState('');
  const [copied, setCopied] = useState(false);
  const [code, setCode] = useState('');
  const [hiddenMessages, setHiddenMessages] = useState<Set<string>>(new Set());
  const [seconds, setSeconds] = useState(0);
  const dialog = useRef<HTMLDialogElement>(null);
  const transcript = useRef<HTMLDivElement>(null);
  const composer = useRef<HTMLInputElement>(null);
  const abort = useRef<AbortController | null>(null);
  const connected = session.isConnected;
  const connecting = busy || session.connectionState === ConnectionState.Connecting;
  const reconnecting = [ConnectionState.Reconnecting, ConnectionState.SignalReconnecting].includes(session.connectionState);
  const visibleMessages = messages.filter((message) => !hiddenMessages.has(message.id));
  const status = reconnecting ? 'Reconnecting' : !connected ? (connecting ? 'Connecting' : 'Ready when you are')
    : agent.state === 'failed' ? 'Agent unavailable' : agent.state === 'speaking' ? 'Ariana is speaking'
    : agent.state === 'thinking' ? 'Thinking it through' : !agent.isConnected ? 'Finding Ariana'
    : isMicrophoneEnabled ? 'Listening to you' : 'Ready for your message';

  useEffect(() => {
    const onError = (err: Error) => setError(friendlyError(err));
    session.room.on(RoomEvent.MediaDevicesError, onError);
    return () => { session.room.off(RoomEvent.MediaDevicesError, onError); };
  }, [session.room]);

  useEffect(() => {
    if (!connected) return;
    const start = Date.now();
    const timer = setInterval(() => setSeconds(Math.floor((Date.now() - start) / 1000)), 1000);
    return () => clearInterval(timer);
  }, [connected]);

  useEffect(() => {
    const element = transcript.current;
    if (element) element.scrollTop = element.scrollHeight;
  }, [messages]);

  useEffect(() => () => { abort.current?.abort(); void session.room.disconnect(); }, [session.room]);

  async function start() {
    if (connecting || connected) return;
    setBusy(true); setError(''); setSeconds(0);
    setHiddenMessages(new Set(messages.map((message) => message.id)));
    const controller = new AbortController();
    abort.current = controller;
    try {
      await prepare(controller.signal);
      controller.signal.throwIfAborted();
      await session.start({ signal: controller.signal, tracks: { microphone: { enabled: mode === 'voice' } } });
      controller.signal.throwIfAborted();
      // StartAudio offers a user gesture if the browser blocks autoplay.
      await session.room.startAudio().catch(() => {});
    } catch (err) {
      if (!controller.signal.aborted) setError(friendlyError(err));
      await session.end();
    } finally { setBusy(false); }
  }

  async function end() {
    abort.current?.abort();
    await session.end();
  }

  async function media(action: () => Promise<unknown>) {
    if (mediaBusy) return;
    setMediaBusy(true); setError('');
    try { await action(); } catch (err) { setError(friendlyError(err)); }
    finally { setMediaBusy(false); }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!draft.trim() || !agent.isConnected || isSending) return;
    const text = draft.trim();
    setError('');
    try { await send(text); setDraft(''); } catch { setError('Your message could not be sent. Please try again.'); }
  }

  async function copyTranscript() {
    try {
      await navigator.clipboard.writeText(visibleMessages.map((message) =>
        `${message.type === 'agentTranscript' || (message.from && !message.from.isLocal) ? 'Ariana' : 'You'}: ${message.message}`
      ).join('\n\n'));
      setCopied(true); setTimeout(() => setCopied(false), 2000);
    } catch { setError('Could not copy the conversation. Try selecting the text instead.'); }
  }

  return <main className="app-shell">
    <aside className="rail" aria-label="Workspace">
      <a href="/" className="brand-mark" aria-label="Ariana home">a<span>·</span></a>
      <div className="rail-center"><span className="rail-active" aria-label="Conversation"><AudioLines size={22} /></span><span className="rail-line" /></div>
      <button className="icon-button" aria-label="Connection settings" onClick={() => dialog.current?.showModal()}><Settings2 size={20} /></button>
    </aside>
    <div className="workspace">
      <header className="topbar">
        <div className="brand"><span>Ariana</span><span className="brand-separator" /> <span className="workspace-label">Your personal assistant</span></div>
        <div className={`connection-pill ${connected ? 'online' : ''}`}><span />{connected ? 'Connected' : connecting ? 'Connecting' : 'Offline'}</div>
      </header>

      <div className="main-grid">
        <section className="voice-panel" aria-labelledby="voice-heading">
          <div className="eyebrow"><span className="small-line" /> A LITTLE CLARITY, OUT LOUD</div>
          <h1 id="voice-heading">A space to<br />think <em>together.</em></h1>
          <p className="intro">Ask a question. Untangle an idea.<br />Or just start talking.</p>

          <div className={`visualizer-scene ${connected ? 'active' : ''} ${agent.state === 'speaking' ? 'speaking' : ''}`} aria-hidden="true">
            <div className="orbit orbit-outer" /><div className="orbit orbit-middle" />
            <div className="voice-orb"><div className="orb-highlight" /><div className="orb-core">
              {connected && agent.microphoneTrack ? <BarVisualizer state={agent.state} trackRef={agent.microphoneTrack} barCount={7} /> : <AudioLines size={58} strokeWidth={1.3} />}
            </div></div><span className="orbit-point" />
          </div>

          <div className="voice-status" role="status"><span className={connected ? 'status-dot live' : 'status-dot'} />{status}</div>
          {connected && <span className="session-time">{String(Math.floor(seconds / 60)).padStart(2, '0')}:{String(seconds % 60).padStart(2, '0')}</span>}

          {!connected && !connecting ? <>
            <button className="start-button" onClick={start}><Mic size={19} />Start conversation</button>
            <div className="mode-picker" aria-label="Conversation mode">
              <button aria-pressed={mode === 'voice'} onClick={() => setMode('voice')}><Headphones size={15} />Voice</button>
              <button aria-pressed={mode === 'text'} onClick={() => setMode('text')}><Keyboard size={15} />Text</button>
            </div>
          </> : <div className="call-controls">
            {connected && <>
              <button className={`control-button ${!isMicrophoneEnabled ? 'muted' : ''}`} disabled={mediaBusy} aria-label={isMicrophoneEnabled ? 'Mute microphone' : 'Unmute microphone'} aria-pressed={isMicrophoneEnabled} onClick={() => media(() => localParticipant.setMicrophoneEnabled(!isMicrophoneEnabled))}>{isMicrophoneEnabled ? <Mic size={21} /> : <MicOff size={21} />}</button>
              <button className={`control-button ${isScreenShareEnabled ? 'sharing' : ''}`} disabled={mediaBusy} aria-label={isScreenShareEnabled ? 'Stop sharing screen' : 'Share screen'} aria-pressed={isScreenShareEnabled} onClick={() => media(() => localParticipant.setScreenShareEnabled(!isScreenShareEnabled, { audio: false }))}><Monitor size={21} /></button>
            </>}
            <button className="end-button" onClick={end}>{connecting ? <X size={19} /> : <PhoneOff size={19} />}{connecting ? 'Cancel' : 'End session'}</button>
          </div>}
          {isScreenShareEnabled && <p className="sharing-notice"><Monitor size={14} />Ariana can see your shared screen.</p>}
          <StartAudio label="Enable Ariana’s audio" className="enable-audio" />

          <p className="mic-note"><ShieldCheck size={14} />{connected ? 'You control what you share.' : mode === 'voice' ? 'Your microphone stays off until you start.' : 'Start with text. Turn on your mic anytime.'}</p>
        </section>

        <section className="conversation-panel" aria-label="Conversation">
          <header className="conversation-header"><div><h2>Conversation</h2><span>LIVE TRANSCRIPT</span></div><button className="icon-button" aria-label={copied ? 'Transcript copied' : 'Copy transcript'} disabled={!visibleMessages.length} onClick={copyTranscript}>{copied ? <Check size={18} /> : <Copy size={18} />}</button></header>
          <div ref={transcript} className="transcript" role="log" aria-live="polite" aria-relevant="additions text">
            {visibleMessages.length === 0 ? <div className="empty-transcript"><div className="empty-icon"><MessageSquare size={23} strokeWidth={1.4} /><span /></div><h3>Good conversations<br />start somewhere.</h3><p>Your words and Ariana’s replies<br />will appear here as you talk.</p></div>
            : visibleMessages.map((message) => {
              const isAgent = message.type === 'agentTranscript' || (message.from && !message.from.isLocal);
              return <article className={`message ${isAgent ? 'agent-message' : 'user-message'}`} key={message.id}><div className="message-label"><span>{isAgent ? 'ARIANA' : 'YOU'}</span><time>{new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</time></div><p>{message.message}</p></article>;
            })}
            {connected && agent.state === 'thinking' && <div className="thinking-indicator"><span /><span /><span /><span className="sr-only">Ariana is thinking</span></div>}
          </div>
          {error && <div className="error-banner" role="alert"><p>{error}</p><button aria-label="Dismiss error" onClick={() => setError('')}><X size={16} /></button></div>}
          {connected && agent.state === 'failed' && <div className="error-banner" role="alert"><p>Ariana hasn’t joined yet. Check that your agent is running, then end this session and try again.</p></div>}
          <form className="composer" onSubmit={submit}><input ref={composer} value={draft} onChange={(event) => setDraft(event.target.value)} placeholder={connected ? 'Or type a message…' : 'What’s on your mind?'} aria-label="Message Ariana" maxLength={4000} /><button aria-label="Send message" disabled={!agent.isConnected || !draft.trim() || isSending}>{isSending ? <LoaderCircle size={19} className="spin" /> : <ArrowUp size={20} />}</button></form>
          <div className="composer-hint"><Keyboard size={13} />{agent.isConnected ? 'Enter to send · voice and text work together' : 'Start a conversation to send a message'}</div>
        </section>
      </div>

      <section className="suggestions" aria-label="Conversation ideas"><p>A PLACE TO START</p><div>{prompts.map(({ icon: Icon, label, text }) => <button key={label} onClick={() => { setDraft(text); composer.current?.focus(); }}><Icon size={18} /><span>{label}</span><ChevronRight size={16} /></button>)}</div></section>
      <footer className="footer"><span><AudioLines size={14} /> Made for a more natural conversation.</span><span>Powered by LiveKit</span></footer>
    </div>

    <dialog ref={dialog} className="settings-dialog" onClick={(event) => { if (event.target === dialog.current) dialog.current?.close(); }}>
      <header><div><p className="eyebrow">YOUR WORKSPACE</p><h2>Connection settings</h2></div><button className="icon-button" aria-label="Close settings" onClick={() => dialog.current?.close()}><X size={20} /></button></header>
      <p>Enter your private access code if this workspace requires one.</p>
      <form onSubmit={(event) => { event.preventDefault(); onCodeChange(code); dialog.current?.close(); }}><label htmlFor="access-code">Access code</label><input id="access-code" type="password" autoComplete="current-password" value={code} onChange={(event) => setCode(event.target.value)} /><p className="settings-help">Kept only for this open page. Your LiveKit API keys belong on the server.</p><button className="start-button" type="submit">Save settings<Check size={17} /></button></form>
    </dialog>
  </main>;
}
