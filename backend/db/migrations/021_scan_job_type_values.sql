-- 021: Extend scan_job_type enum, optionally extend scan_failures error_code enum.
--
-- Apply after your baseline schema that defines scan_jobs / scan_failures exists.
-- This repo does not ship earlier DDL for those tables; operators run this against
-- the real DB that already has scan_job_type (and possibly an error_code enum).
--
-- Policy (application layer matches this):
-- - Existing scan_jobs rows are NOT backfilled; old rows may stay MANUAL_SCAN.
-- - New runs record granular job_type only after this migration is applied; if the
--   enum lacks a value, create_scan_job fails best-effort (returns NULL) and the
--   sync/pipeline still completes.
-- - Past job kinds cannot be inferred from scan_jobs alone without correlating
--   action_logs by time window.
--
-- Apply (example):
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f db/migrations/021_scan_job_type_values.sql

-- ---------------------------------------------------------------------------
-- scan_job_type: add granular pipeline labels (MANUAL_SCAN remains).
-- Idempotent for PostgreSQL versions without ADD VALUE IF NOT EXISTS.
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'scan_job_type') THEN
        IF NOT EXISTS (
            SELECT 1 FROM pg_enum e
            JOIN pg_type t ON t.oid = e.enumtypid
            WHERE t.typname = 'scan_job_type' AND e.enumlabel = 'WEBDAV_SYNC_ROOT'
        ) THEN
            ALTER TYPE scan_job_type ADD VALUE 'WEBDAV_SYNC_ROOT';
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM pg_enum e
            JOIN pg_type t ON t.oid = e.enumtypid
            WHERE t.typname = 'scan_job_type' AND e.enumlabel = 'WEBDAV_SYNC_TREE'
        ) THEN
            ALTER TYPE scan_job_type ADD VALUE 'WEBDAV_SYNC_TREE';
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM pg_enum e
            JOIN pg_type t ON t.oid = e.enumtypid
            WHERE t.typname = 'scan_job_type' AND e.enumlabel = 'PROCESS_PENDING_TEXT'
        ) THEN
            ALTER TYPE scan_job_type ADD VALUE 'PROCESS_PENDING_TEXT';
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM pg_enum e
            JOIN pg_type t ON t.oid = e.enumtypid
            WHERE t.typname = 'scan_job_type' AND e.enumlabel = 'PROCESS_PENDING_DOCUMENTS'
        ) THEN
            ALTER TYPE scan_job_type ADD VALUE 'PROCESS_PENDING_DOCUMENTS';
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM pg_enum e
            JOIN pg_type t ON t.oid = e.enumtypid
            WHERE t.typname = 'scan_job_type' AND e.enumlabel = 'CHUNK_COMPLETED_TEXT'
        ) THEN
            ALTER TYPE scan_job_type ADD VALUE 'CHUNK_COMPLETED_TEXT';
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM pg_enum e
            JOIN pg_type t ON t.oid = e.enumtypid
            WHERE t.typname = 'scan_job_type' AND e.enumlabel = 'EMBED_PENDING_CHUNKS'
        ) THEN
            ALTER TYPE scan_job_type ADD VALUE 'EMBED_PENDING_CHUNKS';
        END IF;
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- scan_failures.error_code: if implemented as enum scan_failure_error_code,
-- add CHUNK_SAVE_FAILED. If error_code is VARCHAR, this block is a no-op.
-- Other enum names are not altered here; extend manually if your schema differs.
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'scan_failure_error_code') THEN
        IF NOT EXISTS (
            SELECT 1 FROM pg_enum e
            JOIN pg_type t ON t.oid = e.enumtypid
            WHERE t.typname = 'scan_failure_error_code' AND e.enumlabel = 'CHUNK_SAVE_FAILED'
        ) THEN
            ALTER TYPE scan_failure_error_code ADD VALUE 'CHUNK_SAVE_FAILED';
        END IF;
    END IF;
END $$;
