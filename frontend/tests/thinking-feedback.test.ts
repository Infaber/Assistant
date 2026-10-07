import { test } from "node:test";
import assert from "node:assert/strict";
import { ThinkingFeedback } from "../lib/thinking-feedback";
test("thinking cues wait, stop on interruption, and do not chatter across tool turns", (context) => {
  context.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const cues: string[] = [];
  let stops = 0;
  const feedback = new ThinkingFeedback(
    async (name) => {
      cues.push(name);
    },
    () => {
      stops++;
    },
  );
  feedback.update(true);
  context.mock.timers.tick(1799);
  assert.deepEqual(cues, []);
  context.mock.timers.tick(1);
  assert.deepEqual(cues, ["thinking"]);
  feedback.update(false);
  assert.ok(stops >= 2);
  context.mock.timers.tick(5000);
  assert.equal(cues.length, 1);
  feedback.update(true);
  context.mock.timers.tick(1800);
  assert.equal(cues.length, 1);
  context.mock.timers.tick(13200);
  assert.deepEqual(cues, ["thinking", "still-here"]);
  feedback.cancel();
  context.mock.timers.tick(60000);
  assert.equal(cues.length, 2);
});
test("an async playback attempt loses authorization when a response or user speech begins", (context) => {
  context.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  let active: (() => boolean) | undefined;
  const feedback = new ThinkingFeedback(
    async (_name, check) => {
      active = check;
    },
    () => {},
  );
  feedback.update(true);
  context.mock.timers.tick(1800);
  assert.equal(active?.(), true);
  feedback.update(false);
  assert.equal(active?.(), false);
});
