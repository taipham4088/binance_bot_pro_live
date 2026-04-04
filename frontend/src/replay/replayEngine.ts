// src/replay/replayEngine.ts
import { reduce, SystemState, StateMessage } from "../reducer";

export interface ReplayFrame {
  index: number;
  message: StateMessage;
  state: SystemState;
}

export class ReplayEngine {
  private messages: StateMessage[] = [];
  private frames: ReplayFrame[] = [];

  load(messages: StateMessage[]) {
    this.messages = messages;
    this.frames = [];
  }

  build(): ReplayFrame[] {
    let currentState: SystemState | null = null;

    this.frames = [];

    for (let i = 0; i < this.messages.length; i++) {
      const msg = this.messages[i];

      if (msg.type === "SNAPSHOT") {
        currentState = reduce(null, msg); // reset khi snapshot
      } else {
        if (!currentState) continue; // DELTA trước SNAPSHOT → bỏ
        currentState = reduce(currentState, msg);
      }

      // ⬇️ CHỈ PUSH KHI currentState ĐÃ TỒN TẠI
      if (!currentState) continue;

      this.frames.push({
        index: i,
        message: msg,
        state: currentState,
      });

    }


    return this.frames;
  }

  getFrame(index: number): ReplayFrame | null {
    return this.frames[index] ?? null;
  }

  size(): number {
    return this.frames.length;
  }
}
