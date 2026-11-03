import {createHash,timingSafeEqual} from "node:crypto";
type Environment=Record<string,string|undefined>;
export const loopbackHosts = new Set(['localhost', '127.0.0.1', '[::1]']);

export function allowedOrigin(request: Request, env: Environment) {
  const origin = request.headers.get('origin');
  const expected = env.APP_ORIGIN || new URL(request.url).origin;
  if (!origin) return false;
  if (origin === expected) return true;
  // Next dev can reconstruct request.url with localhost even when the browser
  // uses 127.0.0.1. Allow loopback aliases only in development, on the same port.
  if (env.APP_ORIGIN || env.NODE_ENV !== 'development') return false;
  try {
    const actual = new URL(origin);
    const target = new URL(expected);
    return actual.origin === origin && loopbackHosts.has(actual.hostname)
      && loopbackHosts.has(target.hostname) && actual.protocol === target.protocol
      && actual.port === target.port;
  } catch { return false; }
}

export const PHONE_COOKIE="__Host-ariana-phone";
export function privatePhoneServer(env:Environment) {
  if(env.ARIANA_PHONE_ACCESS!=="1")return false;
  try {const url=new URL(env.APP_ORIGIN || "");return url.protocol==="https:" && url.hostname.endsWith(".ts.net") && url.port==="8443";}catch{return false;}
}
export function hasAccessCode(request:Request,code:string,env:Environment,cookieAllowed=true) {
  let supplied=request.headers.get("authorization")?.replace(/^Bearer /,"") || "";
  if(!supplied && cookieAllowed && privatePhoneServer(env)) {
    try {supplied=decodeURIComponent((request.headers.get("cookie") || "").split(";").map(value=>value.trim()).find(value=>value.startsWith(PHONE_COOKIE+"="))?.slice(PHONE_COOKIE.length+1) || "");}catch{return false;}
  }
  const digest=(value:string)=>createHash("sha256").update(value).digest();
  return timingSafeEqual(digest(supplied),digest(code));
}
