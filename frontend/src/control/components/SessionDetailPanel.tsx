import { useState } from "react";
import { Session } from "../../types/session"
import ConfigSwitchPanel from "./ConfigSwitchPanel";
import JobStatusPanel from "./JobStatusPanel";

type Props = {
  session: Session;
  onSessionUpdate: (s: Session) => void;
};

export default function SessionDetailPanel({ session }: Props) {
  const [jobId, setJobId] = useState<string | null>(null);
  if (!session) {
    return (
      <div style={{ padding: 16, flex: 1 }}>
        <h2>No session selected</h2>
      </div>
    );
  }

  return (
    <div style={{ padding: 16, flex: 1 }}>
      <h2>{session.mode.toUpperCase()} SESSION</h2>

      <pre>{JSON.stringify(session.config, null, 2)}</pre>

      <ConfigSwitchPanel session={session} onJobCreated={setJobId} />

      {jobId && <JobStatusPanel jobId={jobId} />}
    </div>
  );
}
