import assert from "node:assert/strict";
import test from "node:test";
import {
  CompanionLifecycle,
  terminalConnectionError,
} from "../lib/companion-lifecycle";
test("bounded reconnect, no duplicate connection, and reset after success", () => {
  const policy = new CompanionLifecycle();
  assert.deepEqual(
    Array.from({ length: 8 }, () => policy.delay()),
    [2000, 4000, 8000, 16000, 32000, 60000, 60000, 60000],
  );
  assert.equal(policy.delay(), null);
  policy.connected();
  assert.equal(policy.delay(), 2000);
  policy.connecting = true;
  assert.equal(policy.delay(), null);
});
test("pause, sleep, network and terminal errors suppress retries", () => {
  for (const flag of ["paused", "sleeping", "terminal"] as const) {
    const policy = new CompanionLifecycle();
    policy[flag] = true;
    assert.equal(policy.delay(), null);
    policy.resume();
    assert.equal(policy.delay(), 2000);
  }
  const policy = new CompanionLifecycle();
  policy.online = false;
  assert.equal(policy.delay(), null);
  assert.equal(terminalConnectionError(new Error("API key invalid")), true);
  assert.equal(terminalConnectionError(new Error("network lost")), false);
});
