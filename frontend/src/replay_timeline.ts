// replay_timeline.ts
import { ReplayReader } from "./replay_reader";
import { SystemState } from "./reducer";

type TimelineListener = (state: SystemState | null, progress: Progress) => void;

type Progress = {
  cursor: number;
  total: number;
};

export class ReplayTimeline {
  private timer: any = null;
  private listeners: Set<TimelineListener> = new Set();

  constructor(private reader: ReplayReader) {}

  subscribe(cb: TimelineListener): () => void {
    this.listeners.add(cb);
    cb(this.reader.getState(), this.reader.getProgress());
    return () => this.listeners.delete(cb);
  }

  private emit() {
    const state = this.reader.getState();
    const progress = this.reader.getProgress();
    this.listeners.forEach((cb) => cb(state, progress));
  }

  step() {
    this.reader.step();
    this.emit();
  }

  play(intervalMs: number = 300) {
    if (this.timer) return;

    this.timer = setInterval(() => {
      const before = this.reader.getProgress().cursor;
      this.reader.step();
      const after = this.reader.getProgress().cursor;

      this.emit();

      if (before === after) {
        this.pause(); // end of replay
      }
    }, intervalMs);
  }

  pause() {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
  }

  reset() {
    this.pause();
    this.reader.reset();
    this.emit();
  }
}
