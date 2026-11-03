// Monotonic, session-local wake ownership. No audio or transcript storage.
export class WakeConversation {
  active = false;
  pending = false;
  private lastActivity = 0;
  private generation = 0;
  private publishing = false;
  acquirePublication(token: number): boolean {
    if (this.publishing || !this.isPending(token)) return false;
    this.publishing = true;
    return true;
  }
  releasePublication() { this.publishing = false; }
  constructor(public idleSeconds = 90) {}
  begin(now: number): number | null {
    if (this.pending || this.active || this.publishing) return null;
    this.pending = true;
    this.lastActivity = now;
    return ++this.generation;
  }
  isPending(token: number): boolean {
    return token === this.generation && this.pending;
  }
  ready(token: number, now: number): boolean {
    if (token !== this.generation || !this.pending) return false;
    this.pending = false;
    this.active = true;
    this.lastActivity = now;
    return true;
  }
  activity(now: number, busy: boolean) {
    if (this.active && busy) this.lastActivity = now;
  }
  due(now: number, busy: boolean): boolean {
    this.activity(now, busy);
    return (
      this.active && !busy && now - this.lastActivity >= this.idleSeconds * 1000
    );
  }
  cancel() {
    this.generation++;
    this.pending = false;
    this.active = false;
  }
}

// Wait while capture is muted. A canceled activation cannot publish a microphone.
export async function waitForWakeReady(
  state: WakeConversation,
  token: number,
  ready: () => boolean,
  now: () => number,
  pause: () => Promise<void>,
  timeoutMs: number,
): Promise<boolean> {
  const started = now();
  while (state.isPending(token) && now() - started < timeoutMs) {
    if (ready()) return true;
    await pause();
  }
  return false;
}

export async function publishWakeMicrophone(
  state: WakeConversation,
  token: number,
  now: () => number,
  enable: () => Promise<void>,
  disable: () => Promise<void>,
): Promise<boolean> {
  if (!state.acquirePublication(token)) return false;
  try {
    try {
      await enable();
    } catch (error) {
      const canceled = !state.isPending(token);
      state.cancel();
      // Cleanup failure is actionable even after cancellation. Never hide it.
      await disable();
      if (canceled) return false;
      throw error;
    }
    if (state.ready(token, now())) return true;
    await disable();
    return false;
  } finally {
    state.releasePublication();
  }
}
