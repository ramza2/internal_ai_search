-- Step 20: audit action_logs + action_result enum.

DO $$ BEGIN
    CREATE TYPE action_result AS ENUM ('SUCCESS', 'FAIL');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS action_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES app_users (id) ON DELETE SET NULL,
    action_type VARCHAR(128) NOT NULL,
    result action_result NOT NULL,
    request_url TEXT,
    request_method VARCHAR(16),
    search_query TEXT,
    data_source_id UUID,
    target_file_id UUID,
    target_file_path TEXT,
    ip_address VARCHAR(128),
    user_agent TEXT,
    detail JSONB,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS action_logs_created_at_idx
    ON action_logs (created_at DESC);
CREATE INDEX IF NOT EXISTS action_logs_user_id_idx ON action_logs (user_id);
CREATE INDEX IF NOT EXISTS action_logs_action_type_idx ON action_logs (action_type);
CREATE INDEX IF NOT EXISTS action_logs_result_idx ON action_logs (result);
CREATE INDEX IF NOT EXISTS action_logs_data_source_id_idx ON action_logs (data_source_id);
