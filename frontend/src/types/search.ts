export type SearchMode = "vector" | "keyword" | "hybrid";

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
  total_results: number;
  results: SearchResultItem[];
  message?: string;
  [key: string]: unknown;
}
