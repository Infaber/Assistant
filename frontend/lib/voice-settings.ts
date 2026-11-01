export type VoiceSnapshot = {
  preferences: Record<string, string>;
  voices: string[];
  styles: Record<string, string[]>;
  active_voice: string;
  mode?: "normal" | "local";
  effective?: Record<string, string>;
  active_settings?: Record<string, string>;
  configured_default_voice?: string;
  samples?: Record<string, string>;
  local_speeds?: string[];
  sample_text: string;
  diagnostics: Record<string, unknown>;
};
export function voiceDraft(status: VoiceSnapshot): Record<string, string> {
  return {
    ...status.effective,
    turn_end_pause: status.preferences.turn_end_pause || "provider",
    google_voice:
      status.preferences.google_voice ||
      "",
    ...Object.fromEntries(
      Object.keys(status.styles)
        .filter((key) => status.preferences[key])
        .map((key) => [key, status.preferences[key]]),
    ),
  };
}
export function voicePatch(
  draft: Record<string, string>,
): Record<string, string> {
  return Object.fromEntries(
    Object.entries(draft).filter(([, value]) => value !== ""),
  );
}

export function settingAppliesToMode(key: string, mode: "normal" | "local" = "normal"): boolean {
  if (key === "local_speed") return mode === "local";
  if (key === "google_voice" || key === "turn_end_pause") return mode === "normal";
  return true;
}

export function hasPendingVoiceSettings(status: VoiceSnapshot): boolean {
  if (!status.effective || !status.active_settings) return false;
  return Object.entries(status.effective).some(([key, value]) =>
    settingAppliesToMode(key, status.mode) &&
    key in status.active_settings! && status.active_settings![key] !== value,
  );
}

export type TimingRow = {stage: string; samples: number; median: number; p95: number};
export function diagnosticRows(value: unknown): TimingRow[] {
  if (!value || typeof value !== "object") return [];
  return Object.entries(value).flatMap(([stage, item]) => {
    if (!item || typeof item !== "object") return [];
    const row = item as Record<string, unknown>;
    if (![row.samples, row.median_ms, row.p95_ms].every(n => typeof n === "number" && Number.isFinite(n) && n >= 0)) return [];
    return [{stage, samples:row.samples as number, median:row.median_ms as number, p95:row.p95_ms as number}];
  });
}

export function parseVoiceSlots(raw: string | null): Record<string, Record<string,string>> {
  if (!raw || raw.length > 4096) return {};
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {};
    const keys = new Set(["google_voice","turn_end_pause","local_speed","delivery","warmth","playfulness","sarcasm","initiative","talkativeness"]);
    const result: Record<string,Record<string,string>> = {};
    for (const name of ["A", "B"]) {
      const slot = (parsed as Record<string,unknown>)[name];
      if (!slot || typeof slot !== "object" || Array.isArray(slot)) continue;
      const entries = Object.entries(slot);
      if (entries.length && entries.every(([key,value]) => keys.has(key) && typeof value === "string" && value.length <= 40 && !/[\x00-\x1f]/.test(value)))
        result[name] = Object.fromEntries(entries) as Record<string,string>;
    }
    return result;
  } catch { return {}; }
}
