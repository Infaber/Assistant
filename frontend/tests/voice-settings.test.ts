import test from "node:test";
import assert from "node:assert/strict";
import {
  voiceDraft,
  hasPendingVoiceSettings,
  diagnosticRows,
  parseVoiceSlots,
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
  assert.equal(voiceDraft(status).google_voice, "");
  status.preferences = { google_voice: "Leda", sarcasm: "off" };
  assert.deepEqual(voicePatch(voiceDraft(status)), {
    google_voice: "Leda",
    turn_end_pause: "provider",
    sarcasm: "off",
  });
});


test("known effective styles populate defaults without manufacturing a voice override", () => {
  const status: VoiceSnapshot = {preferences: {}, voices: ["Sulafat"], styles: {warmth:["low","balanced","high"]}, active_voice:"Sulafat", sample_text:"", diagnostics:{}, effective:{warmth:"balanced", google_voice:"Sulafat"}};
  assert.equal(voiceDraft(status).warmth, "balanced");
  assert.equal(voiceDraft(status).google_voice, "");
  assert.equal(voicePatch(voiceDraft(status)).google_voice, undefined);
});

test("pending settings compare to the active snapshot, not the loaded A/B draft", () => {
  const status: VoiceSnapshot = {preferences:{google_voice:"Leda"}, voices:[], styles:{}, active_voice:"Sulafat",sample_text:"",diagnostics:{},effective:{google_voice:"Leda",warmth:"high"},active_settings:{google_voice:"Sulafat",warmth:"balanced"}};
  assert.equal(hasPendingVoiceSettings(status), true);
  const draft = voiceDraft(status); draft.warmth = "low";
  assert.equal(status.active_settings!.warmth, "balanced");
  status.active_settings = {...status.effective};
  assert.equal(hasPendingVoiceSettings(status), false);
});

test("diagnostics reject non-numerical payloads and retain measured percentiles", () => {
  assert.deepEqual(diagnosticRows({e2e_latency:{samples:20,median_ms:500,p95_ms:900},invalid:{samples:2,median_ms:NaN,p95_ms:Infinity},text:{transcript:"private"}}), [{stage:"e2e_latency",samples:20,median:500,p95:900}]);
});

test("corrupt comparison storage cannot break settings or introduce unrelated preferences", () => {
  for (const raw of ["null", "[]", "invalid", '{"A":{"home_city":"Oslo"}}', '{"A":{"warmth":42}}']) assert.deepEqual(parseVoiceSlots(raw), {});
  assert.deepEqual(parseVoiceSlots('{"A":{"google_voice":"","warmth":"balanced"},"B":null}'), {A:{google_voice:"",warmth:"balanced"}});
});
