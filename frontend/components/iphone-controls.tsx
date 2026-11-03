"use client";
import { useEffect, useState } from "react";
import { Smartphone, Copy, Check } from "lucide-react";
import { desktopConfig } from "../lib/desktop";
import { forgetPhonePairing } from "../lib/phone-pairing";
type PhoneStatus = {enabled: boolean; installed: boolean; ready: boolean; phase: string; message: string; url?: string; code?: string; qr?: string};
export default function IPhoneControls() {
  const [native,setNative]=useState(false);
  const [status,setStatus]=useState<PhoneStatus|null>(null);
  const [reveal,setReveal]=useState(false);
  const [pairingError,setPairingError]=useState("");
  const [copied,setCopied]=useState(false);
  useEffect(()=>{
    if(!desktopConfig()) return;
    setNative(true);
    const receive=(event:Event)=>{
      const value=(event as CustomEvent).detail;
      if(value && typeof value.enabled === "boolean" && typeof value.ready === "boolean" && typeof value.installed === "boolean" && typeof value.message === "string" && typeof value.phase === "string") {
        setStatus(current=>({...value,...(current?.code && value.ready && current.url===value.url ? {code:current.code,qr:current.qr} : {})}));
      }
    };
    window.addEventListener("ariana:iphone-status",receive);
    const refresh=()=>desktopConfig()?.postMessage?.({type:"iphone-status"});
    refresh();const timer=setInterval(refresh,3000);
    return()=>{clearInterval(timer);window.removeEventListener("ariana:iphone-status",receive);};
  },[]);
  return <section className="voice-settings iphone-settings" id="iphone-section" aria-label="iPhone access">
    <h3><Smartphone size={18}/> Ariana on iPhone</h3>
    {native ? <>
      <p role="status">{status?.message || "Checking iPhone setup…"}</p>
      <p>Use Ariana’s orb, chat and voice on your iPhone through a private Tailscale connection. Your Mac runs the assistant and must stay awake.</p>
      <div className="iphone-actions"><button onClick={()=>desktopConfig()?.postMessage?.({type:"iphone-open-tailscale"})}>{status?.installed ? "Open Tailscale" : "Get Tailscale for Mac"}</button>
        <button disabled={!status || (!status.enabled && !status.installed) || status.phase === "stopping"} onClick={()=>{setReveal(false);setStatus(current=>current?{...current,code:undefined,qr:undefined}:current);desktopConfig()?.postMessage?.({type:"iphone-settings",enabled:!status?.enabled});}}>{status?.enabled ? "Turn off iPhone access" : "Enable private iPhone access"}</button>
        {status?.installed && status.enabled && !status.ready && <button onClick={()=>desktopConfig()?.postMessage?.({type:"iphone-settings",enabled:true})}>Retry iPhone connection</button>}
      </div>
      {status?.ready && <>
        <p className="iphone-url">{status.url}</p>
        <button onClick={()=>{setReveal(value=>!value);if(reveal)setStatus(current=>current?{...current,code:undefined,qr:undefined}:current);if(!reveal)desktopConfig()?.postMessage?.({type:"iphone-status",reveal:true});}}>{reveal ? "Hide pairing" : "Show iPhone pairing"}</button>
        {reveal && status.code && <div className="iphone-pairing">
          {status.qr && <img src={status.qr} alt="Scan with your iPhone camera to pair Ariana" width={220} height={220}/>}
          <p>On iPhone, connect Tailscale to the same account, then scan this QR code. Tap <strong>Pair this iPhone</strong>.</p>
          <button onClick={()=>{void navigator.clipboard.writeText(`${status.url}/#pair=${status.code}`).then(()=>setCopied(true));}}>{copied ? <Check size={14}/> : <Copy size={14}/>}Copy private pairing link</button>
          <small>The pairing link grants access to your assistant. Turning iPhone access off ends phone sessions and resets this key.</small>
        </div>}
      </>}
      <ol><li>Install Tailscale on your Mac and iPhone. Sign in to the same account.</li><li>Enable private iPhone access here. If requested, enable HTTPS certificates in Tailscale.</li><li>Show pairing, scan the code, and pair in iPhone Safari.</li><li>In Safari, tap Share → Add to Home Screen → Open as Web App → Add.</li></ol>
    </> : <>
      <p>In iPhone Safari, open your paired Ariana link. Tap Share → Add to Home Screen, keep Open as Web App on, then tap Add.</p>
      <p>Keep Tailscale connected and your Mac awake. Voice starts only when you choose it. Keep Ariana open for a voice conversation; iOS can suspend it in the background.</p>
      <button onClick={()=>{void forgetPhonePairing().then(()=>setPairingError("Saved pairing removed.")).catch(error=>setPairingError(error.message));}}>Remove saved phone pairing</button>
      {pairingError && <p role="status">{pairingError}</p>}
    </>}
  </section>;
}
