"""Single-process DB polling worker (skeleton).

``run_once`` claims PENDING rows, runs :func:`job_runner.run_job`, then marks
terminal state. Long-running handlers should refresh ``heartbeat_at`` in-loop
via ``scan_jobs_service.update_job_heartbeat`` / ``update_scan_job_progress``
once real work is wired in.
"""

from __future__ import annotations

import logging
import time

from app.core.config import Settings
from app.services import scan_jobs_service
from app.workers import job_runner

logger = logging.getLogger(__name__)


class DBPollingWorker:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self.worker_id = (settings.worker_id or "local-worker-1").strip()[:100]
        self.poll_interval_seconds = max(0.5, float(settings.worker_poll_interval_seconds))
        self.heartbeat_interval_seconds = max(1.0, float(settings.worker_heartbeat_interval_seconds))
        self.max_jobs_per_loop = max(1, int(settings.worker_max_jobs_per_loop))
        self.stale_timeout_minutes = max(1, int(settings.worker_stale_timeout_minutes))
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run_once(self) -> int:
        """Process up to ``max_jobs_per_loop`` jobs; returns number processed."""
        processed = 0
        for _ in range(self.max_jobs_per_loop):
            if self._stop:
                break
            job = scan_jobs_service.dequeue_pending_job(worker_id=self.worker_id)
            if job is None:
                break

            if scan_jobs_service.is_cancel_requested(job.id):
                scan_jobs_service.mark_job_cancelled(job.id, message="Job cancelled")
                processed += 1
                continue

            scan_jobs_service.update_job_heartbeat(job.id, self.worker_id)

            # Handlers that finalize scan_jobs (e.g. WEBDAV_SYNC_TREE core) set
            # ``WorkerRunResult.finalized_by_handler``; finer in-loop heartbeats for
            # very large trees are a future improvement (see README).

            try:
                result = job_runner.run_job(job)
            except Exception as exc:  # pragma: no cover - defensive
                logger.exception("run_job crashed job_id=%s", job.id)
                scan_jobs_service.mark_job_failed(
                    job.id,
                    error_message=f"Worker exception: {type(exc).__name__}",
                )
                processed += 1
                continue

            scan_jobs_service.update_job_heartbeat(job.id, self.worker_id)

            if result.finalized_by_handler:
                processed += 1
                continue

            if result.success:
                scan_jobs_service.mark_job_completed(job.id, message=result.message)
            else:
                scan_jobs_service.mark_job_failed(job.id, error_message=result.message)

            processed += 1

        return processed

    def run_forever(self) -> None:
        logger.info(
            "DBPollingWorker started worker_id=%s poll=%ss max_per_loop=%s stale_timeout_min=%s (skeleton)",
            self.worker_id,
            self.poll_interval_seconds,
            self.max_jobs_per_loop,
            self.stale_timeout_minutes,
        )
        try:
            while not self._stop:
                n = self.run_once()
                if n == 0:
                    time.sleep(self.poll_interval_seconds)
        except KeyboardInterrupt:
            logger.info("DBPollingWorker interrupted, shutting down")
            self._stop = True


__all__ = ["DBPollingWorker"]
