"""Orchestrator for ``POST /api/data-sources/{id}/process-pending-documents``.

Mirrors the Step-12 text processor shape (WebDAV GET, per-file DB
transactions, ``scan_jobs`` / ``scan_failures``) but routes bytes through
the document parser registry (PDF / DOCX / XLSX / PPTX / HWPX).

Synchronous routes call :func:`run_process_pending_documents` (dry-run or
``create_scan_job`` + core). The DB worker runs
:func:`run_process_pending_documents_core` with an existing ``scan_job_id``.

Credentials, Authorization headers, download URLs with embedded secrets,
and full extracted bodies never appear in logs or persisted error text.

**Heartbeat note:** Progress/heartbeat updates run between files (and
before each download). A single large PDF/DOCX parse can block for a long
time without intermediate heartbeats; finer-grained parser hooks or
worker timeout policy are left for a future iteration.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.core.config import Settings
from app.core.security import decrypt_credential_token
from app.db.database import get_db_connection
from app.parsers.base import DocumentParser
from app.parsers.registry import (
    get_parser_for_extension,
    supported_document_extensions,
)
from app.schemas.data_source import WEBDAV_KINDS, SourceType
from app.services import data_source_service as datasource_svc
from app.services import scan_failures_service
from app.services import scan_jobs_service
from app.services.data_source_service import DataSourceNotFound
from app.services.file_contents_service import (
    apply_completed,
    apply_failed,
    apply_skipped,
    fetch_pending_document_files,
)
from app.services.text_extraction_service import (
    normalize_extension,
    parse_include_extensions,
)
from app.webdav.download import download_file_bytes

_LIMIT_MIN = 1
_LIMIT_MAX = 5000
_SIZE_MIN = 1
_SIZE_MAX = 256 * 1024 * 1024

SUCCESS_MESSAGE = "Pending document files processed"
DRY_RUN_MESSAGE = "Dry run completed. No files were downloaded or updated."
AUTH_FAILURE_MESSAGE = "WebDAV authentication failed"

_ERR_UNSUPPORTED_EXT = "UNSUPPORTED_EXTENSION"
_ERR_FILE_TOO_LARGE = "FILE_TOO_LARGE"
_ERR_DOWNLOAD_FAILED = "DOWNLOAD_FAILED"
_ERR_NO_EXTRACTABLE_TEXT = "NO_EXTRACTABLE_TEXT"
_ERR_PASSWORD_PROTECTED = "PASSWORD_PROTECTED"
_ERR_PARSING_FAILED = "PARSING_FAILED"

_MSG_UNSUPPORTED_EXT = "Unsupported document extension"
_MSG_FILE_TOO_LARGE = "File size exceeds max_file_size_bytes"
_MSG_NO_EXTRACTABLE_TEXT = "No extractable text found"
_MSG_PASSWORD_PROTECTED = "Password protected document"

_MIN_MEANINGFUL_STRIP_LEN = 5

_PROGRESS_HEARTBEAT_EVERY = 5
_CANCELLED_MESSAGE = "Job cancelled by request"


def _clamp(value: int, lo: int, hi: int) -> int:
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


def _error_payload(
    *,
    message: str,
    data_source_id: UUID | None = None,
    name: str | None = None,
    scan_job_id: UUID | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {"status": "error", "message": message}
    if data_source_id is not None:
        out["data_source_id"] = str(data_source_id)
    if name is not None:
        out["name"] = name
    if scan_job_id is not None:
        out["scan_job_id"] = str(scan_job_id)
    if error:
        out["error"] = error
    return out


def _parser_label(parser: DocumentParser) -> str:
    return str(getattr(parser, "PARSER_NAME", type(parser).__name__))


def _make_item(
    row: dict[str, Any],
    *,
    status: str | None = None,
    planned_action: str | None = None,
    reason: str | None = None,
    text_length: int | None = None,
    content_hash: str | None = None,
    parser_name: str | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "file_id": str(row.get("id")),
        "remote_path": row.get("remote_path"),
        "filename": row.get("filename"),
        "extension": row.get("extension"),
    }
    if status is not None:
        item["status"] = status
    if planned_action is not None:
        item["planned_action"] = planned_action
    if reason is not None:
        item["reason"] = reason
    if text_length is not None:
        item["text_length"] = text_length
    if content_hash is not None:
        item["content_hash"] = content_hash
    if parser_name is not None:
        item["parser_name"] = parser_name
    return item


def _classify_pre_download(
    row: dict[str, Any], *, max_file_size_bytes: int, allowed_ext: frozenset[str]
) -> tuple[str | None, str | None]:
    ext = normalize_extension(row.get("extension"))
    if ext not in allowed_ext:
        return _ERR_UNSUPPORTED_EXT, _MSG_UNSUPPORTED_EXT
    size = row.get("size_bytes")
    if size is not None:
        try:
            size_int = int(size)
        except (TypeError, ValueError):
            size_int = -1
        if size_int > max_file_size_bytes:
            return _ERR_FILE_TOO_LARGE, _MSG_FILE_TOO_LARGE
    return None, None


def _meaningful_text(text: str | None) -> bool:
    if text is None:
        return False
    s = "".join(str(text).split())
    return len(s) >= _MIN_MEANINGFUL_STRIP_LEN


def _resolve_effective_extensions(
    include_extensions: frozenset[str] | None,
) -> frozenset[str]:
    base = supported_document_extensions()
    if include_extensions is None:
        return base
    inter = frozenset(include_extensions) & base
    return inter


def _normalize_include_extensions_input(
    include_extensions: frozenset[str] | str | None,
) -> frozenset[str] | None:
    if include_extensions is None:
        return None
    if isinstance(include_extensions, frozenset):
        return include_extensions
    if isinstance(include_extensions, str):
        s = include_extensions.strip()
        if not s:
            return None
        return parse_include_extensions(s)
    return frozenset(include_extensions)


def _build_dry_run_payload(
    *,
    data_source_id: UUID,
    name: str,
    rows: list[dict[str, Any]],
    max_file_size_bytes: int,
    allowed_ext: frozenset[str],
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for prow in rows:
        parser = get_parser_for_extension(str(prow.get("extension") or ""))
        skip_code, _ = _classify_pre_download(
            prow, max_file_size_bytes=max_file_size_bytes, allowed_ext=allowed_ext
        )
        if skip_code is None:
            items.append(
                _make_item(
                    prow,
                    planned_action="PROCESS",
                    parser_name=_parser_label(parser),
                )
            )
        else:
            items.append(
                _make_item(
                    prow,
                    planned_action="SKIP",
                    reason=skip_code,
                    parser_name=_parser_label(parser),
                )
            )
    return {
        "status": "ok",
        "data_source_id": str(data_source_id),
        "name": name,
        "target_count": len(rows),
        "dry_run": True,
        "message": DRY_RUN_MESSAGE,
        "items": items,
    }


def _commit_skip(
    conn,
    *,
    ds_id: UUID,
    scan_job_id: UUID | None,
    file_id: UUID,
    remote_path: str,
    error_code: str,
    error_message: str | None,
) -> None:
    try:
        apply_skipped(
            conn,
            file_id=file_id,
            error_code=error_code,
            error_message=error_message,
        )
        conn.commit()
    except Exception:
        conn.rollback()
    scan_failures_service.record_scan_failure(
        scan_job_id=scan_job_id,
        data_source_id=ds_id,
        file_id=file_id,
        remote_path=remote_path,
        error_code=error_code,
        error_message=error_message,
    )


def _commit_failed(
    conn,
    *,
    ds_id: UUID,
    scan_job_id: UUID | None,
    file_id: UUID,
    remote_path: str,
    error_code: str,
    error_message: str | None,
) -> None:
    try:
        apply_failed(
            conn,
            file_id=file_id,
            error_code=error_code,
            error_message=error_message,
        )
        conn.commit()
    except Exception:
        conn.rollback()
    scan_failures_service.record_scan_failure(
        scan_job_id=scan_job_id,
        data_source_id=ds_id,
        file_id=file_id,
        remote_path=remote_path,
        error_code=error_code,
        error_message=error_message,
    )


def _process_one_file(
    conn,
    *,
    ds_id: UUID,
    scan_job_id: UUID | None,
    row: dict[str, Any],
    server_url: str,
    webdav_root: str,
    uname: str,
    password: str,
    timeout_seconds: float,
    max_file_size_bytes: int,
    allowed_ext: frozenset[str],
) -> dict[str, Any]:
    file_id: UUID = row["id"]
    remote_path = row.get("remote_path") or ""
    prior_hash = row.get("content_hash")
    parser = get_parser_for_extension(str(row.get("extension") or ""))

    skip_code, skip_msg = _classify_pre_download(
        row, max_file_size_bytes=max_file_size_bytes, allowed_ext=allowed_ext
    )
    if skip_code is not None:
        _commit_skip(
            conn,
            ds_id=ds_id,
            scan_job_id=scan_job_id,
            file_id=file_id,
            remote_path=remote_path,
            error_code=skip_code,
            error_message=skip_msg,
        )
        return {
            "kind": "skipped",
            "item": _make_item(
                row,
                status="SKIPPED",
                reason=skip_code,
                parser_name=_parser_label(parser),
            ),
        }

    outcome = download_file_bytes(
        server_url=server_url,
        webdav_root_path=webdav_root,
        remote_path=remote_path,
        username=uname,
        password=password,
        timeout_seconds=timeout_seconds,
        max_bytes=max_file_size_bytes,
    )

    if outcome.auth_failed:
        _commit_failed(
            conn,
            ds_id=ds_id,
            scan_job_id=scan_job_id,
            file_id=file_id,
            remote_path=remote_path,
            error_code=_ERR_DOWNLOAD_FAILED,
            error_message=outcome.error_summary or AUTH_FAILURE_MESSAGE,
        )
        return {
            "kind": "failed",
            "auth_failed": True,
            "auth_error": outcome.error_summary,
            "item": _make_item(
                row,
                status="FAILED",
                reason=_ERR_DOWNLOAD_FAILED,
                parser_name=_parser_label(parser),
            ),
        }

    if outcome.truncated:
        _commit_skip(
            conn,
            ds_id=ds_id,
            scan_job_id=scan_job_id,
            file_id=file_id,
            remote_path=remote_path,
            error_code=_ERR_FILE_TOO_LARGE,
            error_message=_MSG_FILE_TOO_LARGE,
        )
        return {
            "kind": "skipped",
            "item": _make_item(
                row,
                status="SKIPPED",
                reason=_ERR_FILE_TOO_LARGE,
                parser_name=_parser_label(parser),
            ),
        }

    if not outcome.success:
        _commit_failed(
            conn,
            ds_id=ds_id,
            scan_job_id=scan_job_id,
            file_id=file_id,
            remote_path=remote_path,
            error_code=_ERR_DOWNLOAD_FAILED,
            error_message=outcome.error_summary or "Download failed",
        )
        return {
            "kind": "failed",
            "item": _make_item(
                row,
                status="FAILED",
                reason=_ERR_DOWNLOAD_FAILED,
                parser_name=_parser_label(parser),
            ),
        }

    body: bytes = outcome.body
    filename = str(row.get("filename") or "")
    extension = str(row.get("extension") or "")

    try:
        parsed = parser.parse_bytes(body, filename, extension)
    except Exception:
        _commit_failed(
            conn,
            ds_id=ds_id,
            scan_job_id=scan_job_id,
            file_id=file_id,
            remote_path=remote_path,
            error_code=_ERR_PARSING_FAILED,
            error_message="Document parsing failed",
        )
        return {
            "kind": "failed",
            "item": _make_item(
                row,
                status="FAILED",
                reason=_ERR_PARSING_FAILED,
                parser_name=_parser_label(parser),
            ),
        }

    if not parsed.success:
        code = (parsed.error_code or _ERR_PARSING_FAILED).strip().upper()
        if code == _ERR_PASSWORD_PROTECTED:
            _commit_failed(
                conn,
                ds_id=ds_id,
                scan_job_id=scan_job_id,
                file_id=file_id,
                remote_path=remote_path,
                error_code=_ERR_PASSWORD_PROTECTED,
                error_message=_MSG_PASSWORD_PROTECTED,
            )
            return {
                "kind": "failed",
                "item": _make_item(
                    row,
                    status="FAILED",
                    reason=_ERR_PASSWORD_PROTECTED,
                    parser_name=_parser_label(parser),
                ),
            }
        if code == _ERR_UNSUPPORTED_EXT:
            _commit_skip(
                conn,
                ds_id=ds_id,
                scan_job_id=scan_job_id,
                file_id=file_id,
                remote_path=remote_path,
                error_code=_ERR_UNSUPPORTED_EXT,
                error_message=_MSG_UNSUPPORTED_EXT,
            )
            return {
                "kind": "skipped",
                "item": _make_item(
                    row,
                    status="SKIPPED",
                    reason=_ERR_UNSUPPORTED_EXT,
                    parser_name=_parser_label(parser),
                ),
            }
        if code == _ERR_NO_EXTRACTABLE_TEXT:
            _commit_skip(
                conn,
                ds_id=ds_id,
                scan_job_id=scan_job_id,
                file_id=file_id,
                remote_path=remote_path,
                error_code=_ERR_NO_EXTRACTABLE_TEXT,
                error_message=_MSG_NO_EXTRACTABLE_TEXT,
            )
            return {
                "kind": "skipped",
                "item": _make_item(
                    row,
                    status="SKIPPED",
                    reason=_ERR_NO_EXTRACTABLE_TEXT,
                    parser_name=parsed.parser_name or _parser_label(parser),
                ),
            }
        _commit_failed(
            conn,
            ds_id=ds_id,
            scan_job_id=scan_job_id,
            file_id=file_id,
            remote_path=remote_path,
            error_code=_ERR_PARSING_FAILED,
            error_message="Document parsing failed",
        )
        return {
            "kind": "failed",
            "item": _make_item(
                row,
                status="FAILED",
                reason=_ERR_PARSING_FAILED,
                parser_name=_parser_label(parser),
            ),
        }

    text = parsed.extracted_text or ""
    if not _meaningful_text(text):
        _commit_skip(
            conn,
            ds_id=ds_id,
            scan_job_id=scan_job_id,
            file_id=file_id,
            remote_path=remote_path,
            error_code=_ERR_NO_EXTRACTABLE_TEXT,
            error_message=_MSG_NO_EXTRACTABLE_TEXT,
        )
        return {
            "kind": "skipped",
            "item": _make_item(
                row,
                status="SKIPPED",
                reason=_ERR_NO_EXTRACTABLE_TEXT,
                parser_name=parsed.parser_name,
            ),
        }

    content_hash = hashlib.sha256(body).hexdigest()
    unchanged = (
        isinstance(prior_hash, str)
        and prior_hash.strip().lower() == content_hash.lower()
    )

    try:
        apply_completed(
            conn,
            file_id=file_id,
            data_source_id=ds_id,
            extracted_text=text,
            content_hash=content_hash,
            parser_name=parsed.parser_name,
            parser_version=parsed.parser_version,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        _commit_failed(
            conn,
            ds_id=ds_id,
            scan_job_id=scan_job_id,
            file_id=file_id,
            remote_path=remote_path,
            error_code=_ERR_PARSING_FAILED,
            error_message="Document persistence failed",
        )
        return {
            "kind": "failed",
            "item": _make_item(
                row,
                status="FAILED",
                reason="PERSISTENCE_FAILED",
                parser_name=parsed.parser_name,
            ),
        }

    item = _make_item(
        row,
        status="UNCHANGED" if unchanged else "COMPLETED",
        text_length=len(text),
        content_hash=content_hash,
        parser_name=parsed.parser_name,
    )
    return {
        "kind": "unchanged" if unchanged else "completed",
        "item": item,
    }


def _pending_document_webdav_context(
    settings: Settings, ds_id: UUID
) -> tuple[dict[str, Any] | None, tuple[dict[str, Any], int] | None]:
    """Return ``(ctx, None)`` or ``(None, (error_payload, http_status))``."""
    try:
        row = datasource_svc.fetch_data_source_row_internal(ds_id=ds_id)
    except DataSourceNotFound:
        return (
            None,
            (
                _error_payload(
                    message="Data source not found",
                    data_source_id=ds_id,
                ),
                404,
            ),
        )

    source_type_str = str(row["source_type"]).strip().upper()
    ds_name = row["name"]

    try:
        source_type_enum = SourceType(source_type_str)
    except ValueError:
        source_type_enum = None
    if source_type_enum == SourceType.LOCAL_FOLDER:
        return (
            None,
            (
                _error_payload(
                    message="LOCAL_FOLDER pending-document processing is not supported yet",
                    data_source_id=ds_id,
                    name=ds_name,
                ),
                400,
            ),
        )
    if source_type_enum is None or source_type_enum not in WEBDAV_KINDS:
        return (
            None,
            (
                _error_payload(
                    message=(
                        f"Unsupported source_type {source_type_str} "
                        "for pending-document processing"
                    ),
                    data_source_id=ds_id,
                    name=ds_name,
                ),
                400,
            ),
        )

    uname_raw = row.get("username")
    uname = (uname_raw or "").strip() if uname_raw is not None else ""
    enc_blob = row.get("credential_secret_enc")
    cred_present = isinstance(enc_blob, str) and enc_blob.strip() != ""
    if not uname or not cred_present:
        return (
            None,
            (
                _error_payload(
                    message="WebDAV username or credential is missing",
                    data_source_id=ds_id,
                    name=ds_name,
                ),
                400,
            ),
        )

    server_url = (row["server_url"] or "").strip()
    if not (
        server_url.startswith("http://") or server_url.startswith("https://")
    ):
        return (
            None,
            (
                _error_payload(
                    message="server_url must start with http:// or https://",
                    data_source_id=ds_id,
                    name=ds_name,
                ),
                400,
            ),
        )

    wr_row = row.get("webdav_root_path")
    webdav_root = (
        wr_row.strip() if isinstance(wr_row, str) else str(wr_row or "").strip()
    )
    if not webdav_root:
        return (
            None,
            (
                _error_payload(
                    message="webdav_root_path is required for WebDAV-based data sources",
                    data_source_id=ds_id,
                    name=ds_name,
                ),
                400,
            ),
        )

    try:
        password = decrypt_credential_token(settings, str(enc_blob).strip())
    except ValueError:
        return (
            None,
            (
                _error_payload(
                    message="Failed to decrypt stored credential",
                    data_source_id=ds_id,
                    name=ds_name,
                ),
                400,
            ),
        )

    ctx: dict[str, Any] = {
        "ds_name": ds_name,
        "server_url": server_url,
        "webdav_root": webdav_root,
        "uname": uname,
        "password": password,
    }
    return ctx, None


def _emit_document_progress(
    *,
    scan_job_id: UUID | None,
    heartbeat_worker_id: str | None,
    processed: int,
    completed: int,
    failed: int,
    skipped: int,
    current_path: str | None,
) -> None:
    if scan_job_id is None:
        return
    scan_jobs_service.update_scan_job_progress(
        job_id=scan_job_id,
        processed_files=processed,
        completed_files=completed,
        failed_files=failed,
        skipped_files=skipped,
        current_file_path=current_path,
        heartbeat=True,
    )
    if heartbeat_worker_id:
        scan_jobs_service.update_job_heartbeat(scan_job_id, heartbeat_worker_id)


@dataclass(frozen=True)
class ProcessPendingDocumentsCoreResult:
    """Outcome of :func:`run_process_pending_documents_core` (sync + worker)."""

    payload: dict[str, Any]
    http_status: int
    finalized_scan_job: bool


def run_process_pending_documents_core(
    settings: Settings,
    ds_id: UUID,
    *,
    limit: int,
    max_file_size_bytes: int,
    include_extensions: frozenset[str] | str | None,
    reprocess_skipped: bool,
    scan_job_id: UUID | None,
    requested_by: UUID | None = None,
    cancel_check: Callable[[], bool] | None = None,
    heartbeat_worker_id: str | None = None,
    preflight_ctx: dict[str, Any] | None = None,
) -> ProcessPendingDocumentsCoreResult:
    """Process PENDING document files. Used by worker with existing ``scan_job_id``."""
    _ = requested_by

    eff_limit = _clamp(int(limit), _LIMIT_MIN, _LIMIT_MAX)
    eff_size_cap = _clamp(int(max_file_size_bytes), _SIZE_MIN, _SIZE_MAX)
    ext_norm = _normalize_include_extensions_input(include_extensions)
    allowed_ext = _resolve_effective_extensions(ext_norm)

    if preflight_ctx is not None:
        ctx = preflight_ctx
        err_t: tuple[dict[str, Any], int] | None = None
    else:
        ctx, err_t = _pending_document_webdav_context(settings, ds_id)

    if err_t is not None:
        ep, code = err_t
        if scan_job_id is not None:
            scan_jobs_service.fail_scan_job(
                job_id=scan_job_id,
                error_message=str(ep.get("message") or "Preflight failed"),
            )
        if scan_job_id is not None and ep.get("scan_job_id") is None:
            ep = {**ep, "scan_job_id": str(scan_job_id)}
        return ProcessPendingDocumentsCoreResult(
            payload=ep,
            http_status=code,
            finalized_scan_job=bool(scan_job_id),
        )

    ds_name = str(ctx["ds_name"])
    server_url = str(ctx["server_url"])
    webdav_root = str(ctx["webdav_root"])
    uname = str(ctx["uname"])
    password = str(ctx["password"])

    pending_rows = fetch_pending_document_files(
        ds_id=ds_id,
        limit=eff_limit,
        document_extensions=allowed_ext,
        reprocess_skipped=reprocess_skipped,
    )
    target_count = len(pending_rows)

    items: list[dict[str, Any]] = []
    completed_count = 0
    skipped_count = 0
    failed_count = 0
    warnings: list[str] = []

    timeout_seconds = float(settings.webdav_timeout_seconds)

    def _cancelled() -> bool:
        return bool(cancel_check and cancel_check())

    if scan_job_id is not None:
        _emit_document_progress(
            scan_job_id=scan_job_id,
            heartbeat_worker_id=heartbeat_worker_id,
            processed=0,
            completed=0,
            failed=0,
            skipped=0,
            current_path=None,
        )

    if _cancelled() and scan_job_id is not None:
        scan_jobs_service.mark_job_cancelled(
            scan_job_id, message=_CANCELLED_MESSAGE
        )
        return ProcessPendingDocumentsCoreResult(
            payload={
                "status": "ok",
                "data_source_id": str(ds_id),
                "name": ds_name,
                "scan_job_id": str(scan_job_id),
                "target_count": target_count,
                "processed_count": 0,
                "completed_count": 0,
                "skipped_count": 0,
                "failed_count": 0,
                "cancelled": True,
                "dry_run": False,
                "message": _CANCELLED_MESSAGE,
                "items": [],
                "warnings": warnings,
            },
            http_status=200,
            finalized_scan_job=True,
        )

    try:
        with get_db_connection() as conn:
            for idx, prow in enumerate(pending_rows):
                remote_path = str(prow.get("remote_path") or "")
                if _cancelled() and scan_job_id is not None:
                    scan_jobs_service.mark_job_cancelled(
                        scan_job_id, message=_CANCELLED_MESSAGE
                    )
                    processed_count = completed_count + skipped_count + failed_count
                    return ProcessPendingDocumentsCoreResult(
                        payload={
                            "status": "ok",
                            "data_source_id": str(ds_id),
                            "name": ds_name,
                            "scan_job_id": str(scan_job_id),
                            "target_count": target_count,
                            "processed_count": processed_count,
                            "completed_count": completed_count,
                            "skipped_count": skipped_count,
                            "failed_count": failed_count,
                            "cancelled": True,
                            "dry_run": False,
                            "message": _CANCELLED_MESSAGE,
                            "items": items,
                            "warnings": warnings,
                        },
                        http_status=200,
                        finalized_scan_job=True,
                    )

                if scan_job_id is not None:
                    _emit_document_progress(
                        scan_job_id=scan_job_id,
                        heartbeat_worker_id=heartbeat_worker_id,
                        processed=completed_count + skipped_count + failed_count,
                        completed=completed_count,
                        failed=failed_count,
                        skipped=skipped_count,
                        current_path=remote_path or None,
                    )

                if _cancelled() and scan_job_id is not None:
                    scan_jobs_service.mark_job_cancelled(
                        scan_job_id, message=_CANCELLED_MESSAGE
                    )
                    processed_count = completed_count + skipped_count + failed_count
                    return ProcessPendingDocumentsCoreResult(
                        payload={
                            "status": "ok",
                            "data_source_id": str(ds_id),
                            "name": ds_name,
                            "scan_job_id": str(scan_job_id),
                            "target_count": target_count,
                            "processed_count": processed_count,
                            "completed_count": completed_count,
                            "skipped_count": skipped_count,
                            "failed_count": failed_count,
                            "cancelled": True,
                            "dry_run": False,
                            "message": _CANCELLED_MESSAGE,
                            "items": items,
                            "warnings": warnings,
                        },
                        http_status=200,
                        finalized_scan_job=True,
                    )

                outcome = _process_one_file(
                    conn,
                    ds_id=ds_id,
                    scan_job_id=scan_job_id,
                    row=prow,
                    server_url=server_url,
                    webdav_root=webdav_root,
                    uname=uname,
                    password=password,
                    timeout_seconds=timeout_seconds,
                    max_file_size_bytes=eff_size_cap,
                    allowed_ext=allowed_ext,
                )
                items.append(outcome["item"])
                if outcome["kind"] == "completed":
                    completed_count += 1
                elif outcome["kind"] == "unchanged":
                    completed_count += 1
                elif outcome["kind"] == "skipped":
                    skipped_count += 1
                elif outcome["kind"] == "failed":
                    failed_count += 1

                processed_now = completed_count + skipped_count + failed_count
                last_idx = idx == len(pending_rows) - 1
                if scan_job_id is not None and (
                    last_idx or (idx + 1) % _PROGRESS_HEARTBEAT_EVERY == 0
                ):
                    _emit_document_progress(
                        scan_job_id=scan_job_id,
                        heartbeat_worker_id=heartbeat_worker_id,
                        processed=processed_now,
                        completed=completed_count,
                        failed=failed_count,
                        skipped=skipped_count,
                        current_path=remote_path or None,
                    )

                if outcome.get("auth_failed"):
                    msg = AUTH_FAILURE_MESSAGE
                    err = outcome.get("auth_error") or "HTTP 401 Unauthorized"
                    if scan_job_id is not None:
                        scan_jobs_service.fail_scan_job(
                            job_id=scan_job_id, error_message=msg
                        )
                    return ProcessPendingDocumentsCoreResult(
                        payload={
                            "status": "error",
                            "data_source_id": str(ds_id),
                            "name": ds_name,
                            "scan_job_id": (
                                str(scan_job_id) if scan_job_id else None
                            ),
                            "message": msg,
                            "error": err,
                            "processed_count": processed_now,
                            "completed_count": completed_count,
                            "skipped_count": skipped_count,
                            "failed_count": failed_count,
                            "items": items,
                        },
                        http_status=200,
                        finalized_scan_job=bool(scan_job_id),
                    )

                if _cancelled() and scan_job_id is not None:
                    scan_jobs_service.mark_job_cancelled(
                        scan_job_id, message=_CANCELLED_MESSAGE
                    )
                    return ProcessPendingDocumentsCoreResult(
                        payload={
                            "status": "ok",
                            "data_source_id": str(ds_id),
                            "name": ds_name,
                            "scan_job_id": str(scan_job_id),
                            "target_count": target_count,
                            "processed_count": processed_now,
                            "completed_count": completed_count,
                            "skipped_count": skipped_count,
                            "failed_count": failed_count,
                            "cancelled": True,
                            "dry_run": False,
                            "message": _CANCELLED_MESSAGE,
                            "items": items,
                            "warnings": warnings,
                        },
                        http_status=200,
                        finalized_scan_job=True,
                    )
    except Exception as exc:  # pragma: no cover - defensive batch guard
        if scan_job_id is not None:
            scan_jobs_service.fail_scan_job(
                job_id=scan_job_id,
                error_message="Pending-document processing failed",
            )
        return ProcessPendingDocumentsCoreResult(
            payload=_error_payload(
                message="Pending-document processing failed",
                data_source_id=ds_id,
                name=ds_name,
                scan_job_id=scan_job_id,
                error=str(exc),
            ),
            http_status=500,
            finalized_scan_job=bool(scan_job_id),
        )

    processed_count = completed_count + skipped_count + failed_count

    if scan_job_id is not None:
        _emit_document_progress(
            scan_job_id=scan_job_id,
            heartbeat_worker_id=heartbeat_worker_id,
            processed=processed_count,
            completed=completed_count,
            failed=failed_count,
            skipped=skipped_count,
            current_path=None,
        )
        scan_jobs_service.complete_scan_job(
            job_id=scan_job_id,
            total_files=target_count,
            processed_files=processed_count,
            completed_files=completed_count,
            failed_files=failed_count,
            skipped_files=skipped_count,
            deleted_files=0,
        )

    return ProcessPendingDocumentsCoreResult(
        payload={
            "status": "ok",
            "data_source_id": str(ds_id),
            "name": ds_name,
            "scan_job_id": str(scan_job_id) if scan_job_id else None,
            "target_count": target_count,
            "processed_count": processed_count,
            "completed_count": completed_count,
            "skipped_count": skipped_count,
            "failed_count": failed_count,
            "dry_run": False,
            "message": SUCCESS_MESSAGE,
            "items": items,
            "warnings": warnings,
        },
        http_status=200,
        finalized_scan_job=bool(scan_job_id),
    )


def run_process_pending_documents(
    settings: Settings,
    ds_id: UUID,
    *,
    limit: int,
    max_file_size_bytes: int,
    include_extensions: frozenset[str] | None,
    dry_run: bool,
    reprocess_skipped: bool,
    requested_by: UUID | None = None,
) -> tuple[dict[str, Any], int]:
    ctx, err = _pending_document_webdav_context(settings, ds_id)
    if err is not None:
        return err[0], err[1]

    ds_name = str(ctx["ds_name"])
    eff_limit = _clamp(int(limit), _LIMIT_MIN, _LIMIT_MAX)
    eff_size_cap = _clamp(int(max_file_size_bytes), _SIZE_MIN, _SIZE_MAX)
    allowed_ext = _resolve_effective_extensions(include_extensions)

    pending_rows = fetch_pending_document_files(
        ds_id=ds_id,
        limit=eff_limit,
        document_extensions=allowed_ext,
        reprocess_skipped=reprocess_skipped,
    )

    if dry_run:
        return (
            _build_dry_run_payload(
                data_source_id=ds_id,
                name=ds_name,
                rows=pending_rows,
                max_file_size_bytes=eff_size_cap,
                allowed_ext=allowed_ext,
            ),
            200,
        )

    scan_job_id = scan_jobs_service.create_scan_job(
        ds_id=ds_id,
        job_type=scan_jobs_service.JOB_TYPE_PROCESS_PENDING_DOCUMENTS,
        requested_by=requested_by,
    )

    core = run_process_pending_documents_core(
        settings,
        ds_id,
        limit=eff_limit,
        max_file_size_bytes=eff_size_cap,
        include_extensions=include_extensions,
        reprocess_skipped=reprocess_skipped,
        scan_job_id=scan_job_id,
        requested_by=requested_by,
        preflight_ctx=ctx,
    )
    return core.payload, core.http_status


__all__ = [
    "ProcessPendingDocumentsCoreResult",
    "run_process_pending_documents",
    "run_process_pending_documents_core",
]
