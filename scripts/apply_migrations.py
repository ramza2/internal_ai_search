#!/usr/bin/env python3
"""
Apply baseline schema + incremental migrations to an empty/dev PostgreSQL database.

Used by docker-compose ``db-migrate`` service. Idempotent migrations (019+) are safe
to re-run; baseline runs only when ``data_sources`` table is missing.

Environment: DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD (same as backend).
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import psycopg

REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE = REPO_ROOT / "docker" / "db" / "schema" / "baseline_schema.sql"
MIGRATIONS_DIR = REPO_ROOT / "backend" / "db" / "migrations"


def _db_params() -> dict[str, str | int]:
    return {
        "host": os.environ.get("DB_HOST", "localhost"),
        "port": int(os.environ.get("DB_PORT", "5432")),
        "dbname": os.environ.get("DB_NAME", "internal_ai_search"),
        "user": os.environ.get("DB_USER", "openlink"),
        "password": os.environ.get("DB_PASSWORD", ""),
    }


def _wait_db(*, attempts: int = 60, delay: float = 2.0) -> None:
    last: Exception | None = None
    for i in range(attempts):
        try:
            with psycopg.connect(**_db_params(), connect_timeout=5) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
            print(f"[db-migrate] database ready (attempt {i + 1})")
            return
        except Exception as exc:
            last = exc
            print(f"[db-migrate] waiting for database: {exc}")
            time.sleep(delay)
    raise SystemExit(f"[db-migrate] database not ready: {last}") from last


def _table_exists(conn: psycopg.Connection, name: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = %s
            )
            """,
            (name,),
        )
        row = cur.fetchone()
    return bool(row and row[0])


def _run_sql_file(path: Path) -> None:
    print(f"[db-migrate] applying {path.relative_to(REPO_ROOT)}")
    p = _db_params()
    env = os.environ.copy()
    env["PGPASSWORD"] = str(p["password"])
    proc = subprocess.run(
        [
            "psql",
            "-h",
            str(p["host"]),
            "-p",
            str(p["port"]),
            "-U",
            str(p["user"]),
            "-d",
            str(p["dbname"]),
            "-v",
            "ON_ERROR_STOP=1",
            "-f",
            str(path),
        ],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()[:2000]
        raise RuntimeError(f"psql failed for {path.name}: {err}")


def main() -> int:
    if not BASELINE.is_file():
        print(f"[db-migrate] missing baseline: {BASELINE}", file=sys.stderr)
        return 1

    _wait_db()

    with psycopg.connect(**_db_params()) as conn:
        baseline_needed = not _table_exists(conn, "data_sources")

    if baseline_needed:
        _run_sql_file(BASELINE)
    else:
        print("[db-migrate] baseline skipped (data_sources already exists)")

    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    for mf in migration_files:
        _run_sql_file(mf)

    print("[db-migrate] done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
