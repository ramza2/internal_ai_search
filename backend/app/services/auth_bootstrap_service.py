"""Bootstrap initial ``ADMIN`` user when the database has none (Step 19).

Runs once at application startup. If ``app_users`` is missing, the DB
is unreachable, or ``INITIAL_ADMIN_PASSWORD`` is empty, the function
logs a warning and returns without crashing the process.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

import psycopg
from psycopg import errors as pg_errors
from psycopg.rows import dict_row

from app.core.config import settings
from app.core.password import hash_password
from app.db.database import get_db_connection

logger = logging.getLogger(__name__)

_COUNT_ADMIN_SQL = """
    SELECT COUNT(*)::int AS c
    FROM app_users
    WHERE role::text = 'ADMIN'
"""

_INSERT_ADMIN_SQL = """
    INSERT INTO app_users (
        id,
        login_id,
        password_hash,
        name,
        email,
        department,
        role,
        status,
        must_change_password,
        last_login_at,
        created_at,
        updated_at
    ) VALUES (
        %s,
        %s,
        %s,
        %s,
        %s,
        %s,
        'ADMIN'::user_role,
        'ACTIVE'::user_status,
        TRUE,
        NULL,
        NOW(),
        NOW()
    )
"""


def ensure_initial_admin() -> None:
    """Create the first ``ADMIN`` from env when no admin row exists."""
    pwd = (settings.initial_admin_password or "").strip()
    if not pwd:
        logger.warning(
            "Skipping initial admin bootstrap: INITIAL_ADMIN_PASSWORD is empty"
        )
        return

    try:
        with get_db_connection() as conn:
            conn.row_factory = dict_row
            with conn.cursor() as cur:
                cur.execute(_COUNT_ADMIN_SQL)
                row = cur.fetchone()
                count = int(row["c"]) if row else 0
                if count > 0:
                    return

                uid = uuid.uuid4()
                ph = hash_password(pwd)
                cur.execute(
                    _INSERT_ADMIN_SQL,
                    (
                        uid,
                        settings.initial_admin_login_id.strip(),
                        ph,
                        settings.initial_admin_name.strip(),
                        settings.initial_admin_email.strip(),
                        settings.initial_admin_department.strip(),
                    ),
                )
            conn.commit()
        logger.info(
            "Initial admin user created (login_id=%s, must_change_password=true)",
            settings.initial_admin_login_id,
        )
    except pg_errors.UndefinedTable as exc:
        logger.warning(
            "Initial admin bootstrap skipped: app_users table missing (%s)",
            exc.diag.message_primary if exc.diag else str(exc),
        )
    except pg_errors.UniqueViolation:
        logger.warning(
            "Initial admin bootstrap skipped: login_id already exists (race?)"
        )
    except psycopg.Error as exc:
        logger.warning(
            "Initial admin bootstrap failed (non-fatal): %s",
            type(exc).__name__,
            exc_info=False,
        )
    except Exception as exc:  # pragma: no cover - bcrypt / unexpected
        logger.warning(
            "Initial admin bootstrap failed (non-fatal): %s",
            type(exc).__name__,
            exc_info=True,
        )


__all__ = ["ensure_initial_admin"]
