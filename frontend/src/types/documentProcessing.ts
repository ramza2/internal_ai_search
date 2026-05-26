/** Query/body params for `POST .../process-pending-documents`. */
export type DocumentProcessRequestParams = {
  limit: number;
  max_file_size_bytes: number;
  include_extensions?: string;
  dry_run: boolean;
  reprocess_skipped: boolean;
  reprocess_hwp_no_extractable_text?: boolean;
  only_reprocess_hwp_no_extractable_text?: boolean;
};

/** One row in `items[]` from document process API (dry-run or live). */
export type DocumentProcessItem = {
  file_id: string;
  remote_path: string | null;
  filename: string | null;
  extension: string | null;
  status?: string;
  parser_name?: string | null;
  text_length?: number | null;
  content_hash?: string | null;
  reason?: string | null;
  planned_action?: string | null;
  analysis_status_before?: string | null;
  analysis_error_code_before?: string | null;
};

/** Success / error envelope from document process API (HTTP 200 may still be business error). */
export type DocumentProcessResponse = {
  status: string;
  message?: string;
  error?: string;
  data_source_id?: string;
  name?: string;
  scan_job_id?: string | null;
  target_count?: number;
  processed_count?: number;
  completed_count?: number;
  skipped_count?: number;
  failed_count?: number;
  dry_run: boolean;
  items: DocumentProcessItem[];
  warnings?: string[];
};
