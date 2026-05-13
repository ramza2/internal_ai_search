import type { SearchDataSourceScope, SearchMode } from "./search";

export interface AnswerRequest {
  query: string;
  data_source_id?: string | null;
  search_limit?: number;
  context_limit?: number;
  min_score?: number;
  answer_min_score?: number;
  include_extensions?: string[] | null;
  file_type?: string | null;
  temperature?: number;
  max_context_chars?: number;
  dry_run?: boolean;
  search_mode?: SearchMode;
  vector_weight?: number;
  keyword_weight?: number;
}

export interface AnswerCitation {
  rank: number;
  score: number;
  final_score: number;
  vector_score: number | null;
  keyword_score: number | null;
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

export interface ContextPreviewItem {
  context_index: number;
  file_id: string;
  filename: string | null;
  remote_path: string | null;
  chunk_id: string;
  start_line: number | null;
  end_line: number | null;
  score: number;
  snippet: string;
  preview_chars: number;
}

export interface AnswerSearchEnvelope {
  total_results: number;
  used_context_count: number;
  search_limit: number;
  context_limit: number;
  answer_min_score: number;
  max_context_chars: number;
  dropped_for_score?: number;
  dropped_for_budget?: number;
}

export interface AnswerResponse {
  status: string;
  query: string;
  answer: string | null;
  model: string | null;
  embedding_model?: string | null;
  embedding_provider?: string | null;
  search_mode: SearchMode;
  data_source_scope?: SearchDataSourceScope;
  search: AnswerSearchEnvelope;
  citations: AnswerCitation[];
  context_preview?: ContextPreviewItem[] | null;
  dry_run: boolean;
  message: string;
  warnings?: string[];
  finish_reason?: string | null;
}
