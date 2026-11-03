"use client";
import { useEffect, useState, type ReactNode } from "react";
import type { LocalParticipant } from "livekit-client";
import { AudioLines, Mic, MicOff } from "lucide-react";
import { responseStatistics } from "../lib/session-diagnostics";

export default function SessionPanel({ participant, destination, ready, mode, microphone, wakeState, children }: {
  participant: LocalParticipant; destination?: string; ready: boolean; mode?: "normal" | "local";
  microphone: boolean; wakeState: string; children: ReactNode;
}) {
  const [snapshot, setSnapshot] = useState<{voice: string; values: number[]} | null>(null);
  const [unavailable, setUnavailable] = useState(false);
  useEffect(() => {
    let canceled = false;
    let timer: ReturnType<typeof setTimeout>;
    setSnapshot(null); setUnavailable(false);
    if (!ready || !destination) return;
    async function refresh() {
      try {
        const result = JSON.parse(await participant.performRpc({ destinationIdentity: destination!, method: "ariana.voice-settings", payload: JSON.stringify({action: "status"}), responseTimeout: 10000 }));
        if (result.error) throw new Error("Unavailable");
        if (!canceled) {
          setSnapshot({voice: typeof result.active_voice === "string" ? result.active_voice : "—", values: responseStatistics(result.response_times_ms).values});
          setUnavailable(false);
        }
      } catch { if (!canceled) {setUnavailable(true); setSnapshot(null);} }
      finally { if (!canceled) timer = setTimeout(refresh, 8000); }
    }
    void refresh();
    return () => { canceled = true; clearTimeout(timer); };
  }, [participant, destination, ready, mode]);
  const stats = responseStatistics(snapshot?.values);
  const chart = stats.values.slice(-20);
  const ceiling = Math.max(1, Math.ceil(Math.max(...chart, 0) / 500) / 2);
  const points = chart.map((value, index) => `${42 + index * 260 / Math.max(1, chart.length - 1)},${130 - value / 1000 / ceiling * 112}`);
  const format = (value: number | null) => value === null ? "—" : `${(value / 1000).toFixed(1)} s`;
  return <section className="session-panel" aria-label="Session diagnostics">
    <h2>Session</h2>
    <h3>Response time</h3>
    <div className="response-chart">
      <svg viewBox="0 0 320 155" role="img" aria-label={chart.length ? `Last ${chart.length} response times in seconds` : "No response time measurements yet"}>
        {[0, 0.5, 1].map(fraction => <g key={fraction}><text x="0" y={134 - fraction * 112}>{(ceiling * fraction).toFixed(1)} s</text><line x1="42" x2="306" y1={130 - fraction * 112} y2={130 - fraction * 112}/></g>)}
        {points.length > 1 && <polyline points={points.join(" ")} />}
        {points.map((point, index) => <circle key={index} cx={point.split(",")[0]} cy={point.split(",")[1]} r="2.8"><title>Response {index + 1}: {(chart[index] / 1000).toFixed(2)} seconds</title></circle>)}
      </svg>
      {!chart.length && <p>{unavailable ? "Diagnostics unavailable" : ready ? "Awaiting a voice response" : "Connect to see timings"}</p>}
    </div>
    <div className="session-statistics"><div><strong>{format(stats.median)}</strong><span>Median</span></div><div><strong>{format(stats.p95)}</strong><span>p95</span></div></div>
    <p className="sample-count">{stats.values.length} samples</p>
    <p className="metric-note">Speech end → response start, measured by the agent. Recent session samples.</p>
    <dl className="session-details"><div><dt>Voice</dt><dd>{ready ? snapshot?.voice || "—" : "—"}</dd></div><div><dt>Engine</dt><dd>{ready ? mode === "local" ? "Unrestricted" : "Normal" : "Not connected"}</dd></div></dl>
    <div className="session-signals"><p>{microphone ? <Mic size={18}/> : <MicOff size={18}/>}Microphone {microphone ? "on" : "off"}</p><p><AudioLines size={18}/>Conversation: {wakeState.toLowerCase()}</p></div>
    {children}
  </section>;
}
