-- 022: Worker-ready scan_jobs — enum extensions, columns, indexes.
-- PostgreSQL 18+ compatible. Safe when scan_jobs / scan_failures / enums are absent.
--
-- Priority semantics (application): larger integer = higher priority when dequeuing.
--
-- Large production databases: CREATE INDEX CONCURRENTLY cannot run inside a transaction;
-- this file uses plain CREATE INDEX IF NOT EXISTS for dev/small DBs. For huge tables,
-- consider running equivalent CONCURRENTLY indexes in a maintenance window separately.

-- ---------------------------------------------------------------------------
-- scan_job_status: worker lifecycle labels (existing RUNNING/COMPLETED/FAILED kept)
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'scan_job_status') THEN
        ALTER TYPE scan_job_status ADD VALUE IF NOT EXISTS 'PENDING';
        ALTER TYPE scan_job_status ADD VALUE IF NOT EXISTS 'CANCELLING';
        ALTER TYPE scan_job_status ADD VALUE IF NOT EXISTS 'CANCELLED';
        ALTER TYPE scan_job_status ADD VALUE IF NOT EXISTS 'PARTIAL';
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- scan_jobs columns (skip entire block if table missing)
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'scan_jobs'
    ) THEN
        ALTER TABLE scan_jobs ADD COLUMN IF NOT EXISTS requested_by UUID;
        ALTER TABLE scan_jobs ADD COLUMN IF NOT EXISTS job_params JSONB;
        ALTER TABLE scan_jobs ADD COLUMN IF NOT EXISTS cancel_requested BOOLEAN NOT NULL DEFAULT FALSE;
        ALTER TABLE scan_jobs ADD COLUMN IF NOT EXISTS worker_id VARCHAR(100);
        ALTER TABLE scan_jobs ADD COLUMN IF NOT EXISTS heartbeat_at TIMESTAMPTZ;
        ALTER TABLE scan_jobs ADD COLUMN IF NOT EXISTS parent_job_id UUID;
        ALTER TABLE scan_jobs ADD COLUMN IF NOT EXISTS pipeline_step VARCHAR(50);
        ALTER TABLE scan_jobs ADD COLUMN IF NOT EXISTS retry_count INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE scan_jobs ADD COLUMN IF NOT EXISTS max_retries INTEGER NOT NULL DEFAULT 1;
        ALTER TABLE scan_jobs ADD COLUMN IF NOT EXISTS priority INTEGER NOT NULL DEFAULT 0;
    END IF;
END $$;

-- FK parent_job_id → scan_jobs(id) intentionally omitted (self-reference / rollout safety).

-- ---------------------------------------------------------------------------
-- Indexes on scan_jobs (only if table exists — separate statements for clarity)
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'scan_jobs'
    ) THEN
        CREATE INDEX IF NOT EXISTS scan_jobs_status_created_idx
            ON scan_jobs (status, created_at);
        CREATE INDEX IF NOT EXISTS scan_jobs_status_priority_created_idx
            ON scan_jobs (status, priority DESC, created_at);
        CREATE INDEX IF NOT EXISTS scan_jobs_data_source_status_idx
            ON scan_jobs (data_source_id, status);
        CREATE INDEX IF NOT EXISTS scan_jobs_parent_job_idx
            ON scan_jobs (parent_job_id);
        CREATE INDEX IF NOT EXISTS scan_jobs_heartbeat_idx
            ON scan_jobs (heartbeat_at)
            WHERE status = 'RUNNING'::scan_job_status;
        CREATE INDEX IF NOT EXISTS scan_jobs_requested_by_created_idx
            ON scan_jobs (requested_by, created_at DESC);
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- scan_failures(scan_job_id) — listing failures by job
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'scan_failures'
    ) THEN
        CREATE INDEX IF NOT EXISTS scan_failures_scan_job_idx ON scan_failures (scan_job_id);
    END IF;
END $$;
