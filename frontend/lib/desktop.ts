export type DesktopConfig = { desktop: boolean; accessCode: string };
declare global { interface Window { arianaDesktop?: DesktopConfig } }
export function desktopConfig(): DesktopConfig | undefined {
  return typeof window !== 'undefined' && window.arianaDesktop?.desktop ? window.arianaDesktop : undefined;
}
