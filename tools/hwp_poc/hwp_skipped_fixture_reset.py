"""Compose-dev only: reset skipped-baseline file to SKIPPED for only-mode HTTP E2E."""
from __future__ import annotations

from uuid import UUID

from app.db.database import get_db_connection

FIXTURE_FILE_ID = UUID("9f69bb54-b4a2-4c2e-914b-d95cc76bf3f4")


def main() -> int:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM document_chunks WHERE file_id = %s", (FIXTURE_FILE_ID,))
            cur.execute("DELETE FROM file_contents WHERE file_id = %s", (FIXTURE_FILE_ID,))
            cur.execute(
                """
                UPDATE files
                SET analysis_status = 'SKIPPED'::analysis_status,
                    analysis_error_code = 'NO_EXTRACTABLE_TEXT',
                    analysis_error_message = NULL
                WHERE id = %s AND lower(extension) = 'hwp'
                """,
                (FIXTURE_FILE_ID,),
            )
        conn.commit()
    print("fixture_reset_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
