-- 023: Add PIPELINE to scan_job_type enum (server-driven parent pipeline jobs).
--
-- Idempotent: skips when enum or label already exists (PostgreSQL without IF NOT EXISTS on ADD VALUE).
--
-- Apply (example):
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f db/migrations/023_scan_job_type_pipeline.sql

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'scan_job_type') THEN
        IF NOT EXISTS (
            SELECT 1 FROM pg_enum e
            JOIN pg_type t ON t.oid = e.enumtypid
            WHERE t.typname = 'scan_job_type' AND e.enumlabel = 'PIPELINE'
        ) THEN
            ALTER TYPE scan_job_type ADD VALUE 'PIPELINE';
        END IF;
    END IF;
END $$;
