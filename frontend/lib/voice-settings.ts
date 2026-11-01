export type VoiceSnapshot = {
  preferences: Record<string, string>;
  voices: string[];
  styles: Record<string, string[]>;
  active_voice: string;
  sample_text: string;
  diagnostics: Record<string, unknown>;
};
export function voiceDraft(status: VoiceSnapshot): Record<string, string> {
  return {
    turn_end_pause: status.preferences.turn_end_pause || "provider",
    google_voice:
      status.preferences.google_voice ||
      (status.voices.includes(status.active_voice) ? status.active_voice : ""),
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
