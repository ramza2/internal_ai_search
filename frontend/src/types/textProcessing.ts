/** Query params for `POST .../process-pending-text` (bytes for max size). */
export type ProcessPendingTextParams = {
  limit: number;
  max_file_size_bytes: number;
  include_extensions?: string;
  dry_run: boolean;
};
