'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import {
  RoomAudioRenderer, SessionProvider, StartAudio,
  useAgent, useLocalParticipant, useSession, useSessionMessages,
  type UseSessionReturn,
} from '@livekit/components-react';
import { ConnectionState, DisconnectReason, ParticipantKind, RoomEvent, TokenSource, type RemoteParticipant, type DataPacket_Kind } from 'livekit-client';
import { ArrowUp, Check, ChevronRight, Compass, Copy, Headphones,
  Keyboard, LoaderCircle, Mic, MicOff, Monitor, PhoneOff,
  Settings2, ShieldCheck, Sparkles, Brain, X, Aperture, ArrowUpRight,
  Globe, CalendarDays, Music2, House, Maximize2, Minimize2, Command, Radio, ScanLine } from 'lucide-react';

import { desktopConfig } from '../lib/desktop';
import SharingComposer, { type SharedMessage } from './sharing-composer';
import CheckInControls from './check-in-controls';
import IntelligenceCore from './intelligence-core';
import { parseActivity, updateActivity, finishActivity, type Activity } from '../lib/activity';

const capabilities = [
  { icon: Globe, label: 'Research', hint: 'Find a clearer answer', text: 'I have something I would like you to research.' },
  { icon: CalendarDays, label: 'My day', hint: 'Calendar & reminders', text: 'What is on my calendar today?' },
  { icon: House, label: 'My space', hint: 'Home & Mac controls', text: 'What can you help me control on my Mac and at home?' },
  { icon: Music2, label: 'Music', hint: 'Your Spotify controls', text: 'What is currently playing on Spotify?' },
  { icon: Brain, label: 'Memory', hint: 'A little more personal', text: 'What do you remember about me?' },
];

const prompts = [
  { icon: Compass, label: 'Plan my day', text: 'Can you help me plan my day?' },
  { icon: Sparkles, label: 'Think it through', text: 'Can you help me think through an idea?' },
  { icon: Brain, label: 'What you remember', text: 'What do you remember about me?' },
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
  const accessCode = useRef(desktopConfig()?.accessCode || '');
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
  const [focused, setFocused] = useState(false);
  const [panel, setPanel] = useState<'conversation' | 'activity'>('conversation');
  const [activity, setActivity] = useState<Activity[]>([]);
  const [providerError, setProviderError] = useState('');
  const [clock, setClock] = useState('');
  const [mode, setMode] = useState<'voice' | 'text'>('voice');
  const [busy, setBusy] = useState(false);
  const [mediaBusy, setMediaBusy] = useState(false);
  const [error, setError] = useState('');
  const [draft, setDraft] = useState('');
  const [copied, setCopied] = useState(false);
  const [code, setCode] = useState('');
  const [sharedMessages, setSharedMessages] = useState<SharedMessage[]>([]);
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
  const conversation = [...visibleMessages.map(message => ({ ...message, files: [] as SharedMessage['files'], isAgent: message.type === 'agentTranscript' || !!(message.from && !message.from.isLocal) })), ...sharedMessages.map(message => ({ ...message, isAgent: false }))].sort((a, b) => a.timestamp - b.timestamp);
  const status = providerError ? 'Connection needs attention' : reconnecting ? 'Reconnecting' : !connected ? (connecting ? 'Connecting' : 'Ready when you are')
    : agent.state === 'failed' ? 'Agent unavailable' : agent.state === 'speaking' ? 'Ariana is speaking'
    : agent.state === 'thinking' ? 'Thinking it through' : !agent.isConnected ? 'Finding Ariana'
    : isMicrophoneEnabled ? 'Listening to you' : 'Ready for your message';

  useEffect(() => {
    const tick = () => setClock(new Date().toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' }));
    tick();
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    const shortcut = (event: KeyboardEvent) => {
      if (dialog.current?.open) return;
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault(); setFocused(false); setPanel('conversation');
        requestAnimationFrame(() => composer.current?.focus());
      }
    };
    window.addEventListener('keydown', shortcut);
    return () => window.removeEventListener('keydown', shortcut);
  }, []);

  useEffect(() => {
    if (error || providerError || agent.state === 'failed') setFocused(false);
  }, [error, providerError, agent.state]);

  useEffect(() => {
    const receive = (payload: Uint8Array, participant?: RemoteParticipant, _kind?: DataPacket_Kind, topic?: string) => {
      if (topic !== 'ariana.activity' || participant?.kind !== ParticipantKind.AGENT) return;
      const event = parseActivity(payload);
      if (!event) return;
      setActivity(rows => updateActivity(rows, event));
      if (event.kind === 'system' && event.status === 'failed') setProviderError(event.detail);
    };
    const disconnected = (reason?: DisconnectReason) => {
      setActivity(finishActivity);
      if (reason !== DisconnectReason.CLIENT_INITIATED) setProviderError(current => current || 'The connection ended unexpectedly. Reconnect to start a fresh session; check any unfinished action before repeating it.');
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
  }, [messages, sharedMessages]);

  useEffect(() => () => { abort.current?.abort(); void session.room.disconnect(); }, [session.room]);

  async function start(asText = false) {
    if (connecting || connected) return;
    setBusy(true); setError(''); setProviderError(''); setActivity([]); setSharedMessages([]); setSeconds(0);
    setHiddenMessages(new Set(messages.map((message) => message.id)));
    const controller = new AbortController();
    abort.current = controller;
    try {
      await prepare(controller.signal);
      controller.signal.throwIfAborted();
      await session.start({ signal: controller.signal, tracks: { microphone: { enabled: !asText && mode === 'voice' } } });
      controller.signal.throwIfAborted();
      // StartAudio offers a user gesture if the browser blocks autoplay.
      await session.room.startAudio().catch(() => {});
    } catch (err) {
      if (!controller.signal.aborted) setError(friendlyError(err));
      await session.end();
    } finally { setBusy(false); }
  }

  useEffect(() => {
    if (!desktopConfig()) return;
    setMode('text');
    const automaticStart = window.setTimeout(() => { void start(true); }, 400);
    const pause = () => { abort.current?.abort(); void session.end(); };
    window.addEventListener('ariana:pause', pause);
    return () => { window.clearTimeout(automaticStart); window.removeEventListener('ariana:pause', pause); };
  }, [session.room]);

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

  async function copyTranscript() {
    try {
      await navigator.clipboard.writeText(conversation.map((message) =>
        `${message.isAgent ? 'Ariana' : 'You'}: ${message.message}${message.files.length ? '\nAttachments: ' + message.files.map(file => file.name).join(', ') : ''}`
      ).join('\n\n'));
      setCopied(true); setTimeout(() => setCopied(false), 2000);
    } catch { setError('Could not copy the conversation. Try selecting the text instead.'); }
  }

  const coreState = error || providerError || agent.state === 'failed' ? 'error' : connecting || reconnecting || (connected && !agent.isConnected) ? 'connecting' : !connected ? 'standby' : agent.state === 'thinking' ? 'thinking' : agent.state === 'speaking' ? 'speaking' : isMicrophoneEnabled ? 'listening' : 'ready';
  const sessionTime = `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
  function stagePrompt(text: string) {
    setFocused(false); setPanel('conversation'); setDraft(text);
    requestAnimationFrame(() => { composer.current?.focus(); composer.current?.scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'nearest' }); });
  }

  return <main className={`app-shell ${focused ? 'focus-mode' : ''}`}>
    <div className="ambient-grid" aria-hidden="true" />
    <header className="topbar">
      <a href="/" className="brand" aria-label="Ariana home"><span className="brand-mark"><Aperture size={28} strokeWidth={1.3} /></span><span className="brand-word">ARIANA<span>PERSONAL INTELLIGENCE</span></span></a>
      <div className="topbar-centre"><span className="tiny-cross">+</span> YOUR WORLD. IN SYNC. <span className="tiny-cross">+</span></div>
      <div className="topbar-controls">
        <div className={`connection-pill ${connected ? 'online' : ''}`}><span />{reconnecting ? 'RECONNECTING' : connected ? 'CONNECTED' : connecting ? 'CONNECTING' : 'STANDBY'}</div>
        <time className="local-clock" aria-label="Local time">{clock || '—:—:—'}</time>
        <button className="icon-button focus-toggle" aria-label={focused ? 'Exit focus mode' : 'Enter focus mode'} aria-pressed={focused} onClick={() => setFocused(!focused)}>{focused ? <Minimize2 size={17} /> : <Maximize2 size={17} />}</button>
        <button className="icon-button" aria-label="Connection settings" onClick={() => dialog.current?.showModal()}><Settings2 size={18} /></button>
      </div>
    </header>

    <div className="workspace">
      <aside className="systems-panel" aria-label="Workspace capabilities">
        <div className="section-label">WORKSPACE<span>01</span></div>
        <div className="workspace-active"><Aperture size={17} />Overview<span className="active-indicator" /></div>
        <div className="capabilities-heading">CAPABILITIES</div>
        <nav aria-label="Draft a request">{capabilities.map(({ icon: Icon, label, hint, text }) => <button className="capability" key={label} onClick={() => stagePrompt(text)}><Icon size={18} strokeWidth={1.4} /><span>{label}<small>{hint}</small></span><ArrowUpRight size={13} /></button>)}</nav>
        <div className="session-readout"><div className="section-label">SESSION<ScanLine size={13} /></div><dl><div><dt>Connection</dt><dd>{reconnecting ? 'Reconnecting' : connected ? 'Established' : connecting ? 'Connecting' : 'Not started'}</dd></div><div><dt>Microphone</dt><dd>{isMicrophoneEnabled && connected ? 'Active' : 'Off'}</dd></div><div><dt>Screen</dt><dd>{isScreenShareEnabled ? 'Sharing' : 'Not shared'}</dd></div><div><dt>Messages</dt><dd>{String(visibleMessages.length).padStart(2, '0')}</dd></div></dl></div>
        <div className="sidebar-note"><ShieldCheck size={15} /><p>ON YOUR TERMS<span>You choose when to connect<br />and what to share.</span></p></div>
      </aside>

      <section className="voice-panel" aria-labelledby="voice-heading">
        <div className="core-heading"><span className="section-label">INTELLIGENCE CORE</span><span className="core-state-label">{coreState.toUpperCase()}</span></div>
        <div className="hero-title"><div className="eyebrow">ALWAYS A LITTLE AHEAD</div><h1 id="voice-heading">At your command.</h1><p>Your ideas. Your world. A little more possible.</p></div>
        <div className="visualizer-scene">
          <div className="core-callout callout-left"><span>INPUT MODE</span><strong>{connected ? isMicrophoneEnabled ? 'VOICE + TEXT' : 'TEXT' : mode.toUpperCase()}</strong><i /></div>
          <IntelligenceCore state={coreState} track={agent.microphoneTrack} />
          <div className="core-callout callout-right"><span>SESSION TIME</span><strong>{connected ? sessionTime : '00:00'}</strong><i /></div>
          <span className="core-caption">A R I A N A <span>/</span> INTERACTIVE CORE</span>
        </div>
        <div className="voice-status" role="status"><span className={`status-dot ${connected ? 'live' : ''}`} />{status}</div>
          {!connected && !connecting ? <>
            <button className="start-button" onClick={() => { void start(); }}><Mic size={19} />Start conversation</button>
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

        <CheckInControls participant={localParticipant} destination={agent.isConnected ? agent.identity : undefined} ready={agent.isConnected && !providerError} />
        <div className="quick-commands"><div className="section-label">QUICK START<span>SELECT TO DRAFT</span></div><div>{prompts.map(({ icon: Icon, label, text }) => <button key={label} onClick={() => stagePrompt(text)}><Icon size={15} strokeWidth={1.5} /><span>{label}</span><ChevronRight size={13} /></button>)}</div></div>
      </section>
        <section className="conversation-panel" aria-label="Conversation">
          <header className="conversation-header"><div><h2>{panel === 'conversation' ? 'Conversation' : 'Activity'}<span className="section-index">02</span></h2><span>{panel === 'conversation' ? 'VOICE + TEXT CHANNEL' : 'LIVE ACTION FEED'}</span></div><button className="icon-button" aria-label={copied ? 'Transcript copied' : 'Copy transcript'} disabled={!conversation.length} onClick={copyTranscript}>{copied ? <Check size={18} /> : <Copy size={18} />}</button></header>
          <div className="channel-switch" role="group" aria-label="Channel view"><button aria-pressed={panel === 'conversation'} onClick={() => setPanel('conversation')}>Conversation</button><button aria-pressed={panel === 'activity'} onClick={() => setPanel('activity')}>Activity{' '}<span>{activity.length}</span></button></div>
          {panel === 'activity' ? <div className="activity-feed" role="log" aria-label="Action activity" aria-live="polite">
            {!activity.length ? <div className="empty-transcript"><div className="empty-icon"><ScanLine size={26} strokeWidth={1} /></div><h3>Waiting for a task.</h3><p>Real actions appear here as Ariana works.<br />Page text and personal data stay out of this feed.</p></div>
            : [...activity].reverse().map(item => <article className={`activity-item activity-${item.status}`} key={item.id}><div className="activity-line"><span className="activity-marker">{item.status === 'running' || item.status === 'recovering' ? <LoaderCircle size={14} className="spin" /> : item.status === 'verified' ? <Check size={14} /> : <ScanLine size={14} />}</span><strong>{item.label}</strong><time>{new Date(item.timestamp * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</time></div><span className="activity-state">{({ running: 'Working', returned: 'Result returned', verified: 'Verified', approval: 'Approval needed', uncertain: 'Needs checking', failed: 'Could not complete', recovering: 'Reconnecting' })[item.status]}</span><p>{item.detail}</p></article>)}
          </div> : <div ref={transcript} className="transcript" role="log" aria-live="polite" aria-relevant="additions text">
            {conversation.length === 0 ? <div className="empty-transcript"><div className="empty-icon"><Radio size={27} strokeWidth={1} /><span /></div><h3>Channel standing by.</h3><p>Open a connection to Ariana.<br />Your exchange will appear here.</p></div>
            : conversation.map((message) => {
              const isAgent = message.isAgent;
              return <article className={`message ${isAgent ? 'agent-message' : 'user-message'}`} key={message.id}><div className="message-label"><span>{isAgent ? 'ARIANA' : 'YOU'}</span><time>{new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</time></div><p>{message.message}</p>{message.files.length > 0 && <div className="shared-files">{message.files.map((file, index) => <div key={index}>{file.preview && <img src={file.preview} alt={file.name} />}<span>{file.name}</span></div>)}</div>}</article>;
            })}
            {connected && agent.state === 'thinking' && <div className="thinking-indicator"><span /><span /><span /><span className="sr-only">Ariana is thinking</span></div>}
          </div>}
          {providerError && <div className="error-banner" role="alert"><p>{providerError}</p><button className="reconnect-button" disabled={connecting} onClick={() => { void (connected ? end() : start()); }}>{connected ? 'End session' : 'Reconnect'}</button></div>}
          {error && <div className="error-banner" role="alert"><p>{error}</p><button aria-label="Dismiss error" onClick={() => setError('')}><X size={16} /></button></div>}
          {connected && agent.state === 'failed' && <div className="error-banner" role="alert"><p>Ariana hasn’t joined yet. Check that your agent is running, then end this session and try again.</p></div>}
          <SharingComposer participant={localParticipant} destination={agent.isConnected ? agent.identity : undefined} ready={agent.isConnected && !isSending && !providerError} draft={draft} setDraft={setDraft} inputRef={composer} onText={async text => { await send(text); }} onShared={message => setSharedMessages(current => [...current, message])} onError={setError} sessionKey={connected} />
        </section>
    </div>
    <footer className="footer"><span><span className="footer-dot" />ARIANA<span className="footer-divider">/</span>PERSONAL WORKSPACE</span><button onClick={() => stagePrompt(draft)}><Command size={12} /><span>⌘ / CTRL + K</span><span className="footer-command-label">Command input</span></button><span>VOICE & TEXT<span className="footer-divider">/</span>LIVEKIT</span></footer>
    <dialog ref={dialog} className="settings-dialog" onClick={(event) => { if (event.target === dialog.current) dialog.current?.close(); }}>
      <header><div><p className="eyebrow">YOUR WORKSPACE</p><h2>Connection settings</h2></div><button className="icon-button" aria-label="Close settings" onClick={() => dialog.current?.close()}><X size={20} /></button></header>
      <p>Enter your private access code if this workspace requires one.</p>
      <form onSubmit={(event) => { event.preventDefault(); onCodeChange(code); dialog.current?.close(); }}><label htmlFor="access-code">Access code</label><input id="access-code" type="password" autoComplete="current-password" value={code} onChange={(event) => setCode(event.target.value)} /><p className="settings-help">Kept only for this open page. Your LiveKit API keys belong on the server.</p><button className="start-button" type="submit">Save settings<Check size={17} /></button></form>
    </dialog>
  </main>;
}
