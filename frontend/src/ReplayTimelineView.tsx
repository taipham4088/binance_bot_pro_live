import { useEffect, useState } from "react";
import { ReplayTimeline } from "./replay_timeline";
import { buildHealthTimeline } from "./health_timeline";
import { HealthTimelineOverlay } from "./HealthTimelineOverlay";

export function ReplayTimelineView({
  timeline,
}: {
  timeline: ReplayTimeline;
}) {
  const [state, setState] = useState<any>(null);
  const [progress, setProgress] = useState({ cursor: 0, total: 0 });
  const [healthPoints, setHealthPoints] = useState<any[]>([]);

  useEffect(() => {
    return timeline.subscribe((s, p) => {
      setState(s);
      setProgress(p);
    });
  }, [timeline]);

  useEffect(() => {
    // build once from replay reader
    const points = buildHealthTimeline(
      (timeline as any).reader
    );
    setHealthPoints(points);
  }, [timeline]);

  return (
    <div>
      {/* HEALTH OVERLAY */}
      <HealthTimelineOverlay
        points={healthPoints}
        current={progress.cursor}
      />

      {/* CONTROLS */}
      <button onClick={() => timeline.step()}>Step</button>
      <button onClick={() => timeline.play(300)}>Play</button>
      <button onClick={() => timeline.pause()}>Pause</button>
      <button onClick={() => timeline.reset()}>Reset</button>

      <div>
        {progress.cursor} / {progress.total}
      </div>
    </div>
  );
}
