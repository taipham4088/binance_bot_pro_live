from typing import Dict, Optional
import time

from backend.core.control.config_job import (
    ConfigJob,
    ConfigDiff,
    AuditMeta,
)
from backend.core.control.config_job_runner import ConfigJobRunner


# =========================
# In-memory Job Registry
# (Stub – replace by DB later)
# =========================

_CONFIG_JOBS: Dict[str, ConfigJob] = {}


# =========================
# Control Plane API (Stub)
# =========================

class ControlPlaneAPI:
    """
    STEP 12.4 – ControlPlaneAPI (STUB)

    Responsibilities:
    - Accept config change requests
    - Create ConfigJob
    - Trigger ConfigJobRunner
    - Expose job status
    - NO execution authority
    - NO websocket execution
    """

    def __init__(self, job_runner: ConfigJobRunner):
        self.job_runner = job_runner

    # -------------------------
    # Submit Config Job
    # -------------------------

    def submit_config_job(
        self,
        session_id: str,
        requested_by: str,
        config_diff: ConfigDiff,
        reason: Optional[str] = None,
    ) -> str:
        """
        Create and run a config job.
        Returns job_id.
        """

        audit = AuditMeta(
            requested_by=requested_by,
            requested_at=time.time(),
            reason=reason,
        )

        job = ConfigJob(
            session_id=session_id,
            config_diff=config_diff,
            audit=audit,
        )

        _CONFIG_JOBS[job.job_id] = job

        # NOTE:
        # Runner is synchronous by design.
        # Async execution will be added at outer layer.
        self.job_runner.run(job)

        return job.job_id

    # -------------------------
    # Query Job Status
    # -------------------------

    def get_job(self, job_id: str) -> Optional[dict]:
        job = _CONFIG_JOBS.get(job_id)
        if not job:
            return None
        return job.snapshot()

    def list_jobs(self, session_id: Optional[str] = None) -> Dict[str, dict]:
        """
        List jobs, optionally filtered by session_id.
        """
        result: Dict[str, dict] = {}

        for job_id, job in _CONFIG_JOBS.items():
            if session_id and job.session_id != session_id:
                continue
            result[job_id] = job.snapshot()

        return result
