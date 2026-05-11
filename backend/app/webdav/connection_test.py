"""Run a Depth:0 PROPFIND WebDAV probe for a configured data source (no indexing)."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.core.config import Settings
from app.core.security import decrypt_credential_token
from app.schemas.data_source import WEBDAV_KINDS, SourceType
from app.services import data_source_service as datasource_svc
from app.webdav.client import join_webdav_url, run_propfind

SUCCESS_MESSAGE = "WebDAV connection test succeeded"
PARSE_WARNING = (
    "Connected successfully, but failed to parse WebDAV XML response"
)
PARSE_PARTIAL_WARNING = "Connected successfully; DAV XML did not expose expected properties"


@dataclass
class ParsedPropfind:
    root_info: dict[str, Any] | None
    warnings: list[str]
    dav_resource_ok: bool | None
    dav_auth_ok: bool | None


def local_name(tag: str) -> str:
    if tag.startswith("{") and "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def analyze_propfind_body(
    raw: bytes, http_status: int | None
) -> ParsedPropfind:
    warns: list[str] = []

    if http_status not in {200, 207}:
        return ParsedPropfind(None, warns, None, None)

    if not raw.strip():
        warns.append(PARSE_WARNING)
        return ParsedPropfind(None, warns, None, None)

    try:
        tree = ET.fromstring(raw)
    except ET.ParseError:
        warns.append(PARSE_WARNING)
        return ParsedPropfind(None, warns, None, None)

    multistatus = None
    for el in tree.iter():
        if local_name(el.tag) == "multistatus":
            multistatus = el
            break

    if multistatus is None:
        warns.append(
            "WebDAV XML did not contain a multistatus element; treating as ambiguous"
        )
        return ParsedPropfind(None, warns, None, None)

    responses = [
        child
        for child in multistatus
        if local_name(child.tag) == "response"
    ]
    if not responses:
        warns.append("Empty DAV multistatus response")
        return ParsedPropfind(None, warns, False, False)

    first = responses[0]
    propstats = [
        ps for ps in first if local_name(ps.tag) == "propstat"
    ]
    if not propstats:
        warns.append("DAV response lacked propstat elements")
        return ParsedPropfind(None, warns, False, None)

    chosen: ET.Element | None = None
    auth_fail_inner = False

    for ps in propstats:
        status_elements = [
            se for se in ps if local_name(se.tag) == "status"
        ]
        combo = " ".join(
            (se.text or "").strip() for se in status_elements if se.text
        ).lower()

        if "401" in combo or "403" in combo or "forbidden" in combo:
            auth_fail_inner = True
        if "200" in combo:
            chosen = ps
            break

    dav_auth_inner: bool | None
    if auth_fail_inner:
        dav_auth_inner = False
    elif chosen is not None:
        dav_auth_inner = True
    else:
        dav_auth_inner = None

    if chosen is None:
        warns.append(
            "DAV multistatus did not include an HTTP 200 propstat entry for the resource"
        )
        dav_res = False
        return ParsedPropfind(None, warns, dav_res, dav_auth_inner)

    prop_elems = [pe for pe in chosen if local_name(pe.tag) == "prop"]
    if not prop_elems:
        warns.append(PARSE_PARTIAL_WARNING)
        return ParsedPropfind(None, warns, False, dav_auth_inner)

    prop = prop_elems[0]

    display_name: str | None = None
    etag_val: str | None = None
    last_modified: str | None = None
    content_length: int | None = None
    is_collection = False

    for node in prop:
        ln = local_name(node.tag).lower()
        if ln == "displayname":
            if node.text and node.text.strip():
                display_name = node.text.strip()
        elif ln == "getetag":
            if node.text and node.text.strip():
                etag_val = node.text.strip()
        elif ln == "getlastmodified":
            if node.text and node.text.strip():
                last_modified = node.text.strip()
        elif ln == "getcontentlength":
            txt = (node.text or "").strip()
            if txt.isdigit():
                content_length = int(txt)
            elif txt:
                try:
                    content_length = int(txt)
                except ValueError:
                    pass
        elif ln == "resourcetype":
            for sub in node:
                if local_name(sub.tag).lower() == "collection":
                    is_collection = True
                    break

    root_payload: dict[str, Any] = {
        "display_name": display_name,
        "is_collection": is_collection,
        "etag": etag_val,
        "last_modified": last_modified,
        "content_length": content_length,
    }

    # No properties may still be reachable; keep success but hint.
    if all(
        v is None
        for k, v in root_payload.items()
        if k != "is_collection"
    ):
        warns.append(PARSE_PARTIAL_WARNING)

    return ParsedPropfind(
        root_payload, warns, True, dav_auth_inner
    )


def run_webdav_connection_test(
    settings: Settings, ds_id: UUID
) -> tuple[dict[str, Any], int]:
    """Return payload dict + HTTP status for the REST layer (never leaks secrets).

    Writes ``last_connection_*`` whenever the row exists (including invalid
    configuration), except that missing rows propagate ``DataSourceNotFound``.
    """
    row = datasource_svc.fetch_data_source_row_internal(ds_id=ds_id)

    source_type_enum = SourceType(str(row["source_type"]).strip().upper())
    base_out: dict[str, Any] = {
        "data_source_id": str(row["id"]),
        "name": row["name"],
        "source_type": row["source_type"],
    }

    def persist(success: bool, msg: str) -> None:
        datasource_svc.update_last_connection_test_result(
            ds_id=ds_id,
            success=success,
            message=msg,
        )

    # --- LOCAL_FOLDER ---
    if source_type_enum == SourceType.LOCAL_FOLDER:
        payload = {
            "status": "error",
            "message": "LOCAL_FOLDER connection test is not supported yet",
            **base_out,
            "reachable": False,
            "auth_success": False,
            "root_accessible": False,
            "http_status": None,
        }
        persist(False, payload["message"])
        return payload, 400

    if source_type_enum not in WEBDAV_KINDS:
        msg = (
            f"Unsupported source_type {row['source_type']} for WebDAV connection test"
        )
        payload = {
            "status": "error",
            "message": msg,
            **base_out,
            "reachable": False,
            "auth_success": False,
            "root_accessible": False,
            "http_status": None,
        }
        persist(False, msg)
        return payload, 400

    # --- Credential / username configuration ---
    uname_raw = row.get("username")
    uname = (uname_raw or "").strip() if uname_raw is not None else ""
    enc_blob = row.get("credential_secret_enc")
    cred_present = (
        isinstance(enc_blob, str) and enc_blob.strip() != ""
    ) or (
        enc_blob is not None
        and not isinstance(enc_blob, str)
        and str(enc_blob).strip() != ""
    )

    if not uname or not cred_present:
        msg_cfg = "WebDAV username or credential is missing"
        payload = {
            "status": "error",
            "message": msg_cfg,
            **base_out,
            "reachable": False,
            "auth_success": False,
            "root_accessible": False,
        }
        persist(False, msg_cfg)
        return payload, 400

    try:
        password = decrypt_credential_token(settings, str(enc_blob).strip())
    except ValueError:
        msg_decrypt = "Failed to decrypt stored credential"
        payload = {
            "status": "error",
            "message": msg_decrypt,
            **base_out,
            "reachable": False,
            "auth_success": False,
            "root_accessible": False,
            "http_status": None,
        }
        persist(False, msg_decrypt)
        return payload, 400

    server_url = (row["server_url"] or "").strip()
    if not (
        server_url.startswith("http://") or server_url.startswith("https://")
    ):
        msg_url = "server_url must start with http:// or https://"
        payload = {
            "status": "error",
            "message": msg_url,
            **base_out,
            "reachable": False,
            "auth_success": False,
            "root_accessible": False,
            "http_status": None,
        }
        persist(False, msg_url)
        return payload, 400

    wr_row = row.get("webdav_root_path")
    webdav_root = ""
    if isinstance(wr_row, str):
        webdav_root = wr_row.strip()
    elif wr_row is not None:
        webdav_root = str(wr_row).strip()

    if source_type_enum in WEBDAV_KINDS and not webdav_root:
        msg_root = "webdav_root_path is required for WebDAV-based data sources"
        payload = {
            "status": "error",
            "message": msg_root,
            **base_out,
            "reachable": False,
            "auth_success": False,
            "root_accessible": False,
            "http_status": None,
            "server_url": server_url,
        }
        persist(False, msg_root)
        return payload, 400

    webdav_url = join_webdav_url(server_url, webdav_root)
    merged_out = {
        **base_out,
        "server_url": server_url,
        "webdav_root_path": webdav_root or None,
        "webdav_url": webdav_url,
    }

    outcome = run_propfind(
        webdav_url=webdav_url,
        username=uname,
        password=password,
        timeout_seconds=float(settings.webdav_timeout_seconds),
    )

    parsed = analyze_propfind_body(outcome.raw_body, outcome.http_status)

    warnings = list(parsed.warnings)
    root_info_payload = parsed.root_info

    auth_success = outcome.auth_success
    if parsed.dav_auth_ok is False:
        auth_success = False
    elif parsed.dav_auth_ok is True:
        auth_success = True

    root_accessible = outcome.root_accessible
    if parsed.dav_resource_ok is False:
        root_accessible = False
    elif parsed.dav_resource_ok is True:
        root_accessible = True

    reachable = outcome.reachable

    http_status = outcome.http_status
    response_ms = outcome.response_ms

    ok_status = (
        reachable
        and auth_success
        and root_accessible
        and http_status is not None
        and http_status in {200, 207}
    )

    outer_message: str
    outer_error: str | None = None

    if not reachable:
        outer_message = "Failed to connect to WebDAV server"
        outer_error = outcome.error_summary or outer_message
    elif not auth_success:
        outer_message = "WebDAV authentication failed"
        outer_error = outcome.error_summary or "HTTP 401/403 Unauthorized"
    elif http_status == 405:
        outer_message = "PROPFIND is not supported for this endpoint"
        outer_error = outcome.error_summary or "HTTP 405 Method Not Allowed"
    elif http_status == 404:
        outer_message = "WebDAV root path was not found"
        outer_error = outcome.error_summary or "HTTP 404 Not Found"
    elif http_status not in {200, 207}:
        outer_message = "Unexpected WebDAV response"
        outer_error = outcome.error_summary or (
            f"HTTP {http_status}" if http_status is not None else "Unknown HTTP status"
        )
    elif ok_status:
        outer_message = SUCCESS_MESSAGE

    elif not root_accessible:
        outer_message = "WebDAV root path is not accessible"
        outer_error = outcome.error_summary or outer_message

    else:
        outer_message = "WebDAV connection test failed"
        outer_error = outcome.error_summary

    persist(ok_status, SUCCESS_MESSAGE if ok_status else outer_message)

    resp: dict[str, Any] = {
        "status": "ok" if ok_status else "error",
        **merged_out,
        "reachable": reachable,
        "auth_success": auth_success,
        "root_accessible": root_accessible,
        "http_status": http_status,
        "response_ms": response_ms,
        "message": outer_message,
    }

    if root_info_payload is not None:
        resp["root_info"] = root_info_payload

    if warnings:
        resp["warnings"] = warnings

    if not ok_status and outer_error:
        resp["error"] = outer_error

    return resp, 200
