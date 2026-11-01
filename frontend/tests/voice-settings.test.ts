import test from "node:test";
import assert from "node:assert/strict";
import {
  voiceDraft,
  voicePatch,
  type VoiceSnapshot,
} from "../lib/voice-settings";

test("local voice is never accidentally saved as an unsupported Gemini preset", () => {
  const status: VoiceSnapshot = {
    preferences: {},
    voices: ["Sulafat", "Leda"],
    styles: { sarcasm: ["off", "gentle"] },
    active_voice: "af_heart",
    sample_text: "Fixed sample",
    diagnostics: {},
  };
  const draft = voiceDraft(status);
  assert.equal(draft.google_voice, "");
  assert.equal(voicePatch(draft).google_voice, undefined);
  status.active_voice = "Sulafat";
  assert.equal(voiceDraft(status).google_voice, "Sulafat");
  status.preferences = { google_voice: "Leda", sarcasm: "off" };
  assert.deepEqual(voicePatch(voiceDraft(status)), {
    google_voice: "Leda",
    turn_end_pause: "provider",
    sarcasm: "off",
  });
});
