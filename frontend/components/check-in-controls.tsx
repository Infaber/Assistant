'use client';

import { useEffect, useState } from 'react';
import type { LocalParticipant } from 'livekit-client';
import { desktopConfig } from '../lib/desktop';
import { Radio } from 'lucide-react';

export default function CheckInControls({ participant, destination, ready }: { participant: LocalParticipant; destination?: string; ready: boolean }) {
  const [enabled, setEnabled] = useState(false);
  const [interval, setIntervalMinutes] = useState(15);
  const [quietStart, setQuietStart] = useState(22);
  const [quietEnd, setQuietEnd] = useState(8);
  const [status, setStatus] = useState('Off');
  const [error, setError] = useState('');
  const [desktop, setDesktop] = useState(false);
  useEffect(() => {
    if (!desktopConfig()) return;
    setDesktop(true);
    try {
      const saved = JSON.parse(localStorage.getItem('ariana.desktop.check-ins') || '{}');
      setEnabled(typeof saved.enabled === 'boolean' ? saved.enabled : true);
      if ([5, 15, 30, 60].includes(saved.interval)) setIntervalMinutes(saved.interval);
      if (Number.isInteger(saved.quietStart) && saved.quietStart >= 0 && saved.quietStart < 24) setQuietStart(saved.quietStart);
      if (Number.isInteger(saved.quietEnd) && saved.quietEnd >= 0 && saved.quietEnd < 24) setQuietEnd(saved.quietEnd);
    } catch { setEnabled(true); }
  }, []);
  useEffect(() => {
    if (desktop) { try { localStorage.setItem('ariana.desktop.check-ins', JSON.stringify({ enabled, interval, quietStart, quietEnd })); } catch {} }
  }, [desktop, enabled, interval, quietStart, quietEnd]);
  useEffect(() => {
    if (!ready || !destination) { setStatus('Connect to enable'); return; }
    let cancelled = false;
    const configure = async () => {
      try {
        const result = JSON.parse(await participant.performRpc({ destinationIdentity: destination, method: 'ariana.check-ins', responseTimeout: 10_000, payload: JSON.stringify({ enabled, interval, quiet_start: quietStart, quiet_end: quietEnd, timezone: Intl.DateTimeFormat().resolvedOptions().timeZone }) }));
        if (cancelled) return;
        if (result.error) throw new Error(result.error);
        setError(''); setStatus(result.enabled ? 'Check-ins active' : 'Off');
      } catch {
        if (!cancelled) { setError('Could not update check-ins. They pause if the connection is lost.'); setStatus('Needs attention'); }
      }
    };
    setStatus('Applying…'); void configure();
    const nativeHeartbeat = () => { void configure(); };
    window.addEventListener('ariana:heartbeat', nativeHeartbeat);
    const heartbeat = window.setInterval(() => { void configure(); }, 30_000);
    return () => { cancelled = true; window.clearInterval(heartbeat); window.removeEventListener('ariana:heartbeat', nativeHeartbeat); };
  }, [participant, destination, ready, enabled, interval, quietStart, quietEnd]);
  return <section className="check-in-panel" aria-label="Proactive check-ins"><div className="check-in-title"><Radio size={15} /><span>CHECK-INS</span><button type="button" role="switch" aria-label="Let Ariana start conversations" aria-checked={enabled} disabled={!ready} onClick={() => setEnabled(!enabled)}>{enabled ? 'ON' : 'OFF'}</button></div><p role="status">{status}</p>{enabled && <><label>After silence<select aria-label="Check-in interval" value={interval} onChange={event => setIntervalMinutes(Number(event.target.value))}>{[5, 15, 30, 60].map(value => <option key={value} value={value}>{value} minutes</option>)}</select></label><div className="quiet-hours"><label>Quiet from<select aria-label="Quiet hours start" value={quietStart} onChange={event => setQuietStart(Number(event.target.value))}>{Array.from({ length: 24 }, (_, hour) => <option key={hour} value={hour}>{String(hour).padStart(2, '0')}:00</option>)}</select></label><label>Until<select aria-label="Quiet hours end" value={quietEnd} onChange={event => setQuietEnd(Number(event.target.value))}>{Array.from({ length: 24 }, (_, hour) => <option key={hour} value={hour}>{String(hour).padStart(2, '0')}:00</option>)}</select></label></div></>}<small>{desktop ? 'Close the window to keep Ariana in the menu bar. Microphone is off until you enable it.' : 'Keep this page and session open.'} One unanswered check-in at a time. Equal quiet hours disable the quiet window.</small>{error && <p className="check-in-error" role="alert">{error}</p>}</section>;
}
