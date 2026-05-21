"""One-off: export schema-only DDL to docker/db/schema/baseline_schema.sql (dev maintainer tool)."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "docker" / "db" / "schema" / "baseline_schema.sql"
ENV = REPO / "backend" / ".env"


def _load_env() -> None:
    if not ENV.is_file():
        raise SystemExit(f"missing {ENV}")
    for line in ENV.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s and not s.startswith("#") and "=" in s:
            k, v = s.split("=", 1)
            os.environ.setdefault(k, v)


def main() -> int:
    _load_env()
    host = os.environ.get("SCHEMA_DUMP_HOST", "host.docker.internal")
    port = os.environ.get("DB_PORT", "5433")
    env = os.environ.copy()
    env["PGPASSWORD"] = os.environ["DB_PASSWORD"]
    cmd = [
        "docker",
        "run",
        "--rm",
        "-e",
        f"PGPASSWORD={env['PGPASSWORD']}",
        "postgres:18",
        "pg_dump",
        "-h",
        host,
        "-p",
        port,
        "-U",
        os.environ["DB_USER"],
        "-d",
        os.environ["DB_NAME"],
        "--schema-only",
        "--no-owner",
        "--no-acl",
        "--no-comments",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        return proc.returncode
    header = (
        "-- internal-ai-search baseline schema (DDL only, no data, no comments).\n"
        "-- Applied once on empty DB by scripts/apply_migrations.py.\n\n"
    )
    OUT.write_text(header + proc.stdout, encoding="utf-8", newline="\n")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
