/** GET /api/search/data-sources — 읽기 전용, 활성 소스만 (민감 필드 없음) */
export interface SearchDataSource {
  id: string;
  name: string;
  source_type: string;
  description: string | null;
  last_scan_at: string | null;
  last_connection_success: boolean | null;
}

export interface SearchDataSourceListResponse {
  status: string;
  items: SearchDataSource[];
  total: number;
  message: string;
}
