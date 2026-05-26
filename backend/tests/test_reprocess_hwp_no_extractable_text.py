"""Tests for explicit HWP SKIPPED/NO_EXTRACTABLE_TEXT reprocess targeting."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.schemas.admin_jobs import AdminProcessPendingDocumentsJobRequest
from app.services.file_contents_service import fetch_pending_document_files
from app.services.pending_document_processor_service import (
    _planned_action_for_row,
    _resolve_documents_request_options,
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


def test_planned_action_only_mode() -> None:
    action, reason = _planned_action_for_row(
        {
            "analysis_status": "SKIPPED",
            "analysis_error_code": "NO_EXTRACTABLE_TEXT",
            "extension": "hwp",
        },
        only_reprocess_hwp_no_extractable_text=True,
    )
    assert action == "REPROCESS_HWP_NO_EXTRACTABLE_TEXT_ONLY"
    assert reason == "NO_EXTRACTABLE_TEXT"


def test_planned_action_only_mode_excludes_pending() -> None:
    action, _ = _planned_action_for_row(
        {"analysis_status": "PENDING", "extension": "hwp"},
        only_reprocess_hwp_no_extractable_text=True,
    )
    assert action == "SKIP"


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


@patch("app.services.file_contents_service.get_db_connection")
def test_fetch_only_mode_sql(mock_get_conn: MagicMock) -> None:
    ds_id = uuid4()
    cur = _wire_mock_db(mock_get_conn)

    fetch_pending_document_files(
        ds_id=ds_id,
        limit=1,
        document_extensions=frozenset({"hwp"}),
        reprocess_skipped=False,
        reprocess_hwp_no_extractable_text=True,
        only_reprocess_hwp_no_extractable_text=True,
    )

    sql, params = cur.execute.call_args[0]
    assert "analysis_status = 'PENDING'" not in sql
    assert params == [ds_id, 1]


def test_resolve_only_mode_defaults_hwp() -> None:
    eff, rs, rh, only, err = _resolve_documents_request_options(
        None,
        reprocess_skipped=True,
        reprocess_hwp_no_extractable_text=False,
        only_reprocess_hwp_no_extractable_text=True,
    )
    assert err is None
    assert only is True
    assert eff == frozenset({"hwp"})
    assert rs is False
    assert rh is True


def test_resolve_only_mode_requires_hwp_in_include() -> None:
    _, _, _, only, err = _resolve_documents_request_options(
        frozenset({"pdf"}),
        reprocess_skipped=False,
        reprocess_hwp_no_extractable_text=False,
        only_reprocess_hwp_no_extractable_text=True,
    )
    assert only is True
    assert err is not None
    assert "hwp" in err.get("message", "")


def test_admin_job_request_stores_hwp_reprocess_flag() -> None:
    body = AdminProcessPendingDocumentsJobRequest(
        data_source_id=uuid4(),
        reprocess_hwp_no_extractable_text=True,
    )
    assert body.reprocess_hwp_no_extractable_text is True


def test_admin_job_request_stores_only_flag() -> None:
    body = AdminProcessPendingDocumentsJobRequest(
        data_source_id=uuid4(),
        only_reprocess_hwp_no_extractable_text=True,
    )
    assert body.only_reprocess_hwp_no_extractable_text is True


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
@patch(
    "app.workers.job_runner.scan_jobs_service.is_cancel_requested",
    return_value=False,
)
def test_worker_passes_hwp_reprocess_flag(
    _mock_cancel: MagicMock,
    mock_core: MagicMock,
) -> None:
    from app.services.pending_document_processor_service import (
        ProcessPendingDocumentsCoreResult,
    )
    from app.workers.job_runner import run_job
    from app.workers.worker_types import WorkerJob

    job = WorkerJob(
        id=uuid4(),
        data_source_id=uuid4(),
        job_type="PROCESS_PENDING_DOCUMENTS",
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

    run_job(job)

    assert mock_core.called
    kwargs = mock_core.call_args.kwargs
    assert kwargs.get("reprocess_hwp_no_extractable_text") is True


@patch("app.services.pending_document_processor_service.run_process_pending_documents_core")
@patch("app.services.pending_document_processor_service.scan_jobs_service.create_scan_job")
@patch("app.services.pending_document_processor_service.fetch_pending_document_files")
@patch("app.services.pending_document_processor_service._pending_document_webdav_context")
def test_only_mode_dry_run_planned_action_only(
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
            "remote_path": "/skip.hwp",
            "filename": "skip.hwp",
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
        limit=1,
        max_file_size_bytes=52_428_800,
        include_extensions=None,
        dry_run=True,
        reprocess_skipped=True,
        reprocess_hwp_no_extractable_text=False,
        only_reprocess_hwp_no_extractable_text=True,
    )

    assert code == 200
    mock_core.assert_not_called()
    items = payload.get("items") or []
    assert items[0].get("planned_action") == "REPROCESS_HWP_NO_EXTRACTABLE_TEXT_ONLY"
    assert items[0].get("analysis_status_before") == "SKIPPED"


def test_only_mode_validation_400() -> None:
    from app.core.config import Settings

    payload, code = run_process_pending_documents(
        Settings(),
        uuid4(),
        limit=1,
        max_file_size_bytes=52_428_800,
        include_extensions=frozenset({"pdf"}),
        dry_run=True,
        reprocess_skipped=False,
        reprocess_hwp_no_extractable_text=False,
        only_reprocess_hwp_no_extractable_text=True,
    )
    assert code == 400
    assert "hwp" in str(payload.get("message", ""))


@patch("app.workers.job_runner.run_process_pending_documents_core")
@patch(
    "app.workers.job_runner.scan_jobs_service.is_cancel_requested",
    return_value=False,
)
def test_worker_passes_only_flag(
    _mock_cancel: MagicMock,
    mock_core: MagicMock,
) -> None:
    from app.services.pending_document_processor_service import (
        ProcessPendingDocumentsCoreResult,
    )
    from app.workers.job_runner import run_job
    from app.workers.worker_types import WorkerJob

    job = WorkerJob(
        id=uuid4(),
        data_source_id=uuid4(),
        job_type="PROCESS_PENDING_DOCUMENTS",
        job_params={
            "limit": 1,
            "max_file_size_bytes": 52_428_800,
            "only_reprocess_hwp_no_extractable_text": True,
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
    run_job(job)

    kwargs = mock_core.call_args.kwargs
    assert kwargs.get("only_reprocess_hwp_no_extractable_text") is True
