"""pgvector insert + cosine smoke test using a temporary table (no production data)."""

from __future__ import annotations

import re
from typing import Any

from psycopg import sql

from app.core.config import Settings
from app.db.database import get_db_connection
from app.embedding.ollama_embedding_client import create_embedding


def _format_vector_literal(vector: list[float]) -> str:
    """Build pgvector text input for use as a single bound parameter."""
    return "[" + ",".join(str(float(x)) for x in vector) + "]"


def _base_error_payload(settings: Settings) -> dict[str, Any]:
    return {
        "embedding_model": settings.embedding_model,
        "expected_dimension": settings.embedding_dimension,
        "generated_dimension": None,
        "db_insert_success": False,
        "db_vector_dimension": None,
        "dimension_matched": False,
        "similarity_search_success": False,
    }


def _gather_schema_check(cur: Any) -> dict[str, Any]:
    """
    Inspect pgvector extension and optional document_chunks schema.

    Never raises; uses warnings for unexpected issues.
    """
    out: dict[str, Any] = {
        "pgvector_enabled": False,
        "pgvector_version": None,
        "document_chunks_exists": False,
        "document_chunks_embedding_is_vector": False,
        "document_chunks_embedding_dimension": None,
        "warnings": [],
    }

    try:
        cur.execute(
            "SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'vector')"
        )
        row = cur.fetchone()
        out["pgvector_enabled"] = bool(row and row[0])
    except Exception as exc:  # pragma: no cover - defensive
        out["warnings"].append(f"pgvector extension check failed: {exc}")
        return out

    if out["pgvector_enabled"]:
        try:
            cur.execute(
                "SELECT extversion FROM pg_extension WHERE extname = 'vector' LIMIT 1"
            )
            vrow = cur.fetchone()
            if vrow and vrow[0] is not None:
                out["pgvector_version"] = str(vrow[0])
        except Exception as exc:
            out["warnings"].append(f"pgvector version query failed: {exc}")

    try:
        cur.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'document_chunks'
            )
            """
        )
        row = cur.fetchone()
        out["document_chunks_exists"] = bool(row and row[0])
    except Exception as exc:
        out["warnings"].append(f"document_chunks existence check failed: {exc}")
        return out

    if not out["document_chunks_exists"]:
        out["warnings"].append(
            "public.document_chunks not found; apply migrations when ready."
        )
        return out

    try:
        cur.execute(
            """
            SELECT pg_catalog.format_type(a.atttypid, a.atttypmod) AS coltype
            FROM pg_attribute a
            JOIN pg_class c ON c.oid = a.attrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public'
              AND c.relname = 'document_chunks'
              AND a.attname = 'embedding'
              AND NOT a.attisdropped
            """
        )
        trow = cur.fetchone()
        if trow and trow[0]:
            coltype = str(trow[0])
            out["document_chunks_embedding_is_vector"] = coltype.startswith(
                "vector"
            )
            m = re.search(r"vector\((\d+)\)", coltype)
            if m:
                out["document_chunks_embedding_dimension"] = int(m.group(1))
            elif coltype == "vector":
                out["document_chunks_embedding_dimension"] = None
                out["warnings"].append(
                    "document_chunks.embedding is vector without explicit dimension in typmod."
                )
        else:
            out["warnings"].append(
                "document_chunks exists but column embedding was not found."
            )
    except Exception as exc:
        out["warnings"].append(f"document_chunks.embedding column check failed: {exc}")

    return out


def check_vector_db_health(settings: Settings) -> dict[str, Any]:
    """
    Embedding -> temp pgvector table -> dimension check -> cosine-order search.

    Never raises; returns JSON-serializable dict for GET /health/vector-db.
    """
    expected = settings.embedding_dimension
    test_text = settings.embedding_test_text
    model = settings.embedding_model

    if (settings.embedding_provider or "").strip().lower() != "ollama":
        payload = _base_error_payload(settings)
        payload.update(
            {
                "status": "error",
                "message": "Unsupported embedding provider for vector-db smoke test",
                "error": f"Only 'ollama' is supported; got {settings.embedding_provider!r}",
                "schema_check": None,
            }
        )
        return payload

    emb = create_embedding(
        base_url=settings.ollama_base_url,
        model=model,
        text=test_text,
        timeout_seconds=settings.embedding_timeout_seconds,
    )

    if not emb.success or emb.vector is None:
        payload = _base_error_payload(settings)
        payload.update(
            {
                "status": "error",
                "message": "Failed to generate embedding",
                "error": emb.error or "Unknown embedding error",
                "schema_check": None,
            }
        )
        return payload

    generated = len(emb.vector)
    if generated != expected:
        payload = _base_error_payload(settings)
        payload["generated_dimension"] = generated
        payload.update(
            {
                "status": "error",
                "message": "Embedding dimension mismatch",
                "error": f"Expected {expected} dimensions, got {generated}",
                "schema_check": None,
            }
        )
        return payload

    vec_literal = _format_vector_literal(emb.vector)
    schema_check: dict[str, Any] | None = None

    try:
        with get_db_connection() as conn:
            conn.autocommit = False
            try:
                with conn.cursor() as cur:
                    schema_check = _gather_schema_check(cur)

                    create_stmt = sql.SQL(
                        "CREATE TEMP TABLE IF NOT EXISTS tmp_vector_health_check ( "
                        "id UUID PRIMARY KEY DEFAULT gen_random_uuid(), "
                        "content TEXT, "
                        "embedding vector({dim}) "
                        ") ON COMMIT DROP"
                    ).format(dim=sql.Literal(expected))
                    cur.execute(create_stmt)

                    cur.execute(
                        """
                        INSERT INTO tmp_vector_health_check (content, embedding)
                        VALUES (%s, %s::vector)
                        """,
                        (test_text, vec_literal),
                    )

                    db_dim: int | None = None
                    try:
                        cur.execute(
                            """
                            SELECT vector_dims(embedding)
                            FROM tmp_vector_health_check
                            LIMIT 1
                            """
                        )
                        drow = cur.fetchone()
                        if drow and drow[0] is not None:
                            db_dim = int(drow[0])
                    except Exception:
                        db_dim = generated

                    if db_dim is not None and db_dim != expected:
                        conn.rollback()
                        payload = _base_error_payload(settings)
                        payload["generated_dimension"] = generated
                        payload.update(
                            {
                                "status": "error",
                                "message": "Vector dimension in database does not match expected",
                                "error": f"Expected {expected} dimensions in pgvector, got {db_dim}",
                                "schema_check": schema_check,
                            }
                        )
                        return payload

                    cur.execute(
                        """
                        SELECT (1.0 - (embedding <=> %s::vector))::double precision
                        FROM tmp_vector_health_check
                        ORDER BY embedding <=> %s::vector ASC
                        LIMIT 1
                        """,
                        (vec_literal, vec_literal),
                    )
                    srow = cur.fetchone()
                    top_sim = float(srow[0]) if srow and srow[0] is not None else None

                    if top_sim is None or top_sim < 0.999:
                        conn.rollback()
                        payload = _base_error_payload(settings)
                        payload["generated_dimension"] = generated
                        payload["db_vector_dimension"] = db_dim
                        payload.update(
                            {
                                "status": "error",
                                "message": "Similarity search below expected threshold",
                                "error": (
                                    f"top_similarity={top_sim!r} "
                                    f"(expected >= 0.999 for identical query vector)"
                                ),
                                "schema_check": schema_check,
                                "top_similarity": top_sim,
                            }
                        )
                        return payload

                conn.commit()
            except Exception:
                conn.rollback()
                raise

    except Exception as exc:
        payload = _base_error_payload(settings)
        payload["generated_dimension"] = generated
        payload.update(
            {
                "status": "error",
                "message": "Failed to insert/search vector in pgvector",
                "error": str(exc),
                "schema_check": schema_check,
            }
        )
        return payload

    dim_match = db_dim == expected if db_dim is not None else False

    return {
        "status": "ok",
        "embedding_model": model,
        "expected_dimension": expected,
        "generated_dimension": generated,
        "db_insert_success": True,
        "db_vector_dimension": db_dim,
        "dimension_matched": dim_match,
        "similarity_search_success": True,
        "top_similarity": top_sim,
        "test_text": test_text,
        "message": "pgvector insert/search smoke test is healthy",
        "schema_check": schema_check,
    }
