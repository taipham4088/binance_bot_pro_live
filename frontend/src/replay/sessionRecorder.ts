// src/replay/sessionRecorder.ts
import { StateMessage } from "../reducer";

export class SessionRecorder {
  private messages: StateMessage[] = [];

  reset() {
    this.messages = [];
  }

  record(message: StateMessage) {
    this.messages.push(message);
  }

  getAll(): StateMessage[] {
    return [...this.messages];
  }

  size(): number {
    return this.messages.length;
  }
}
