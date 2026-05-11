"""WebDAV PROPFIND Depth:1 root listing (preview only; no files table writes)."""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from datetime import timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import unquote, urlparse
from uuid import UUID

from app.core.config import Settings
from app.core.security import decrypt_credential_token
from app.schemas.data_source import WEBDAV_KINDS, SourceType
from app.services import data_source_service as datasource_svc
from app.webdav.client import join_webdav_url, run_propfind
from app.webdav.connection_test import local_name


SUCCESS_MESSAGE = "WebDAV root listing succeeded"

_HIDDEN_EXACT = frozenset({".git", ".svn", ".env", ".idea", ".vscode"})


def normalize_path(path: str) -> str:
    p = (path or "").strip()
    if not p:
        return "/"
    if not p.startswith("/"):
        p = "/" + p
    if len(p) > 1:
        p = p.rstrip("/")
    return p


def href_to_absolute_path(href: str, webdav_url: str) -> str:
    h = (href or "").strip()
    if not h:
        return ""
    if h.startswith(("http://", "https://")):
        path = urlparse(h).path
    else:
        path = h.split("?")[0].split("#")[0]
        if not path.startswith("/"):
            base = urlparse(webdav_url).path.rstrip("/") + "/"
            path = base + path.lstrip("/")
    return unquote(path or "/")


def to_iso_maybe(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    try:
        dt = parsedate_to_datetime(s)
        if dt is None:
            return s
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    except (TypeError, ValueError, OSError):
        return s


def is_hidden_entry(name: str, include_hidden: bool) -> bool:
    if include_hidden:
        return False
    if not name or name in (".", ".."):
        return True
    if name.lower() in _HIDDEN_EXACT:
        return True
    if name.startswith("."):
        return True
    return False


def _choose_propstat(response_el: ET.Element) -> ET.Element | None:
    propstats = [ps for ps in response_el if local_name(ps.tag) == "propstat"]
    chosen: ET.Element | None = None
    for ps in propstats:
        status_elements = [
            se for se in ps if local_name(se.tag) == "status"
        ]
        combo = " ".join(
            (se.text or "").strip() for se in status_elements if se.text
        ).lower()
        if "401" in combo or "403" in combo or "forbidden" in combo:
            continue
        if "200" in combo:
            chosen = ps
            break
    return chosen


def _extract_props(prop: ET.Element) -> dict[str, Any]:
    display_name = ""
    etag_val = ""
    last_modified = ""
    content_length: int | None = None
    content_type = ""
    is_collection = False
    for node in prop:
        ln = local_name(node.tag).lower()
        if ln == "displayname" and node.text and node.text.strip():
            display_name = node.text.strip()
        elif ln == "getetag" and node.text and node.text.strip():
            etag_val = node.text.strip()
        elif ln == "getlastmodified" and node.text and node.text.strip():
            last_modified = node.text.strip()
        elif ln == "getcontentlength":
            txt = (node.text or "").strip()
            if txt.isdigit():
                content_length = int(txt)
            elif txt:
                try:
                    content_length = int(float(txt))
                except ValueError:
                    pass
        elif ln == "getcontenttype" and node.text and node.text.strip():
            content_type = node.text.strip()
        elif ln == "resourcetype":
            for sub in node:
                if local_name(sub.tag).lower() == "collection":
                    is_collection = True
                    break
    return {
        "display_name": display_name,
        "etag": etag_val,
        "last_modified_raw": last_modified,
        "content_length": content_length,
        "content_type": content_type,
        "is_collection": is_collection,
    }


def parse_depth1_items(
    raw: bytes,
    *,
    webdav_url: str,
    http_status: int | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    items: list[dict[str, Any]] = []
    if http_status not in {200, 207}:
        return items, warnings

    if not raw.strip():
        warnings.append("Empty WebDAV response body")
        return items, warnings

    try:
        tree = ET.fromstring(raw)
    except ET.ParseError:
        warnings.append("Failed to parse WebDAV XML response")
        return items, warnings

    multistatus = None
    for el in tree.iter():
        if local_name(el.tag) == "multistatus":
            multistatus = el
            break
    if multistatus is None:
        warnings.append("WebDAV XML did not contain multistatus")
        return items, warnings

    root_path = normalize_path(
        href_to_absolute_path(urlparse(webdav_url).path or "/", webdav_url)
    )

    responses = [c for c in multistatus if local_name(c.tag) == "response"]
    for resp in responses:
        href_elems = [c for c in resp if local_name(c.tag) == "href"]
        if not href_elems or not (href_elems[0].text or "").strip():
            continue
        href_raw = (href_elems[0].text or "").strip()
        abs_path = normalize_path(href_to_absolute_path(href_raw, webdav_url))

        if abs_path == root_path:
            continue

        chosen = _choose_propstat(resp)
        if chosen is None:
            continue

        prop_elems = [pe for pe in chosen if local_name(pe.tag) == "prop"]
        if not prop_elems:
            continue
        props = _extract_props(prop_elems[0])

        root_prefix = root_path + "/"
        if not abs_path.startswith(root_prefix):
            continue
        remainder = abs_path[len(root_prefix) :]
        remainder = remainder.rstrip("/")
        if "/" in remainder or not remainder:
            continue

        disp = props["display_name"]
        name = disp if disp else remainder
        remote_path = "/" + remainder

        is_dir = bool(props["is_collection"])
        etag = props["etag"] or None

        lm_raw = props["last_modified_raw"]
        last_mod: str | None
        if lm_raw:
            conv = to_iso_maybe(lm_raw)
            last_mod = conv if conv else None
        else:
            last_mod = None

        if is_dir:
            href_out = abs_path.rstrip("/") + "/"
            size_bytes = None
            etag_out = None
            ct_out = None
        else:
            href_out = abs_path.rstrip("/")
            size_bytes = props["content_length"]
            etag_out = etag
            ctype = props["content_type"]
            ct_out = ctype if ctype else None

        extension: str | None = None
        if not is_dir:
            bn = os.path.basename(name)
            if "." in bn:
                _, ext_part = bn.rsplit(".", 1)
                if ext_part:
                    extension = ext_part.lower()

        items.append(
            {
                "name": name,
                "remote_path": remote_path,
                "href": href_out,
                "is_directory": is_dir,
                "extension": extension,
                "size_bytes": size_bytes,
                "etag": etag_out,
                "last_modified": last_mod,
                "content_type": ct_out,
            }
        )

    items.sort(key=lambda x: (str(x["name"]).casefold(), x["remote_path"]))
    return items, warnings


def run_webdav_root_listing(
    settings: Settings,
    ds_id: UUID,
    *,
    limit: int,
    include_hidden: bool,
) -> tuple[dict[str, Any], int]:
    row = datasource_svc.fetch_data_source_row_internal(ds_id=ds_id)
    source_type_enum = SourceType(str(row["source_type"]).strip().upper())
    base_out: dict[str, Any] = {
        "data_source_id": str(row["id"]),
        "name": row["name"],
        "source_type": row["source_type"],
    }

    def persist(success: bool, msg: str) -> None:
        datasource_svc.update_last_connection_test_result(
            ds_id=ds_id, success=success, message=(msg or "").strip()
        )

    if source_type_enum == SourceType.LOCAL_FOLDER:
        payload: dict[str, Any] = {
            "status": "error",
            **base_out,
            "items": [],
            "message": "LOCAL_FOLDER listing is not supported yet",
        }
        persist(False, payload["message"])
        return payload, 400

    if source_type_enum not in WEBDAV_KINDS:
        msg = (
            f"Unsupported source_type {row['source_type']} for WebDAV listing"
        )
        payload = {
            "status": "error",
            **base_out,
            "items": [],
            "message": msg,
        }
        persist(False, msg)
        return payload, 400

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
            **base_out,
            "items": [],
            "message": msg_cfg,
        }
        persist(False, msg_cfg)
        return payload, 400

    try:
        password = decrypt_credential_token(settings, str(enc_blob).strip())
    except ValueError:
        msg_decrypt = "Failed to decrypt stored credential"
        payload = {
            "status": "error",
            **base_out,
            "items": [],
            "message": msg_decrypt,
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
            **base_out,
            "items": [],
            "message": msg_url,
        }
        persist(False, msg_url)
        return payload, 400

    wr_row = row.get("webdav_root_path")
    webdav_root = ""
    if isinstance(wr_row, str):
        webdav_root = wr_row.strip()
    elif wr_row is not None:
        webdav_root = str(wr_row).strip()

    if not webdav_root:
        msg_root = "webdav_root_path is required for WebDAV-based data sources"
        payload = {
            "status": "error",
            **base_out,
            "items": [],
            "message": msg_root,
            "server_url": server_url,
        }
        persist(False, msg_root)
        return payload, 400

    webdav_url = join_webdav_url(server_url, webdav_root)
    merged_out: dict[str, Any] = {
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
        depth="1",
    )

    http_status = outcome.http_status
    response_ms = outcome.response_ms

    if not outcome.reachable:
        msg = "Failed to connect to WebDAV server"
        err = outcome.error_summary or msg
        payload = {
            "status": "error",
            **merged_out,
            "http_status": http_status,
            "response_ms": response_ms,
            "items": [],
            "message": msg,
            "error": err,
        }
        persist(False, msg)
        return payload, 200

    if not outcome.auth_success:
        payload = {
            "status": "error",
            **merged_out,
            "http_status": http_status,
            "response_ms": response_ms,
            "items": [],
            "message": "WebDAV authentication failed",
            "error": outcome.error_summary or "HTTP 401 Unauthorized",
        }
        persist(False, payload["message"])
        return payload, 200

    if http_status == 404:
        payload = {
            "status": "error",
            **merged_out,
            "http_status": 404,
            "response_ms": response_ms,
            "items": [],
            "message": "WebDAV root path not found",
            "error": outcome.error_summary or "HTTP 404 Not Found",
        }
        persist(False, payload["message"])
        return payload, 200

    if http_status == 405:
        payload = {
            "status": "error",
            **merged_out,
            "http_status": http_status,
            "response_ms": response_ms,
            "items": [],
            "message": "PROPFIND is not supported for this endpoint",
            "error": outcome.error_summary or "HTTP 405 Method Not Allowed",
        }
        persist(False, payload["message"])
        return payload, 200

    if http_status not in {200, 207}:
        payload = {
            "status": "error",
            **merged_out,
            "http_status": http_status,
            "response_ms": response_ms,
            "items": [],
            "message": "Unexpected WebDAV response",
            "error": outcome.error_summary or f"HTTP {http_status}",
        }
        persist(False, payload["message"])
        return payload, 200

    parsed_items, parse_warnings = parse_depth1_items(
        outcome.raw_body, webdav_url=webdav_url, http_status=http_status
    )

    filtered: list[dict[str, Any]] = []
    for it in parsed_items:
        if is_hidden_entry(str(it["name"]), include_hidden):
            continue
        filtered.append(it)

    effective_limit = max(1, min(int(limit), 5000))
    total_items = len(filtered)
    truncated = total_items > effective_limit
    slice_items = filtered[:effective_limit]
    returned_items = len(slice_items)
    folders = sum(1 for x in slice_items if x["is_directory"])
    files = returned_items - folders

    warnings_out: list[str] = list(parse_warnings)
    if truncated:
        warnings_out.append(f"Result was truncated by limit={effective_limit}")

    ok_payload: dict[str, Any] = {
        "status": "ok",
        **merged_out,
        "http_status": http_status,
        "response_ms": response_ms,
        "total_items": total_items,
        "returned_items": returned_items,
        "truncated": truncated,
        "folders": folders,
        "files": files,
        "items": slice_items,
        "message": SUCCESS_MESSAGE,
    }
    if warnings_out:
        ok_payload["warnings"] = warnings_out

    persist(True, SUCCESS_MESSAGE)
    return ok_payload, 200
