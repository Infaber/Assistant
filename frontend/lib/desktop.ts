export type DesktopConfig = {
  desktop: boolean;
  accessCode: string;
  postMessage?: (message: {
    type: "state";
    state: string;
    microphone: boolean;
    output: boolean;
  } | {type:"iphone-status";reveal?:boolean} | {type:"iphone-settings";enabled:boolean} | {type:"iphone-open-tailscale"} | {type:"wake-status"} | {type:"wake-settings";enabled?:boolean;phrase?:"Hey Ariana"|"Ariana"}) => void;
};
declare global {
  interface Window {
    arianaDesktop?: DesktopConfig;
  }
}
export function desktopConfig(): DesktopConfig | undefined {
  return typeof window !== "undefined" && window.arianaDesktop?.desktop
    ? window.arianaDesktop
    : undefined;
}
