"use client";
import { useEffect, useRef, useState } from 'react';
import { ConnectionState, ParticipantKind, Room, RoomEvent } from 'livekit-client';
import { type AIMode, type ModeStatus, parseModeStatus } from '../lib/ai-mode';

export function useAIMode(room: Room, selected: AIMode, onRequest: (mode:AIMode)=>void, onConfirmed: (mode:AIMode)=>void, restart:()=>Promise<void>) {
  const [status, setStatus] = useState<ModeStatus | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const callbacks = useRef({onRequest,onConfirmed,restart,selected});
  callbacks.current = {onRequest,onConfirmed,restart,selected};
  useEffect(() => {
    const read = () => {
      const agent = [...room.remoteParticipants.values()].find(p=>p.kind===ParticipantKind.AGENT);
      if (!agent) return;
      const a = agent.attributes;
      const next = parseModeStatus({mode:a['ariana.mode'],model:a['ariana.model'],state:a['ariana.state'],error:a['ariana.error'] || ''});
      if (!next) return;
      setStatus(next);
      if (next.state === 'ready' && next.mode===callbacks.current.selected) callbacks.current.onConfirmed(next.mode);
      if (next.error) setError(next.error);
    };
    const offline=()=>{setStatus(null);setPending(false);};
    room.on(RoomEvent.ParticipantAttributesChanged,read);
    room.on(RoomEvent.ParticipantConnected,read);
    room.on(RoomEvent.Disconnected,offline);
    read();
    return ()=>{room.off(RoomEvent.ParticipantAttributesChanged,read);room.off(RoomEvent.ParticipantConnected,read);room.off(RoomEvent.Disconnected,offline);};
  },[room]);
  async function change(mode:AIMode, carryContext=false) {
    callbacks.current.onRequest(mode);
    setError('');
    if (room.state !== ConnectionState.Connected) return;
    const agent=[...room.remoteParticipants.values()].find(p=>p.kind===ParticipantKind.AGENT);
    if (pending) return;
    if (!agent) {await callbacks.current.restart();return;}
    setPending(true);
    const mic = room.localParticipant.isMicrophoneEnabled;
    try {
      // Do not feed speech to the old engine while Local is loading.
      await room.localParticipant.setMicrophoneEnabled(false);
      if (mode==='local' && room.localParticipant.isScreenShareEnabled) await room.localParticipant.setScreenShareEnabled(false);
      const raw=await room.localParticipant.performRpc({destinationIdentity:agent.identity,method:'ariana.mode',payload:JSON.stringify({action:'switch',mode,carry_context:carryContext}),responseTimeout:90_000});
      const next=parseModeStatus(JSON.parse(raw));
      if (!next || next.error || next.state!=='ready' || next.mode!==mode) throw new Error(next?.error || 'Backend has not confirmed the mode change. Check the displayed active engine before speaking.');
      setStatus(next);
      callbacks.current.onConfirmed(next.mode);
      if (mic) await room.localParticipant.setMicrophoneEnabled(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Mode switch failed.');
      // Leave mic off on uncertainty: selected and active may differ.
    } finally {setPending(false);}
  }
  return {status,pending,error,change,selected};
}
