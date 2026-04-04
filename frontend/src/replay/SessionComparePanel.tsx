import React from "react";
import { Divergence } from "./session_compare";

type Props = {
  divergence: Divergence | null;
};

export const SessionComparePanel: React.FC<Props> = ({ divergence }) => {
  if (!divergence) {
    return (
      <div style={{ padding: 8, color: "green" }}>
        ✅ LIVE = REPLAY (no divergence)
      </div>
    );
  }

  return (
    <div style={{ padding: 8, border: "1px solid #e0e0e0" }}>
      <h4 style={{ color: "#c62828", marginBottom: 8 }}>
        ⚠️ Divergence detected
      </h4>

      <div><b>Path:</b> {divergence.path}</div>

      <div style={{ marginTop: 6 }}>
        <b>LIVE</b>
        <pre style={{ background: "#f8f8f8", padding: 6 }}>
          {JSON.stringify(divergence.live, null, 2)}
        </pre>
      </div>

      <div>
        <b>REPLAY</b>
        <pre style={{ background: "#f8f8f8", padding: 6 }}>
          {JSON.stringify(divergence.replay, null, 2)}
        </pre>
      </div>
    </div>
  );
};
