/** GET /api/admin/dashboard/summary */
export interface DashboardUsersSummary {
  total: number;
  pending: number;
  active: number;
  inactive: number;
  locked: number;
  admins: number;
}

export interface DashboardDataSourcesSummary {
  total: number;
  active: number;
  inactive: number;
  connection_success: number;
  connection_failed: number;
  never_tested: number;
}

export interface DashboardFilesSummary {
  total_items: number;
  total_files: number;
  total_directories: number;
  total_size_bytes: number;
  total_size_human: string;
  pending: number;
  completed: number;
  failed: number;
  skipped: number;
  deleted: number;
}

export interface DashboardChunksSummary {
  total_chunks: number;
  embedded_chunks: number;
  pending_embedding_chunks: number;
}

export interface DashboardActivity24h {
  search_count_24h: number;
  rag_count_24h: number;
  login_count_24h: number;
  failed_action_count_24h: number;
}

export interface DashboardSummaryBlock {
  users: DashboardUsersSummary;
  data_sources: DashboardDataSourcesSummary;
  files: DashboardFilesSummary;
  chunks: DashboardChunksSummary;
  activity: DashboardActivity24h;
}

export interface RecentScanJobItem {
  id: string;
  data_source_id: string | null;
  data_source_name: string | null;
  job_type: string;
  status: string;
  total_files: number;
  processed_files: number;
  completed_files: number;
  failed_files: number;
  skipped_files: number;
  deleted_files: number;
  started_at: string | null;
  finished_at: string | null;
}

export interface RecentActionItem {
  id: string;
  user_name: string | null;
  action_type: string;
  result: string;
  search_query: string | null;
  created_at: string | null;
}

export interface DashboardProblemItems {
  failed_files_count: number;
  pending_files_count: number;
  pending_embedding_chunks_count: number;
  inactive_data_sources_count: number;
  pending_users_count: number;
}

export interface DashboardSummaryResponse {
  status: string;
  summary: DashboardSummaryBlock;
  recent_scan_jobs: RecentScanJobItem[];
  recent_actions: RecentActionItem[];
  problem_items: DashboardProblemItems;
  message: string;
}
