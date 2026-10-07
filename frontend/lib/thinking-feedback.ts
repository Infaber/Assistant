/** Scheduling is separate from playback so a cue cannot survive a turn change. */
export class ThinkingFeedback {
  private first?: ReturnType<typeof setTimeout>;
  private second?: ReturnType<typeof setTimeout>;
  private last = -Infinity;
  private count = 0;
  private generation = 0;
  constructor(
    private play: (name: string, active: () => boolean) => Promise<void>,
    private stop: () => void,
  ) {}
  update(active: boolean) {
    this.cancel();
    if (!active) return;
    const generation = this.generation;
    const isActive = () => this.generation === generation;
    const cue = (name: string) => {
      if (!isActive() || Date.now() - this.last < 12_000) return;
      this.last = Date.now();
      void this.play(name, isActive).catch(() => {});
    };
    this.first = setTimeout(
      () => cue(this.count++ % 2 ? "moment" : "thinking"),
      1800,
    );
    this.second = setTimeout(() => cue("still-here"), 15_000);
  }
  cancel() {
    this.generation++;
    clearTimeout(this.first);
    clearTimeout(this.second);
    this.stop();
  }
}
