// Connection recovery never replays messages or tool requests.
export class CompanionLifecycle {
  constructor(paused = false) {
    this.paused = paused;
  }
  paused: boolean;
  sleeping = false;
  online = true;
  terminal = false;
  attempts = 0;
  connecting = false;
  delay(): number | null {
    if (
      this.paused ||
      this.sleeping ||
      !this.online ||
      this.terminal ||
      this.connecting ||
      this.attempts >= 8
    )
      return null;
    return Math.min(2000 * 2 ** this.attempts++, 60000);
  }
  resume() {
    this.paused = false;
    this.sleeping = false;
    this.online = true;
    this.terminal = false;
    this.attempts = 0;
  }
  connected() {
    this.attempts = 0;
  }
}
export function terminalConnectionError(error: unknown) {
  return /quota|billing|API key|unauthori[sz]ed|forbidden|access code|microphone|NotAllowed|NotFound/i.test(
    String(error),
  );
}
