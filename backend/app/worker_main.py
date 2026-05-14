"""Standalone DB polling worker entrypoint (skeleton).

Run from the ``backend`` directory::

    python -m app.worker_main

This process does **not** start when the FastAPI app starts; keep
``WORKER_ENABLED=false`` for normal API-only runs. CLI execution starts the
worker regardless of ``WORKER_ENABLED`` (see log message).
"""

from __future__ import annotations

import logging
import sys

from app.core.config import settings
from app.workers.db_worker import DBPollingWorker

logger = logging.getLogger(__name__)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stderr,
    )

    if not settings.worker_enabled:
        logger.warning(
            "WORKER_ENABLED is false — starting worker anyway (CLI explicit run: "
            "Running worker from CLI)."
        )
    else:
        logger.info("Running worker from CLI (WORKER_ENABLED=true).")

    worker = DBPollingWorker(settings)
    worker.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
