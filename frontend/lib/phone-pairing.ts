const STORAGE_KEY = "ariana.phone.pairing";
const TOKEN = /^[A-Za-z0-9_-]{40,128}$/;
/** A pairing key is accepted only on the private HTTPS host that serves Ariana. */
export function pairingFromURL(address: string): string | null {
  try {
    const url=new URL(address);
    if(url.protocol!=="https:" || !url.hostname.endsWith(".ts.net") || url.port!=="8443")return null;
    const code=new URLSearchParams(url.hash.slice(1)).get("pair");
    return code && TOKEN.test(code) ? code : null;
  } catch {return null;}
}
export function savedPhonePairing(): string {
  try {const code=localStorage.getItem(STORAGE_KEY);return code && TOKEN.test(code) ? code : "";}catch{return "";}
}
export async function savePhonePairing(code:string) {
  if(!TOKEN.test(code))throw new Error("This pairing link is invalid.");
  const response=await fetch("/api/phone-pairing",{method:"POST",headers:{Authorization:`Bearer ${code}`}});
  if(!response.ok){const result=await response.json();throw new Error(result.error || "Pairing failed. Try a new link from your Mac.");}
  try{localStorage.removeItem(STORAGE_KEY);}catch{}
  window.dispatchEvent(new Event("ariana:phone-pairing-changed"));
}
export async function forgetPhonePairing() {
  const response=await fetch("/api/phone-pairing",{method:"DELETE"});
  // Clear legacy saved keys too, including on a local preview without pairing.
  if(!response.ok && response.status!==404)throw new Error("Could not remove this pairing. Check your connection and retry.");
  try{localStorage.removeItem(STORAGE_KEY);}catch{}
  window.dispatchEvent(new Event("ariana:phone-pairing-changed"));
}
