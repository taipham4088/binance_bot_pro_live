// replay_reader.ts
import { reduce, SystemState, StateMessage } from "./reducer";

export class ReplayReader {
  private state: SystemState | null = null;
  private messages: StateMessage[] = [];
  private cursor = 0;

  cconstructor(ndjsonText?: string) {
    if (ndjsonText) {
      this.messages = this.parseNDJSON(ndjsonText);
    } else {
      this.messages = []; // live / empty mode
    }
  }

  private parseNDJSON(text: string): StateMessage[] {
    return text
      .split("\n")
      .map(line => line.trim())
      .filter(line => line.length > 0)
      .map(line => JSON.parse(line));
  }

  /** Step từng message */
  step(): SystemState | null {
    if (this.cursor >= this.messages.length) {
      return this.state;
    }

    const msg = this.messages[this.cursor];
    this.state = reduce(this.state, msg);
    this.cursor += 1;

    return this.state;
  }

  /** Replay full */
  replayAll(): SystemState | null {
    while (this.cursor < this.messages.length) {
      this.step();
    }
    return this.state;
  }

  /** Reset để replay lại */
  reset() {
    this.state = null;
    this.cursor = 0;
  }

  /** Current state */
  getState(): SystemState | null {
    return this.state;
  }

  /** Progress */
  getProgress() {
    return {
      cursor: this.cursor,
      total: this.messages.length
    };
  }
}
