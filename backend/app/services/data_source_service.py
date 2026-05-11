"""DB operations for ``data_sources`` (CRUD; never expose stored credentials)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from psycopg.errors import UniqueViolation
from psycopg.rows import dict_row

from app.core.config import Settings
from app.core.security import encrypt_credential_plaintext
from app.db.database import get_db_connection
from app.schemas.data_source import WEBDAV_KINDS, DataSourceCreate, DataSourceUpdate
from app.schemas.data_source import SourceType


URL_CHANGE_WARNING = (
    "서버 URL 또는 WebDAV 루트 경로가 변경되었습니다. "
    "기존 분석 데이터와 다른 저장소라면 새 데이터 소스로 등록하는 것을 권장합니다."
)

LOCAL_FOLDER_WARNING = "LOCAL_FOLDER는 추후 지원 예정입니다."


class DataSourceNotFound(Exception):
    pass


class DataSourceConflict(Exception):
    pass


class DataSourceBadRequest(Exception):
    def __init__(self, message: str, error: str | None = None):
        super().__init__(message)
        self.message = message
        self.error = error


_SELECT_PUBLIC = """
    SELECT
        id, name, source_type::text AS source_type, server_url, webdav_root_path, username,
        credential_secret_enc, description, is_active,
        last_connection_test_at, last_connection_success, last_connection_message,
        last_scan_at, created_at, updated_at
"""

_RETURNING_TAIL = """
    RETURNING
        id, name, source_type::text AS source_type, server_url, webdav_root_path, username,
        credential_secret_enc, description, is_active,
        last_connection_test_at, last_connection_success, last_connection_message,
        last_scan_at, created_at, updated_at
"""


def row_to_public_dict(row: dict[str, Any], warnings: list[str] | None) -> dict[str, Any]:
    enc = row.get("credential_secret_enc")
    has_cred = enc is not None and str(enc).strip() != ""
    return {
        "id": row["id"],
        "name": row["name"],
        "source_type": str(row["source_type"]),
        "server_url": row["server_url"],
        "webdav_root_path": row["webdav_root_path"],
        "username": row["username"],
        "has_credential": bool(has_cred),
        "description": row["description"],
        "is_active": row["is_active"],
        "last_connection_test_at": row["last_connection_test_at"],
        "last_connection_success": row["last_connection_success"],
        "last_connection_message": row["last_connection_message"],
        "last_scan_at": row["last_scan_at"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "warnings": warnings if warnings else None,
    }


def _stripped_or_none(val: Any) -> Any:
    if val is None:
        return None
    if isinstance(val, str) and not val.strip():
        return None
    return val


def list_data_sources(
    *,
    include_inactive: bool,
    source_type: str | None,
    keyword: str | None,
) -> dict[str, Any]:
    clauses: list[str] = []
    params: list[Any] = []

    if not include_inactive:
        clauses.append("is_active IS TRUE")

    if source_type is not None and source_type.strip():
        clauses.append("source_type = %s::data_source_type")
        params.append(source_type.strip().upper())

    if keyword is not None and keyword.strip():
        clauses.append("(name ILIKE %s OR description ILIKE %s)")
        like = f"%{keyword.strip()}%"
        params.extend([like, like])

    where_sql = " AND ".join(clauses) if clauses else "TRUE"

    sel = f"{_SELECT_PUBLIC.strip()}\n        FROM data_sources\n        WHERE {where_sql}\n        ORDER BY created_at DESC NULLS LAST, id ASC\n    "
    count_sql = (
        f"SELECT COUNT(*)::int AS cnt FROM data_sources WHERE {where_sql}"
    )

    with get_db_connection() as conn:
        conn.row_factory = dict_row
        with conn.cursor() as cur:
            cur.execute(count_sql, params)
            cr = cur.fetchone()
            total = int(cr["cnt"]) if cr else 0

            cur.execute(sel, params)
            rows = cur.fetchall()

    items = [row_to_public_dict(dict(r), None) for r in rows]
    return {"items": items, "total": total}


def get_data_source(*, ds_id: UUID) -> dict[str, Any]:
    sel = f"{_SELECT_PUBLIC.strip()}\n        FROM data_sources\n        WHERE id = %s\n    "
    with get_db_connection() as conn:
        conn.row_factory = dict_row
        with conn.cursor() as cur:
            cur.execute(sel, (ds_id,))
            row = cur.fetchone()

    if not row:
        raise DataSourceNotFound()
    return row_to_public_dict(dict(row), None)


def fetch_data_source_row_internal(*, ds_id: UUID) -> dict[str, Any]:
    """Load a row including ``credential_secret_enc`` (server-side only)."""
    sel = """
        SELECT
            id,
            name,
            source_type::text AS source_type,
            server_url,
            webdav_root_path,
            username,
            credential_secret_enc,
            is_active
        FROM data_sources
        WHERE id = %s
    """
    with get_db_connection() as conn:
        conn.row_factory = dict_row
        with conn.cursor() as cur:
            cur.execute(sel, (ds_id,))
            row = cur.fetchone()
    if not row:
        raise DataSourceNotFound()
    return dict(row)


def update_last_connection_test_result(
    *, ds_id: UUID, success: bool, message: str
) -> None:
    """Persist WebDAV probe outcome (truncated safely; no secrets)."""
    msg = (message or "").strip()
    if len(msg) > 4000:
        msg = msg[:3997] + "..."

    stmt = """
        UPDATE data_sources
        SET
            last_connection_test_at = NOW(),
            last_connection_success = %s,
            last_connection_message = %s,
            updated_at = NOW()
        WHERE id = %s
    """
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(stmt, (success, msg, ds_id))
        conn.commit()


def _name_exists(conn, name: str, exclude_id: UUID | None = None) -> bool:
    with conn.cursor() as cur:
        if exclude_id is None:
            cur.execute(
                "SELECT 1 FROM data_sources WHERE name = %s LIMIT 1",
                (name.strip(),),
            )
        else:
            cur.execute(
                """
                SELECT 1 FROM data_sources
                WHERE name = %s AND id <> %s
                LIMIT 1
                """,
                (name.strip(), exclude_id),
            )
        return cur.fetchone() is not None


def create_data_source(*, settings: Settings, body: DataSourceCreate) -> dict[str, Any]:
    trimmed_cred: str | None = None
    if body.credential_secret is not None:
        trimmed_cred = body.credential_secret.strip()
        if trimmed_cred == "":
            raise DataSourceBadRequest(
                message="credential_secret cannot be empty",
                error=(
                    "Omit credential_secret or send null when no credential is provided."
                ),
            )

    st_enum = SourceType(body.source_type)
    warnings: list[str] = []
    if st_enum == SourceType.LOCAL_FOLDER:
        warnings.append(LOCAL_FOLDER_WARNING)

    credential_enc: str | None = None
    if trimmed_cred is not None:
        try:
            credential_enc = encrypt_credential_plaintext(settings, trimmed_cred)
        except ValueError as exc:
            raise DataSourceBadRequest(
                message="Invalid encryption configuration",
                error=str(exc),
            ) from exc

    webdav_rp = (
        body.webdav_root_path.strip()
        if body.webdav_root_path and body.webdav_root_path.strip()
        else None
    )

    ins = (
        """
        INSERT INTO data_sources (
            id, name, source_type, server_url, webdav_root_path, username,
            credential_secret_enc, description, is_active,
            created_at, updated_at
        ) VALUES (
            gen_random_uuid(), %s, %s::data_source_type, %s, %s, %s,
            %s, %s, %s,
            NOW(), NOW()
        )
        """
        + _RETURNING_TAIL
    )

    vals = (
        body.name.strip(),
        body.source_type,
        body.server_url.strip(),
        webdav_rp,
        _stripped_or_none(body.username),
        credential_enc,
        _stripped_or_none(body.description),
        body.is_active,
    )

    try:
        with get_db_connection() as conn:
            conn.row_factory = dict_row
            if _name_exists(conn, body.name.strip()):
                raise DataSourceConflict()
            with conn.cursor() as cur:
                cur.execute(ins, vals)
                row = dict(cur.fetchone())
            conn.commit()
    except UniqueViolation as exc:
        raise DataSourceConflict() from exc

    return row_to_public_dict(row, warnings if warnings else None)


def update_data_source(
    *,
    settings: Settings,
    ds_id: UUID,
    body: DataSourceUpdate,
) -> dict[str, Any]:
    fields_set = body.model_fields_set

    with get_db_connection() as conn_fetch:
        conn_fetch.row_factory = dict_row
        with conn_fetch.cursor() as cur:
            cur.execute(
                """
                SELECT
                    id, name, source_type::text AS source_type, server_url,
                    webdav_root_path, username, credential_secret_enc, description,
                    is_active, last_connection_test_at, last_connection_success,
                    last_connection_message, last_scan_at, created_at, updated_at
                FROM data_sources
                WHERE id = %s
                """,
                (ds_id,),
            )
            er = cur.fetchone()

    if not er:
        raise DataSourceNotFound()

    prev = dict(er)
    warnings: list[str] = []

    if "credential_secret" in fields_set:
        cs = body.credential_secret
        if cs is not None and cs.strip() == "":
            raise DataSourceBadRequest(
                message="credential_secret cannot be empty",
                error="Omit credential_secret or send null to keep the existing credential.",
            )

    merged_name = body.name.strip() if body.name is not None else prev["name"]
    merged_type = SourceType(
        body.source_type
        if body.source_type is not None
        else str(prev["source_type"])
    )
    merged_url = (
        body.server_url.strip()
        if body.server_url is not None
        else str(prev["server_url"]).strip()
    )
    if merged_type != SourceType.LOCAL_FOLDER:
        if not (
            merged_url.startswith("http://") or merged_url.startswith("https://")
        ):
            raise DataSourceBadRequest(
                message="Validation failed",
                error=(
                    "server_url must start with http:// or https:// "
                    "for WebDAV source types"
                ),
            )

    merged_root_raw = (
        body.webdav_root_path
        if "webdav_root_path" in fields_set
        else prev.get("webdav_root_path")
    )
    merged_root = _stripped_or_none(merged_root_raw)

    if merged_type in WEBDAV_KINDS:
        if not merged_root:
            raise DataSourceBadRequest(
                message="Validation failed",
                error="webdav_root_path is required for WebDAV-related source types",
            )

    if merged_type == SourceType.LOCAL_FOLDER and "source_type" in fields_set:
        warnings.append(LOCAL_FOLDER_WARNING)

    if "server_url" in fields_set and merged_url != str(prev["server_url"]).strip():
        warnings.append(URL_CHANGE_WARNING)
    if (
        "webdav_root_path" in fields_set
        and merged_root != _stripped_or_none(prev.get("webdav_root_path"))
    ):
        if URL_CHANGE_WARNING not in warnings:
            warnings.append(URL_CHANGE_WARNING)

    set_parts: list[str] = []
    params: list[Any] = []

    if body.name is not None:
        set_parts.append("name = %s")
        params.append(body.name.strip())
    if body.source_type is not None:
        set_parts.append("source_type = %s::data_source_type")
        params.append(body.source_type)
    if body.server_url is not None:
        set_parts.append("server_url = %s")
        params.append(body.server_url.strip())
    if "webdav_root_path" in fields_set:
        set_parts.append("webdav_root_path = %s")
        params.append(merged_root)

    if "username" in fields_set:
        set_parts.append("username = %s")
        params.append(_stripped_or_none(body.username))

    if "description" in fields_set:
        set_parts.append("description = %s")
        params.append(_stripped_or_none(body.description))

    if body.is_active is not None:
        set_parts.append("is_active = %s")
        params.append(body.is_active)

    if "credential_secret" in fields_set and body.credential_secret is not None:
        try:
            trimmed_upd = body.credential_secret.strip()
            enc_u = encrypt_credential_plaintext(
                settings,
                trimmed_upd,
            )
            set_parts.append("credential_secret_enc = %s")
            params.append(enc_u)
        except ValueError as exc:
            raise DataSourceBadRequest(
                message="Invalid encryption configuration",
                error=str(exc),
            ) from exc

    # credential_secret: null/absent preserves existing ciphertext (omit column).

    if not set_parts:
        return row_to_public_dict(prev, warnings if warnings else None)

    params.append(ds_id)
    stmt = (
        "UPDATE data_sources SET "
        + ", ".join(set_parts)
        + ", updated_at = NOW() WHERE id = %s\n        "
        + _RETURNING_TAIL.strip()
        + "\n    "
    )

    try:
        with get_db_connection() as conn:
            conn.row_factory = dict_row
            if body.name is not None and body.name.strip() != prev["name"]:
                if _name_exists(conn, merged_name.strip(), exclude_id=ds_id):
                    raise DataSourceConflict()
            with conn.cursor() as cur:
                cur.execute(stmt, params)
                row_out = dict(cur.fetchone())
            conn.commit()
    except UniqueViolation as exc:
        raise DataSourceConflict() from exc

    return row_to_public_dict(row_out, warnings if warnings else None)


def set_active(
    *,
    ds_id: UUID,
    is_active: bool,
) -> dict[str, Any]:
    stmt = (
        """
        UPDATE data_sources SET is_active = %s, updated_at = NOW()
        WHERE id = %s
        """
        + _RETURNING_TAIL
    )
    vals = (is_active, ds_id)

    with get_db_connection() as conn:
        conn.row_factory = dict_row
        with conn.cursor() as cur:
            cur.execute(stmt, vals)
            row = cur.fetchone()
        conn.commit()

    if not row:
        raise DataSourceNotFound()
    return row_to_public_dict(dict(row), None)
