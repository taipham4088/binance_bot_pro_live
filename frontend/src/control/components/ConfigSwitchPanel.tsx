import { useState } from "react"
import { Session } from "../../types/session"
import { switchConfig } from "../api/configApi"

type Props = {
  session: Session
  onJobCreated: (jobId: string) => void
}

export default function ConfigSwitchPanel({ session, onJobCreated }: Props) {
  const [engineProfile, setEngineProfile] = useState(session.config.engine_profile)
  const [positionMode, setPositionMode] = useState(session.config.position_mode)

  const canApply =
    engineProfile !== session.config.engine_profile ||
    positionMode !== session.config.position_mode

  const apply = async () => {
    const res = await switchConfig({
      session_id: session.id,
      engine: "dual_engine",
      engine_profile: engineProfile,
      position_mode: positionMode
    })

    onJobCreated(res.job_id)
  }

  return (
    <div>
      <h4>Config Switch</h4>

      <select value={engineProfile} onChange={(e) => setEngineProfile(e.target.value as any)}>
        <option value="range_trend">Range / Trend</option>
        <option value="momentum">Momentum</option>
      </select>

      <select value={positionMode} onChange={(e) => setPositionMode(e.target.value as any)}>
        <option value="long_only">Long Only</option>
        <option value="short_only">Short Only</option>
        <option value="dual">Dual</option>
      </select>

      <button disabled={!canApply} onClick={apply}>
        Apply Config
      </button>
    </div>
  )
}
