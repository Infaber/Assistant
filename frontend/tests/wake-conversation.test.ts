import assert from "node:assert/strict";
import test from "node:test";
import { WakeConversation } from "../lib/wake-conversation";

test("wake activation is single-owner and canceled readiness cannot reopen capture", () => {
  const state = new WakeConversation();
  const token = state.begin(0)!;
  assert.equal(state.begin(1), null);
  state.cancel();
  assert.equal(state.ready(token, 100), false);
  assert.equal(state.active, false);
  const next = state.begin(200)!;
  assert.equal(state.ready(next, 300), true);
  assert.equal(state.begin(400), null);
});
test("a long story, thinking and output extend idle timeout on every tick", () => {
  const state = new WakeConversation(90);
  state.ready(state.begin(0)!, 1000);
  for (let t = 1000; t < 1800000; t += 1000)
    assert.equal(state.due(t, true), false);
  assert.equal(state.due(1800000, false), false);
  assert.equal(state.due(1890000, false), true);
  state.cancel();
  assert.equal(state.due(2000000, false), false);
});
test("readiness time, not connection startup, starts the inactivity window", () => {
  const state = new WakeConversation(90);
  const token = state.begin(0)!;
  assert.equal(state.due(120000, false), false);
  state.ready(token, 120000);
  assert.equal(state.due(209999, false), false);
  assert.equal(state.due(210000, false), true);
});

test("cold activation waits for the agent while muted and cancellation ends the wait", async () => {
  const { waitForWakeReady } = await import("../lib/wake-conversation");
  const state = new WakeConversation();
  const token = state.begin(0)!;
  let now = 0;
  assert.equal(
    await waitForWakeReady(
      state,
      token,
      () => now >= 500,
      () => now,
      async () => {
        now += 100;
      },
      1000,
    ),
    true,
  );
  state.cancel();
  const next = state.begin(now)!;
  assert.equal(
    await waitForWakeReady(
      state,
      next,
      () => false,
      () => now,
      async () => {
        now += 100;
        state.cancel();
      },
      1000,
    ),
    false,
  );
  const third = state.begin(now)!;
  assert.equal(
    await waitForWakeReady(
      state,
      third,
      () => false,
      () => now,
      async () => {
        now += 100;
      },
      200,
    ),
    false,
  );
});

test("uncertain microphone publication and late canceled capture fail closed", async () => {
  const { publishWakeMicrophone } = await import("../lib/wake-conversation");
  const state = new WakeConversation();
  let captured = false;
  const first = state.begin(0)!;
  await assert.rejects(
    publishWakeMicrophone(
      state,
      first,
      () => 1,
      async () => {
        captured = true;
        throw new Error("publication uncertain");
      },
      async () => {
        captured = false;
      },
    ),
  );
  assert.equal(captured, false);
  assert.equal(state.active, false);
  const next = state.begin(2)!;
  assert.equal(
    await publishWakeMicrophone(
      state,
      next,
      () => 3,
      async () => {
        captured = true;
        state.cancel();
      },
      async () => {
        captured = false;
      },
    ),
    false,
  );
  assert.equal(captured, false);
  let enableCalls = 0;
  assert.equal(
    await publishWakeMicrophone(
      state,
      next,
      () => 4,
      async () => {
        enableCalls++;
      },
      async () => {},
    ),
    false,
  );
  assert.equal(enableCalls, 0);
});


test("a canceled publication retains ownership until cleanup finishes", async () => {
  const { publishWakeMicrophone } = await import("../lib/wake-conversation");
  const state = new WakeConversation();
  let finish!: () => void;
  let muted = false;
  const token = state.begin(0)!;
  const publication = publishWakeMicrophone(state, token, () => 1,
    () => new Promise<void>(resolve => { finish = resolve; }),
    async () => { muted = true; });
  state.cancel();
  assert.equal(state.begin(2), null);
  finish();
  assert.equal(await publication, false);
  assert.equal(muted, true);
  assert.notEqual(state.begin(3), null);
});

for (const reason of ["consent revoked", "sleep", "reconnect", "standby"]) {
  test(`${reason} cancels delayed wake readiness without publishing`, async () => {
    const {waitForWakeReady} = await import("../lib/wake-conversation");
    const state = new WakeConversation();
    const token = state.begin(0)!;
    let now = 0;
    const ready = await waitForWakeReady(state, token, () => now > 0, () => now,
      async () => { now += 100; state.cancel(); }, 1000);
    assert.equal(ready, false);
    assert.equal(state.active, false);
  });
}


test("a rejected canceled publication does not turn intentional cancellation into an error", async () => {
  const {publishWakeMicrophone} = await import("../lib/wake-conversation");
  const state = new WakeConversation();
  const token = state.begin(0)!;
  let reject!: (error: Error) => void;
  let muted = false;
  const result = publishWakeMicrophone(state, token, () => 1,
    () => new Promise<void>((_, fail) => {reject = fail;}), async () => {muted = true;});
  state.cancel();
  reject(new Error("track ended after sleep"));
  assert.equal(await result, false);
  assert.equal(muted, true);
  assert.notEqual(state.begin(2), null);
});

test("microphone cleanup failures remain visible and do not leak ownership", async () => {
  const {publishWakeMicrophone} = await import("../lib/wake-conversation");
  const state = new WakeConversation();
  const token = state.begin(0)!;
  await assert.rejects(publishWakeMicrophone(state, token, () => 1,
    async () => {state.cancel();}, async () => {throw new Error("mute failed");}), /mute failed/);
  assert.equal(state.active, false);
  assert.notEqual(state.begin(2), null);
});
