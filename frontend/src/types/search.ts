export type SearchMode = "vector" | "keyword" | "hybrid";

/** 백엔드 `app.utils.file_type` 분류와 동일한 문자열 */
export type FileTypeBucket =
  | "DOCUMENT"
  | "SOURCE_CODE"
  | "CONFIG"
  | "LOG"
  | "IMAGE"
  | "AUDIO_VIDEO"
  | "ARCHIVE"
  | "BINARY"
  | "UNKNOWN";

export interface SearchRequest {
  query: string;
  data_source_id?: string | null;
  limit?: number;
  min_score?: number;
  include_extensions?: string[] | null;
  file_type?: string | null;
  search_mode?: SearchMode;
  vector_weight?: number;
  keyword_weight?: number;
  vector_candidate_limit?: number;
  keyword_candidate_limit?: number;
}

export interface SearchDataSourceScope {
  data_source_id: string | null;
  data_source_name: string;
}

export interface SearchWeights {
  vector_weight: number;
  keyword_weight: number;
}

export interface SearchResultItem {
  rank: number;
  score: number;
  final_score: number;
  vector_score: number | null;
  keyword_score: number | null;
  distance: number | null;
  match_reasons: string[];
  search_mode: SearchMode;
  data_source_id: string;
  data_source_name: string;
  source_type: string;
  file_id: string;
  filename: string | null;
  remote_path: string | null;
  extension: string | null;
  file_type: string | null;
  chunk_id: string;
  chunk_index: number;
  start_line: number | null;
  end_line: number | null;
  snippet: string;
  last_modified?: string | null;
  last_indexed_at?: string | null;
}

export interface SearchResponse {
  status: string;
  query: string;
  search_mode: SearchMode;
  embedding_model?: string | null;
  embedding_provider?: string | null;
  expected_dimension?: number | null;
  data_source_scope?: SearchDataSourceScope;
  total_results: number;
  limit: number;
  min_score: number;
  weights: SearchWeights;
  results: SearchResultItem[];
  message: string;
}
