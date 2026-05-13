export interface PreviewLine {
  line: number;
  text: string;
}

export interface FilePreviewOpenInfo {
  data_source_id: string;
  server_url: string;
  webdav_root_path: string | null;
  remote_path: string;
  webdav_url: string;
}

export interface FilePreviewFileMeta {
  file_id: string;
  data_source_id: string;
  data_source_name: string;
  source_type: string;
  filename: string | null;
  remote_path: string | null;
  extension: string | null;
  mime_type: string | null;
  size_bytes: number | null;
  analysis_status: string;
  last_modified?: string | null;
  last_indexed_at?: string | null;
  open_info: FilePreviewOpenInfo;
}

export interface FilePreviewBody {
  mode: string;
  chunk_id: string | null;
  chunk_index: number | null;
  start_line: number | null;
  end_line: number | null;
  context_lines: number;
  is_truncated: boolean;
  text: string;
  lines: PreviewLine[];
  line_count: number;
  char_count: number;
}

export interface FilePreviewResponse {
  status: string;
  file: FilePreviewFileMeta;
  preview: FilePreviewBody;
  highlights: Array<Record<string, unknown>>;
  message: string;
}

/** GET /api/files/stats 응답 (백엔드 file_stats_service와 정합) */
export interface FileStatsScope {
  data_source_id: string | null;
  data_source_name: string;
  source_type: string;
}

export interface FileStatsSummary {
  total_items: number;
  total_files: number;
  total_directories: number;
  total_size_bytes: number;
  total_size_human: string;
  latest_modified_at?: string | null;
  last_synced_at?: string | null;
}

export interface FileStatsByStatusRow {
  status: string;
  count: number;
}

export interface FileStatsByFileTypeRow {
  file_type: string;
  count: number;
  total_size_bytes: number;
}

export interface FileStatsByExtensionRow {
  extension: string;
  count: number;
  total_size_bytes: number;
  file_type: string;
}

export interface FileStatsTopFileRow {
  id: string;
  filename: string | null;
  remote_path: string | null;
  extension: string | null;
  size_bytes: number | null;
  size_human: string;
  last_modified: string | null;
}

export interface FileStatsByDataSourceRow {
  data_source_id: string;
  data_source_name: string;
  source_type: string;
  total_files: number;
  total_directories: number;
  total_size_bytes: number;
  last_scan_at: string | null;
}

export interface FileStatsResponse {
  status: string;
  message?: string;
  scope: FileStatsScope;
  summary: FileStatsSummary;
  by_analysis_status: FileStatsByStatusRow[];
  by_extension: FileStatsByExtensionRow[];
  by_file_type: FileStatsByFileTypeRow[];
  top_largest_files: FileStatsTopFileRow[];
  by_data_source?: FileStatsByDataSourceRow[] | null;
}
