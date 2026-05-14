"""DB-polling worker package (skeleton).

Avoid importing ``db_worker`` at package import time so ``scan_jobs_service`` can
import :class:`app.workers.worker_types.WorkerJob` without circular imports.
"""

from app.workers.worker_types import WorkerJob, WorkerRunResult

__all__ = ["WorkerJob", "WorkerRunResult"]


def __getattr__(name: str):
    if name == "DBPollingWorker":
        from app.workers.db_worker import DBPollingWorker

        return DBPollingWorker
    if name == "run_job":
        from app.workers.job_runner import run_job

        return run_job
    raise AttributeError(name)
