"""SQL aggregations for :func:`fetch_dashboard_summary`."""

from __future__ import annotations

import logging
from uuid import UUID

from psycopg.rows import dict_row

from app.db.database import get_db_connection
from app.schemas.admin_dashboard import (
    DashboardActivity24h,
    DashboardChunksSummary,
    DashboardDataSourcesSummary,
    DashboardFilesSummary,
    DashboardPipelinesSummary,
    DashboardProblemItems,
    DashboardSummaryBlock,
    DashboardSummaryResponse,
    DashboardUsersSummary,
    RecentActionItem,
    RecentPipelineJobItem,
    RecentScanJobItem,
)
from app.services.admin_jobs_service import batch_fetch_admin_children_rows_by_parent_ids
from app.services.pipeline_progress import compute_pipeline_summary_dict, pipeline_steps_from_job_params
from app.utils.file_type import humanize_bytes

logger = logging.getLogger(__name__)


class DashboardSummaryError(Exception):
    """Raised when a required dashboard aggregation cannot be completed."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


_SQL_USERS = """
    SELECT
        COUNT(*)::int AS total,
        COUNT(*) FILTER (WHERE status::text = 'PENDING')::int AS pending,
        COUNT(*) FILTER (WHERE status::text = 'ACTIVE')::int AS active,
        COUNT(*) FILTER (WHERE status::text = 'INACTIVE')::int AS inactive,
        COUNT(*) FILTER (WHERE status::text = 'LOCKED')::int AS locked,
        COUNT(*) FILTER (WHERE role::text = 'ADMIN')::int AS admins
    FROM app_users
"""

_SQL_DATA_SOURCES = """
    SELECT
        COUNT(*)::int AS total,
        COUNT(*) FILTER (WHERE is_active IS TRUE)::int AS active,
        COUNT(*) FILTER (WHERE is_active IS NOT TRUE)::int AS inactive,
        COUNT(*) FILTER (WHERE last_connection_success IS TRUE)::int AS connection_success,
        COUNT(*) FILTER (WHERE last_connection_success IS FALSE)::int AS connection_failed,
        COUNT(*) FILTER (WHERE last_connection_success IS NULL)::int AS never_tested
    FROM data_sources
"""

_SQL_FILES = """
    SELECT
        COUNT(*)::bigint AS total_items,
        COUNT(*) FILTER (WHERE NOT is_directory)::bigint AS total_files,
        COUNT(*) FILTER (WHERE is_directory)::bigint AS total_directories,
        COALESCE(SUM(size_bytes) FILTER (WHERE NOT is_directory), 0)::bigint AS total_size_bytes,
        COUNT(*) FILTER (WHERE analysis_status::text = 'PENDING')::int AS pending,
        COUNT(*) FILTER (WHERE analysis_status::text = 'COMPLETED')::int AS completed,
        COUNT(*) FILTER (WHERE analysis_status::text = 'FAILED')::int AS failed,
        COUNT(*) FILTER (WHERE analysis_status::text = 'SKIPPED')::int AS skipped,
        COUNT(*) FILTER (WHERE analysis_status::text = 'DELETED')::int AS deleted
    FROM files
"""

_SQL_CHUNKS = """
    SELECT
        COUNT(*)::bigint AS total_chunks,
        COUNT(*) FILTER (WHERE embedding IS NOT NULL)::bigint AS embedded_chunks,
        COUNT(*) FILTER (WHERE embedding IS NULL)::bigint AS pending_embedding_chunks
    FROM document_chunks
"""

_SQL_ACTIVITY_24H = """
    SELECT
        COUNT(*) FILTER (WHERE action_type = 'SEARCH')::int AS search_count_24h,
        COUNT(*) FILTER (WHERE action_type = 'RAG_QUESTION')::int AS rag_count_24h,
        COUNT(*) FILTER (WHERE action_type = 'LOGIN')::int AS login_count_24h,
        COUNT(*) FILTER (WHERE result = 'FAIL'::action_result)::int AS failed_action_count_24h
    FROM action_logs
    WHERE created_at >= NOW() - INTERVAL '24 hours'
"""

_SQL_RECENT_ACTIONS = """
    SELECT
        al.id,
        COALESCE(NULLIF(TRIM(u.name), ''), u.login_id, '—') AS user_name,
        al.action_type,
        al.result::text AS result,
        al.search_query,
        al.created_at
    FROM action_logs al
    LEFT JOIN app_users u ON u.id = al.user_id
    ORDER BY al.created_at DESC
    LIMIT 10
"""

_SQL_RECENT_SCAN_JOBS = """
    SELECT
        sj.id,
        sj.data_source_id,
        ds.name AS data_source_name,
        sj.job_type::text AS job_type,
        sj.status::text AS status,
        COALESCE(sj.total_files, 0)::int AS total_files,
        COALESCE(sj.processed_files, 0)::int AS processed_files,
        COALESCE(sj.completed_files, 0)::int AS completed_files,
        COALESCE(sj.failed_files, 0)::int AS failed_files,
        COALESCE(sj.skipped_files, 0)::int AS skipped_files,
        COALESCE(sj.deleted_files, 0)::int AS deleted_files,
        sj.started_at,
        sj.finished_at
    FROM scan_jobs sj
    LEFT JOIN data_sources ds ON ds.id = sj.data_source_id
    ORDER BY sj.started_at DESC NULLS LAST, sj.created_at DESC
    LIMIT 5
"""

_SQL_PIPELINES_COUNTS = """
    SELECT
        COUNT(*) FILTER (WHERE status::text IN ('RUNNING', 'CANCELLING'))::int AS running,
        COUNT(*) FILTER (WHERE status::text = 'PENDING')::int AS pending,
        COUNT(*) FILTER (
            WHERE status::text = 'FAILED'
              AND COALESCE(finished_at, updated_at) >= NOW() - INTERVAL '24 hours'
        )::int AS failed_24h,
        COUNT(*) FILTER (
            WHERE status::text IN ('COMPLETED', 'PARTIAL')
              AND COALESCE(finished_at, updated_at) >= NOW() - INTERVAL '24 hours'
        )::int AS completed_24h
    FROM scan_jobs
    WHERE job_type::text = 'PIPELINE'
"""

_SQL_RECENT_PIPELINES = """
    SELECT
        sj.id,
        ds.name AS data_source_name,
        sj.status::text AS status,
        sj.job_params,
        sj.started_at
    FROM scan_jobs sj
    LEFT JOIN data_sources ds ON ds.id = sj.data_source_id
    WHERE sj.job_type::text = 'PIPELINE'
    ORDER BY sj.started_at DESC NULLS LAST, sj.created_at DESC NULLS LAST
    LIMIT 8
"""


def _fetch_recent_scan_jobs(cur) -> list[RecentScanJobItem]:
    try:
        cur.execute(_SQL_RECENT_SCAN_JOBS)
        rows = cur.fetchall() or []
    except Exception as exc:
        logger.warning("dashboard: scan_jobs unavailable (%s)", exc)
        return []
    return [RecentScanJobItem.model_validate(dict(r)) for r in rows]


def fetch_dashboard_summary() -> DashboardSummaryResponse:
    """Run dashboard SQL inside one DB connection."""
    try:
        with get_db_connection() as conn:
            conn.row_factory = dict_row
            with conn.cursor() as cur:
                cur.execute(_SQL_USERS)
                urow = cur.fetchone() or {}
                users = DashboardUsersSummary.model_validate(dict(urow))

                cur.execute(_SQL_DATA_SOURCES)
                drow = cur.fetchone() or {}
                data_sources = DashboardDataSourcesSummary.model_validate(dict(drow))

                cur.execute(_SQL_FILES)
                frow = cur.fetchone() or {}
                fd = dict(frow)
                tsb = int(fd.get("total_size_bytes") or 0)
                fd["total_size_human"] = humanize_bytes(tsb)
                files = DashboardFilesSummary.model_validate(fd)

                cur.execute(_SQL_CHUNKS)
                crow = cur.fetchone() or {}
                chunks = DashboardChunksSummary.model_validate(dict(crow))

                cur.execute(_SQL_ACTIVITY_24H)
                arow = cur.fetchone() or {}
                activity = DashboardActivity24h.model_validate(dict(arow))

                cur.execute(_SQL_RECENT_ACTIONS)
                action_rows = cur.fetchall() or []
                recent_actions = [
                    RecentActionItem.model_validate(dict(r)) for r in action_rows
                ]

                recent_scan_jobs = _fetch_recent_scan_jobs(cur)

                pipelines = DashboardPipelinesSummary()
                recent_pipeline_jobs: list[RecentPipelineJobItem] = []
                try:
                    cur.execute(_SQL_PIPELINES_COUNTS)
                    pc = cur.fetchone() or {}
                    pipelines = DashboardPipelinesSummary.model_validate(dict(pc))
                except Exception as exc:
                    logger.warning("dashboard: pipeline counts unavailable (%s)", exc)

                try:
                    cur.execute(_SQL_RECENT_PIPELINES)
                    prow_list = cur.fetchall() or []
                    pids = [r["id"] for r in prow_list]
                    id_list = [x if isinstance(x, UUID) else UUID(str(x)) for x in pids]
                    cmap = batch_fetch_admin_children_rows_by_parent_ids(id_list)
                    for r in prow_list:
                        rid = r["id"]
                        ru = rid if isinstance(rid, UUID) else UUID(str(rid))
                        steps = pipeline_steps_from_job_params(r.get("job_params"))
                        pct = 0.0
                        cur_step: str | None = None
                        if steps:
                            kids = cmap.get(ru) or []
                            sd = compute_pipeline_summary_dict(steps=steps, children_rows=[dict(x) for x in kids])
                            pct = float(sd.get("progress_percent") or 0.0)
                            cur_step = sd.get("current_step")
                        recent_pipeline_jobs.append(
                            RecentPipelineJobItem(
                                id=ru,
                                data_source_name=r.get("data_source_name"),
                                status=str(r.get("status") or ""),
                                progress_percent=pct,
                                current_step=cur_step,
                                started_at=r.get("started_at"),
                            )
                        )
                except Exception as exc:
                    logger.warning("dashboard: recent pipelines unavailable (%s)", exc)

        problem = DashboardProblemItems(
            failed_files_count=files.failed,
            pending_files_count=files.pending,
            pending_embedding_chunks_count=chunks.pending_embedding_chunks,
            inactive_data_sources_count=data_sources.inactive,
            pending_users_count=users.pending,
        )

        block = DashboardSummaryBlock(
            users=users,
            data_sources=data_sources,
            files=files,
            chunks=chunks,
            activity=activity,
        )
        return DashboardSummaryResponse(
            summary=block,
            recent_scan_jobs=recent_scan_jobs,
            recent_actions=recent_actions,
            problem_items=problem,
            pipelines=pipelines,
            recent_pipeline_jobs=recent_pipeline_jobs,
        )
    except Exception as exc:
        raise DashboardSummaryError(str(exc)) from exc
