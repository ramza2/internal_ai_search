/** GET /api/admin/jobs, /api/admin/jobs/{id}, /api/admin/jobs/{id}/failures */

export interface AdminJob {
  id: string;
  data_source_id: string | null;
  data_source_name: string | null;
  job_type: string;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
  progress_percent: number | null;
  total_files: number;
  processed_files: number;
  completed_files: number;
  failed_files: number;
  skipped_files: number;
  deleted_files: number;
  current_file_path: string | null;
  error_message: string | null;
  requested_by: string | null;
  requested_by_login_id?: string | null;
  requested_by_name?: string | null;
  created_at: string | null;
  updated_at: string | null;
  /** Worker-ready (migration 022); often null until worker exists */
  job_params?: Record<string, unknown> | unknown[] | null;
  cancel_requested?: boolean;
  worker_id?: string | null;
  heartbeat_at?: string | null;
  parent_job_id?: string | null;
  pipeline_step?: string | null;
  retry_count?: number;
  max_retries?: number;
  /** Higher = higher dequeue priority (backend convention) */
  priority?: number;
}

export interface AdminJobListResponse {
  status: string;
  total: number;
  items: AdminJob[];
  warnings?: string[];
  message?: string | null;
}

export interface AdminJobDetailResponse {
  status: string;
  job: AdminJob;
  failures_count: number;
  warnings?: string[];
  message: string;
}

export interface AdminJobFailure {
  id: string;
  file_id: string;
  remote_path: string | null;
  error_code: string;
  error_message: string | null;
  created_at: string | null;
}

export interface AdminJobFailuresResponse {
  status: string;
  job_id: string;
  total: number;
  items: AdminJobFailure[];
  warnings?: string[];
}

export type AdminJobsListParams = {
  data_source_id?: string;
  status?: string;
  job_type?: string;
  keyword?: string;
  from_date?: string;
  to_date?: string;
  limit?: number;
  offset?: number;
};

export type AdminJobFailuresParams = {
  limit?: number;
  offset?: number;
};

/** POST /api/admin/jobs/test-enqueue (admin-only, dev/verification) */
export type AdminTestEnqueueBody = {
  data_source_id: string;
  job_type?: string;
  fail_test?: boolean;
  priority?: number;
};

export type AdminTestEnqueueResponse = {
  status: string;
  job_id: string;
  message: string;
};

/** POST /api/admin/jobs/sync-tree */
export type AdminSyncTreeJobRequest = {
  data_source_id: string;
  start_path?: string;
  max_depth?: number;
  max_items?: number;
  include_hidden?: boolean;
  apply_exclusions?: boolean;
  detect_deleted?: boolean;
  priority?: number;
};

export type AdminSyncTreeJobResponse = {
  status: string;
  job_id: string;
  job_type: string;
  message: string;
};

/** POST /api/admin/jobs/{job_id}/cancel */
export type AdminJobCancelRequest = {
  reason?: string | null;
};

export type AdminJobCancelResponse = {
  status: string;
  job_id: string;
  status_after: string;
  message: string;
};
