"""Tests for explicit HWP SKIPPED/NO_EXTRACTABLE_TEXT reprocess targeting."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.schemas.admin_jobs import AdminProcessPendingDocumentsJobRequest
from app.services.file_contents_service import fetch_pending_document_files
from app.services.pending_document_processor_service import (
    _planned_action_for_row,
    run_process_pending_documents,
)


def test_planned_action_pending() -> None:
    action, reason = _planned_action_for_row(
        {"analysis_status": "PENDING", "extension": "hwp"}
    )
    assert action == "PROCESS_PENDING"
    assert reason is None


def test_planned_action_reprocess_supported() -> None:
    action, reason = _planned_action_for_row(
        {
            "analysis_status": "SKIPPED",
            "analysis_error_code": "UNSUPPORTED_EXTENSION",
            "extension": "pdf",
        }
    )
    assert action == "REPROCESS_SUPPORTED_EXTENSION"
    assert reason == "UNSUPPORTED_EXTENSION"


def test_planned_action_reprocess_hwp_no_text() -> None:
    action, reason = _planned_action_for_row(
        {
            "analysis_status": "SKIPPED",
            "analysis_error_code": "NO_EXTRACTABLE_TEXT",
            "extension": "hwp",
        }
    )
    assert action == "REPROCESS_HWP_NO_EXTRACTABLE_TEXT"
    assert reason == "NO_EXTRACTABLE_TEXT"


def test_planned_action_pdf_no_text_not_hwp_reprocess() -> None:
    action, reason = _planned_action_for_row(
        {
            "analysis_status": "SKIPPED",
            "analysis_error_code": "NO_EXTRACTABLE_TEXT",
            "extension": "pdf",
        }
    )
    assert action == "SKIP"
    assert reason == "NO_EXTRACTABLE_TEXT"


def _wire_mock_db(mock_get_conn: MagicMock) -> MagicMock:
    cur = MagicMock()
    cur.fetchall.return_value = []
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    mock_get_conn.return_value.__enter__.return_value = conn
    return cur


@patch("app.services.file_contents_service.get_db_connection")
def test_fetch_sql_params_hwp_flag_false(mock_get_conn: MagicMock) -> None:
    ds_id = uuid4()
    cur = _wire_mock_db(mock_get_conn)

    fetch_pending_document_files(
        ds_id=ds_id,
        limit=10,
        document_extensions=frozenset({"hwp", "pdf"}),
        reprocess_skipped=False,
        reprocess_hwp_no_extractable_text=False,
    )

    assert cur.execute.called
    sql, params = cur.execute.call_args[0]
    assert "NO_EXTRACTABLE_TEXT" in sql
    assert params[1] == ["hwp", "pdf"]
    assert params[2] is False
    assert params[3] is False
    assert params[4] == 10


@patch("app.services.file_contents_service.get_db_connection")
def test_fetch_sql_params_hwp_flag_true(mock_get_conn: MagicMock) -> None:
    ds_id = uuid4()
    cur = _wire_mock_db(mock_get_conn)

    fetch_pending_document_files(
        ds_id=ds_id,
        limit=5,
        document_extensions=frozenset({"hwp"}),
        reprocess_skipped=False,
        reprocess_hwp_no_extractable_text=True,
    )

    sql, params = cur.execute.call_args[0]
    assert "NO_EXTRACTABLE_TEXT" in sql
    assert params[3] is True


def test_admin_job_request_stores_hwp_reprocess_flag() -> None:
    body = AdminProcessPendingDocumentsJobRequest(
        data_source_id=uuid4(),
        reprocess_hwp_no_extractable_text=True,
    )
    assert body.reprocess_hwp_no_extractable_text is True


@patch("app.services.pending_document_processor_service.run_process_pending_documents_core")
@patch("app.services.pending_document_processor_service.scan_jobs_service.create_scan_job")
@patch("app.services.pending_document_processor_service.fetch_pending_document_files")
@patch("app.services.pending_document_processor_service._pending_document_webdav_context")
def test_dry_run_does_not_call_core(
    mock_ctx: MagicMock,
    mock_fetch: MagicMock,
    mock_create_job: MagicMock,
    mock_core: MagicMock,
) -> None:
    ds_id = uuid4()
    mock_ctx.return_value = (
        {
            "ds_name": "ds",
            "server_url": "http://x",
            "webdav_root": "/",
            "uname": "u",
            "password": "p",
        },
        None,
    )
    mock_fetch.return_value = [
        {
            "id": uuid4(),
            "remote_path": "/a.hwp",
            "filename": "a.hwp",
            "extension": "hwp",
            "size_bytes": 100,
            "content_hash": None,
            "analysis_status": "SKIPPED",
            "analysis_error_code": "NO_EXTRACTABLE_TEXT",
        }
    ]

    from app.core.config import Settings

    payload, code = run_process_pending_documents(
        Settings(),
        ds_id,
        limit=10,
        max_file_size_bytes=52_428_800,
        include_extensions=frozenset({"hwp"}),
        dry_run=True,
        reprocess_skipped=False,
        reprocess_hwp_no_extractable_text=True,
    )

    assert code == 200
    assert payload.get("dry_run") is True
    mock_core.assert_not_called()
    mock_create_job.assert_not_called()
    items = payload.get("items") or []
    assert items and items[0].get("planned_action") == "REPROCESS_HWP_NO_EXTRACTABLE_TEXT"


@patch("app.workers.job_runner.run_process_pending_documents_core")
@patch("app.workers.job_runner.scan_jobs_service")
def test_worker_passes_hwp_reprocess_flag(
    mock_scan: MagicMock,
    mock_core: MagicMock,
) -> None:
    from app.services.pending_document_processor_service import (
        ProcessPendingDocumentsCoreResult,
    )
    from app.services import scan_jobs_service
    from app.workers.job_runner import run_job
    from app.workers.worker_types import WorkerJob

    job = WorkerJob(
        id=uuid4(),
        data_source_id=uuid4(),
        job_type=scan_jobs_service.JOB_TYPE_PROCESS_PENDING_DOCUMENTS,
        job_params={
            "limit": 1,
            "max_file_size_bytes": 52_428_800,
            "include_extensions": "hwp",
            "reprocess_hwp_no_extractable_text": True,
        },
        requested_by=None,
        priority=0,
        pipeline_step=None,
        parent_job_id=None,
        max_retries=1,
        retry_count=0,
        cancel_requested=False,
    )
    mock_core.return_value = ProcessPendingDocumentsCoreResult(
        payload={"status": "ok", "message": "ok"},
        http_status=200,
        finalized_scan_job=True,
    )
    mock_scan.is_cancel_requested.return_value = False

    run_job(job)

    assert mock_core.called
    kwargs = mock_core.call_args.kwargs
    assert kwargs.get("reprocess_hwp_no_extractable_text") is True
