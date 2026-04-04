import { useEffect, useState } from "react"

export default function JobStatusPanel({ jobId }: { jobId: string }) {
  const [job, setJob] = useState<any>(null)

  useEffect(() => {
    const t = setInterval(async () => {
      const res = await fetch(
        `http://127.0.0.1:8000/system/config/job/${jobId}`
      )
      setJob(await res.json())
    }, 1000)

    return () => clearInterval(t)
  }, [jobId])

  if (!job) return null

  return (
    <div>
      <h4>Job Status</h4>
      <div>Status: {job.status}</div>
      <ul>
        {job.audit_log?.map((s: string) => (
          <li key={s}>{s}</li>
        ))}
      </ul>
    </div>
  )
}
