import asyncio
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional

from backend.control_plane.lifecycle_orchestrator.lifecycle_orchestrator import (
    LifecycleContext,
    LifecycleState,
)


# ============================================================
# Job State
# ============================================================

class JobStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"


@dataclass
class ConfigJob:
    job_id: str
    session_id: str
    new_config: dict
    status: JobStatus = JobStatus.PENDING
    current_state: LifecycleState = LifecycleState.VALIDATING
    error: Optional[str] = None
    audit_log: list = field(default_factory=list)


# ============================================================
# Config Job Engine (In-Memory)
# ============================================================

class ConfigJobEngine:
    """
    Async job engine (in-memory).
    One job per session.
    """

    def __init__(self, lifecycle):
        self.lifecycle = lifecycle
        self.jobs: Dict[str, ConfigJob] = {}
        self.session_locks: Dict[str, asyncio.Lock] = {}

    # --------------------------------------------------------
    # Create Job
    # --------------------------------------------------------

    async def create_job(self, session_id: str, new_config: dict) -> str:
        if session_id in self.session_locks:
            raise RuntimeError("Another config job is running for this session")

        job_id = str(uuid.uuid4())
        job = ConfigJob(
            job_id=job_id,
            session_id=session_id,
            new_config=new_config,
        )

        self.jobs[job_id] = job
        self.session_locks[session_id] = asyncio.Lock()

        asyncio.create_task(self._run_job(job))
        return job_id

    # --------------------------------------------------------
    # Run Job
    # --------------------------------------------------------

    async def _run_job(self, job: ConfigJob):
        lock = self.session_locks[job.session_id]

        async with lock:
            job.status = JobStatus.RUNNING

            ctx = LifecycleContext(
                session_id=job.session_id,
                new_config=job.new_config,
                current_state=job.current_state,
            )

            while ctx.current_state not in (
                LifecycleState.DONE,
                LifecycleState.FAILED,
            ):
                ctx = self.lifecycle.step(ctx)
                job.current_state = ctx.current_state
                job.audit_log.append(ctx.current_state)

                # yield control (async friendly)
                await asyncio.sleep(0)

            if ctx.current_state == LifecycleState.DONE:
                job.status = JobStatus.DONE
            else:
                job.status = JobStatus.FAILED
                job.error = ctx.error

        # cleanup lock
        self.session_locks.pop(job.session_id, None)

    # --------------------------------------------------------
    # Query Job
    # --------------------------------------------------------

    def get_job(self, job_id: str) -> Optional[ConfigJob]:
        return self.jobs.get(job_id)
