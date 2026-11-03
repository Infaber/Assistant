"use client";
import { useEffect, useRef, useState } from "react";
import { desktopConfig } from "../lib/desktop";
import { Smartphone } from "lucide-react";
import { pairingFromURL, savePhonePairing, savedPhonePairing } from "../lib/phone-pairing";
export default function PhonePairing({onCode}:{onCode:(code:string)=>void}) {
  const [candidate,setCandidate]=useState<string|null>(null);
  const dialog=useRef<HTMLDialogElement>(null);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  useEffect(()=>{
    if(desktopConfig())return;
    const saved=savedPhonePairing();if(saved)onCode(saved);
    const receiveLink=()=>{const code=pairingFromURL(location.href);if(code){setError("");setCandidate(code);history.replaceState(null,"",location.pathname+location.search);}};
    receiveLink();window.addEventListener("hashchange",receiveLink);
    const changed=()=>onCode(savedPhonePairing());
    window.addEventListener("ariana:phone-pairing-changed",changed);
    return()=>{window.removeEventListener("ariana:phone-pairing-changed",changed);window.removeEventListener("hashchange",receiveLink);};
  },[onCode]);
  useEffect(()=>{if(candidate && !dialog.current?.open)dialog.current?.showModal();else if(!candidate)dialog.current?.close();},[candidate]);
  return <dialog ref={dialog} onClose={()=>setCandidate(null)} aria-label="Pair Ariana on this iPhone" className="phone-pairing-dialog">
    <Smartphone size={32}/><h2>Ariana on your iPhone</h2><p>Pair this browser with your Mac’s Ariana. You can chat, talk, and use your assistant’s connected tools while your Mac is awake.</p><p>The microphone stays off until you choose voice.</p>
    {error && <p role="alert">{error}</p>}
    <button autoFocus disabled={busy} onClick={()=>{setBusy(true);void savePhonePairing(candidate!).then(()=>{onCode("");setCandidate(null);}).catch(reason=>setError(reason instanceof Error ? reason.message : "Pairing failed. Try again.")).finally(()=>setBusy(false));}}>{busy ? "Pairing…" : "Pair this iPhone"}</button>
    <button disabled={busy} onClick={()=>setCandidate(null)}>Cancel</button>
  </dialog>;
}
