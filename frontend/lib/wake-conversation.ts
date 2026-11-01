// Monotonic, session-local wake ownership. No audio or transcript storage.
export class WakeConversation {
  active = false;
  pending = false;
  private lastActivity = 0;
  private generation = 0;
  constructor(public idleSeconds = 90) {}
  begin(now: number): number | null {
    if (this.pending || this.active) return null;
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
  if (!state.isPending(token)) return false;
  try {
    await enable();
    if (state.ready(token, now())) return true;
    await disable();
    return false;
  } catch (error) {
    state.cancel();
    await disable().catch(() => {});
    throw error;
  }
}
