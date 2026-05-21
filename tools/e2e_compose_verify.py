#!/usr/bin/env python3
"""Compose DB E2E verification helper (no secrets in stdout)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
ENV_PATH = REPO / "backend" / ".env"
BASE = os.environ.get("E2E_BASE_URL", "http://localhost:8000")


def _load_env() -> None:
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s and not s.startswith("#") and "=" in s:
            k, v = s.split("=", 1)
            os.environ.setdefault(k, v)


def _api(
    method: str,
    path: str,
    *,
    token: str | None = None,
    body: dict | None = None,
    timeout: float = 120.0,
) -> tuple[int, Any, str | None]:
    url = f"{BASE.rstrip('/')}{path}"
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return resp.status, json.loads(raw) if raw.strip() else None, None
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw) if raw.strip() else None
        except json.JSONDecodeError:
            parsed = None
        msg = None
        if isinstance(parsed, dict):
            msg = str(parsed.get("message") or parsed.get("detail") or "")
        return exc.code, parsed, msg or f"HTTP {exc.code}"


def _login() -> str:
    lid = os.environ.get("INITIAL_ADMIN_LOGIN_ID", "admin")
    pwd = os.environ.get("E2E_ADMIN_PASSWORD") or os.environ.get("INITIAL_ADMIN_PASSWORD", "")
    if not pwd or pwd == "CHANGE_ME":
        raise RuntimeError("Set INITIAL_ADMIN_PASSWORD or E2E_ADMIN_PASSWORD in backend/.env")
    status, data, err = _api(
        "POST",
        "/api/auth/login",
        body={"login_id": lid, "password": pwd},
    )
    if status != 200 or not isinstance(data, dict):
        raise RuntimeError(f"login failed: {err}")
    token = data.get("access_token") or data.get("token")
    if not token:
        raise RuntimeError("login response missing token")
    return str(token)


def _change_password_if_required(token: str) -> None:
    status, me, _ = _api("GET", "/api/auth/me", token=token)
    if status != 200 or not isinstance(me, dict):
        return
    u = me.get("user") if isinstance(me.get("user"), dict) else me
    if not u.get("must_change_password"):
        return
    cur = os.environ.get("INITIAL_ADMIN_PASSWORD", "")
    new_pwd = os.environ.get("E2E_ADMIN_PASSWORD") or os.environ.get("E2E_ADMIN_PASSWORD_NEW")
    if not new_pwd or new_pwd == cur:
        raise RuntimeError(
            "must_change_password=true — set E2E_ADMIN_PASSWORD in backend/.env (gitignored) "
            "to a password meeting PASSWORD_MIN_LENGTH, then re-run"
        )
    st, _, err = _api(
        "POST",
        "/api/auth/change-password",
        token=token,
        body={"current_password": cur, "new_password": new_pwd},
    )
    if st != 200:
        raise RuntimeError(f"change-password failed: {err}")
    os.environ["E2E_ADMIN_PASSWORD"] = new_pwd
    return _login_with(os.environ.get("INITIAL_ADMIN_LOGIN_ID", "admin"), new_pwd)


def _login_with(login_id: str, password: str) -> str:
    status, data, err = _api(
        "POST",
        "/api/auth/login",
        body={"login_id": login_id, "password": password},
    )
    if status != 200:
        raise RuntimeError(err or "login failed")
    return str(data.get("access_token") or data.get("token"))


def _psql_query(host: str, port: str, sql: str) -> list[tuple]:
    """Run SQL via docker compose db (compose) or psycopg if installed (legacy host)."""
    compose_host = os.environ.get("E2E_COMPOSE_DB_HOST", "localhost")
    compose_port = os.environ.get("DB_PUBLISH_PORT") or os.environ.get("E2E_COMPOSE_DB_PORT", "5434")
    if host in (compose_host, "localhost", "127.0.0.1") and str(port) == str(compose_port):
        return _psql_via_compose(sql)
    try:
        import psycopg

        conn = psycopg.connect(
            host=host,
            port=int(port),
            dbname=os.environ["DB_NAME"],
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
        )
        cur = conn.cursor()
        cur.execute(sql)
        rows = cur.fetchall()
        conn.close()
        return rows
    except ImportError:
        return _psql_via_host(host, port, sql)


def _psql_via_compose(sql: str) -> list[tuple]:
    cmd = [
        "docker",
        "compose",
        "--env-file",
        str(ENV_PATH),
        "-f",
        str(REPO / "docker-compose.dev.yml"),
        "exec",
        "-T",
        "db",
        "psql",
        "-U",
        os.environ.get("DB_USER", "openlink"),
        "-d",
        os.environ.get("DB_NAME", "internal_ai_search"),
        "-t",
        "-A",
        "-F",
        "\t",
        "-c",
        sql,
    ]
    proc = subprocess.run(
        cmd, capture_output=True, text=True, cwd=REPO, timeout=60, encoding="utf-8", errors="replace"
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "psql failed")
    rows: list[tuple] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        rows.append(tuple(parts))
    return rows


def _psql_via_host(host: str, port: str, sql: str) -> list[tuple]:
    env = os.environ.copy()
    env["PGPASSWORD"] = env.get("DB_PASSWORD", "")
    cmd = [
        "psql",
        "-h",
        host,
        "-p",
        str(port),
        "-U",
        env.get("DB_USER", "openlink"),
        "-d",
        env.get("DB_NAME", "internal_ai_search"),
        "-t",
        "-A",
        "-F",
        "\t",
        "-c",
        sql,
    ]
    proc = subprocess.run(
        cmd, capture_output=True, text=True, env=env, timeout=60, encoding="utf-8", errors="replace"
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "psql failed")
    rows: list[tuple] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(tuple(line.split("\t")))
    return rows


def _psql_legacy(sql: str) -> list[tuple]:
    container = os.environ.get("E2E_LEGACY_DB_CONTAINER", "internal-ai-search-db")
    cmd = [
        "docker",
        "exec",
        "-i",
        container,
        "psql",
        "-U",
        os.environ.get("DB_USER", "openlink"),
        "-d",
        os.environ.get("DB_NAME", "internal_ai_search"),
        "-t",
        "-A",
        "-F",
        "\t",
        "-c",
        sql,
    ]
    proc = subprocess.run(
        cmd, capture_output=True, text=True, timeout=60, encoding="utf-8", errors="replace"
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "legacy psql failed")
    rows: list[tuple] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line:
            rows.append(tuple(line.split("\t")))
    return rows


def _import_data_source_from_legacy(token: str) -> str | None:
    """Copy data_sources row from legacy host DB (5433) if reachable — no credential in output."""
    sql = """
            SELECT name, source_type::text, server_url, webdav_root_path, username,
                   credential_secret_enc, description, is_active
            FROM data_sources
            WHERE is_active = true
            ORDER BY created_at
            LIMIT 1
            """
    try:
        rows = _psql_legacy(sql)
    except Exception:
        legacy_host = os.environ.get("E2E_LEGACY_DB_HOST", "localhost")
        legacy_port = os.environ.get("E2E_LEGACY_DB_PORT", "5433")
        try:
            rows = _psql_query(legacy_host, legacy_port, sql)
        except Exception:
            return None
    if not rows:
        return None
    name, st, url, root, user, enc, desc, active = rows[0]
    if not enc:
        return None
    # Decrypt and re-register via API (Fernet round-trip in backend)
    sys.path.insert(0, str(REPO / "backend"))
    from app.core.config import Settings
    from app.core.security import decrypt_credential_token

    settings = Settings()
    try:
        plain = decrypt_credential_token(settings, str(enc))
    except Exception:
        return None
    body = {
        "name": f"{name} (compose-e2e)",
        "source_type": st,
        "server_url": url,
        "webdav_root_path": root,
        "username": user,
        "credential_secret": plain,
        "description": desc or "WebDAV 테스트 저장소 (compose E2E)",
        "is_active": bool(active),
    }
    status, data, err = _api("POST", "/api/data-sources", token=token, body=body)
    if status not in (200, 201) or not isinstance(data, dict):
        print(f"[e2e] data source create failed: {err}", file=sys.stderr)
        return None
    if isinstance(data, dict) and data.get("id"):
        return str(data["id"])
    return None


def main() -> int:
    _load_env()
    out: dict[str, Any] = {"base_url": BASE}

    # health
    health: dict[str, bool] = {}
    for p in ("/health", "/health/db", "/health/llm", "/health/embedding", "/health/vector-db"):
        t = 90.0 if "embedding" in p else 30.0
        st, data, _ = _api("GET", p, timeout=t)
        ok = st == 200 and isinstance(data, dict) and (
            data.get("status") == "ok"
            or (p == "/health/db" and (data.get("db") or {}).get("ok"))
            or (p == "/health/llm" and data.get("ollama_reachable"))
        )
        health[p] = ok
    out["health"] = health

    token = _login()
    try:
        token = _change_password_if_required(token) or token
    except Exception as exc:
        out["change_password_error"] = str(exc)

    st, me, _ = _api("GET", "/api/auth/me", token=token)
    if isinstance(me, dict):
        u = me.get("user") if isinstance(me.get("user"), dict) else me
        out["admin_me"] = {
            "login_id": u.get("login_id"),
            "role": u.get("role"),
            "status": u.get("status"),
            "must_change_password": u.get("must_change_password"),
        }

    compose_port = os.environ.get("DB_PUBLISH_PORT") or os.environ.get("E2E_COMPOSE_DB_PORT", "5434")
    rows = _psql_query(os.environ.get("E2E_COMPOSE_DB_HOST", "localhost"), compose_port, """
        SELECT login_id, role::text, status::text, must_change_password, created_at IS NOT NULL
        FROM app_users ORDER BY created_at
    """)
    out["app_users"] = [
        {"login_id": r[0], "role": r[1], "status": r[2], "must_change_password": r[3]}
        for r in rows
    ]

    ds_id = _import_data_source_from_legacy(token)
    out["data_source_id"] = ds_id
    if not ds_id:
        print("[e2e] no data source — register WebDAV manually or keep legacy DB on 5433 for import", file=sys.stderr)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 2

    st, tc, err = _api("POST", f"/api/data-sources/{ds_id}/test-connection", token=token, timeout=60)
    out["test_connection"] = {"ok": st == 200, "status": st, "error": err}

    # LIMITED sync-tree via admin enqueue (worker needed) — use LIMITED for faster E2E
    body = {
        "data_source_id": ds_id,
        "scan_scope": "LIMITED",
        "start_path": "/",
        "max_depth": 3,
        "max_items": 500,
        "include_hidden": False,
        "apply_exclusions": True,
        "detect_deleted": False,
        "priority": 10,
    }
    st, enq, err = _api("POST", "/api/admin/jobs/sync-tree", token=token, body=body)
    job_id = None
    if isinstance(enq, dict):
        job_id = enq.get("job_id")
    out["sync_tree_enqueue"] = {"ok": st == 200 and job_id is not None, "job_id": job_id, "scan_scope": "LIMITED"}

    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if all(health.values()) and ds_id else 1


if __name__ == "__main__":
    raise SystemExit(main())
