// src/replay/replayRunner.ts
import { ReplayEngine } from "./replayEngine";
import { StateMessage, SystemState } from "../reducer";

export function runReplay(messages: StateMessage[]): SystemState | null {
  if (messages.length === 0) return null;

  const engine = new ReplayEngine();
  engine.load(messages);

  const frames = engine.build();

  if (frames.length === 0) return null;

  // trả về state cuối cùng sau replay
  return frames[frames.length - 1].state;
}
