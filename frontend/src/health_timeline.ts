import { ReplayReader } from "./replay_reader";
import { evaluateHealth, HealthLevel } from "./health_evaluator";
import { SystemState } from "./reducer";

export type HealthPoint = {
  index: number;
  level: HealthLevel;
};

export function buildHealthTimeline(
  reader: ReplayReader
): HealthPoint[] {
  const points: HealthPoint[] = [];

  reader.reset();

  while (true) {
    const before = reader.getProgress().cursor;
    const state = reader.step();
    const after = reader.getProgress().cursor;

    if (before === after || !state) break;

    const health = evaluateHealth(state as SystemState);
    points.push({
      index: after,
      level: health.level,
    });
  }

  reader.reset();
  return points;
}
